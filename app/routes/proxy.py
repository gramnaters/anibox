"""
Generic HLS proxy.

Stremio's streaming server does NOT forward behaviorHints.proxyHeaders to
URLs discovered INSIDE an m3u8 playlist (sub-playlists, segments, keys).
CDNs like anvod / uwucdn require a Referer on every request, so without a
proxy those requests 403 and playback hangs.

This blueprint fixes that by rewriting EVERY URL in a playlist to point back
at this addon (/m3u8/<id>, /seg/<id>, /subtitles/<id>). The addon fetches
from the CDN with the stored headers and streams the bytes to Stremio.
"""

import re
import secrets
import hashlib
import time
import warnings
from urllib.parse import urljoin, urlparse

import requests
from cachetools import TTLCache
from flask import Blueprint, Response, abort, request, stream_with_context

warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

proxy_bp = Blueprint('proxy', __name__)

# id -> {'url': ..., 'headers': {...}, 'type': 'm3u8'|'segment'}
playlist_mappings = TTLCache(maxsize=50000, ttl=43200)

# id -> {'url': ..., 'headers': {...}}
subtitle_mappings = TTLCache(maxsize=8000, ttl=3600)

_cookie_jar = requests.cookies.RequestsCookieJar()

DEFAULT_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')


def _fetch_upstream(url, headers, max_retries=4, stream=False, timeout=25):
    """Fetch a URL from the CDN with retry on 403/5xx and timeout backoff."""
    last = None
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, stream=stream, verify=False)
            if r.cookies:
                for c in r.cookies:
                    _cookie_jar.set_cookie(c)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 429, 500, 502, 503, 504, 522, 524):
                time.sleep(1.5 * (attempt + 1))
                last = r
                continue
            return r
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    if isinstance(last, Exception):
        raise last
    return last


def _resolve_url(base_url, u):
    """Resolve a possibly-relative URL against the playlist base URL."""
    if u.startswith('http://') or u.startswith('https://'):
        return u
    return urljoin(base_url, u)


def _is_playlist_url(u):
    path = urlparse(u).path.lower()
    return path.endswith('.m3u8') or path.endswith('.m3u') or '.m3u8' in u


def _is_subtitle_url(u):
    path = urlparse(u).path.lower()
    return path.endswith(('.vtt', '.srt', '.ass', '.ssa'))


_SEGMENT_EXTS = ('.ts', '.m4s', '.mp4', '.m4a', '.aac', '.mp3', '.key',
                 '.vtt', '.srt', '.ass', '.ssa')


def _segment_ext(u):
    """Pick a filename extension for a proxied segment URL.

    Some HLS demuxers (ffmpeg) reject segment URLs without a known media
    extension, so the proxy exposes /seg/<id>.<ext> instead of /seg/<id>.
    """
    path = urlparse(u).path.lower()
    for ext in _SEGMENT_EXTS:
        if path.endswith(ext):
            return ext
    return '.ts'


def _addon_base():
    """Base URL of this addon as seen by the client (honours Render's TLS proxy)."""
    scheme = (request.headers.get('X-Forwarded-Proto') or request.scheme).split(',')[0].strip()
    return f'{scheme}://{request.host}'.rstrip('/')


def addon_base_url():
    """Return this addon's public base URL for the current request.

    Call this on the request thread and pass the result to register_proxy_url
    when registering from a worker thread (Flask's request is thread-local).
    """
    return _addon_base()


def register_proxy_url(url, headers, base_url=None, kind=None, ext=None):
    """Register an upstream media URL and return a local proxy URL for it.

    Used by the stream route for CDNs that reject browser Origin headers or
    require headers on sub-playlists/segments, which Stremio does not forward.
    ``base_url`` must be supplied when called outside the request thread.
    ``kind`` forces 'm3u8' for playlists whose URL carries no playlist
    extension (e.g. Zephyr's /cdn/hls/<id>/master.txt).
    ``ext`` forces the proxy URL's media extension for direct files whose
    upstream URL has none (e.g. an extensionless MP4) so players demux it
    correctly.
    """
    headers = headers or {}
    kind = kind or ('m3u8' if _is_playlist_url(url) else 'segment')
    prefix, route = ('pl_', 'm3u8') if kind == 'm3u8' else ('sg_', 'seg')
    pid = prefix + hashlib.sha1(
        (url + '|' + (headers.get('Referer') or '')).encode()
    ).hexdigest()[:16]
    playlist_mappings[pid] = {'url': url, 'headers': headers, 'type': kind}
    if kind == 'segment':
        suffix = ('.' + ext.lstrip('.')) if ext else _segment_ext(url)
    else:
        suffix = '.m3u8'
    return f'{(base_url or _addon_base()).rstrip("/")}/{route}/{pid}{suffix}'


def _rewrite_m3u8_urls(content, base_url, headers):
    """Rewrite ALL URLs in an m3u8 playlist to go through this addon."""
    addon_base = _addon_base()

    def _register(u, kind):
        if kind == 'subtitle':
            sid = 'sub_' + hashlib.sha1(
                (u + '|' + ((headers or {}).get('Referer') or '')).encode()
            ).hexdigest()[:16]
            subtitle_mappings[sid] = {'url': u, 'headers': headers}
            return f'{addon_base}/subtitles/{sid}'
        prefix, route = ('pl_', 'm3u8') if kind == 'm3u8' else ('sg_', 'seg')
        # Deterministic IDs: the same upstream URL always maps to the same
        # entry, so repeated playlist fetches can't flood the cache and evict
        # the IDs Stremio is currently playing.
        pid = prefix + hashlib.sha1(
            (u + '|' + ((headers or {}).get('Referer') or '')).encode()
        ).hexdigest()[:16]
        playlist_mappings[pid] = {'url': u, 'headers': headers, 'type': kind}
        suffix = _segment_ext(u) if kind == 'segment' else '.m3u8'
        return f'{addon_base}/{route}/{pid}{suffix}'

    def _rewrite_uri(m, line):
        u = m.group(1)
        if not u or u.startswith('data:'):
            return m.group(0)
        absu = _resolve_url(base_url, u)
        if 'TYPE=SUBTITLES' in line or _is_subtitle_url(absu):
            return f'URI="{_register(absu, "subtitle")}"'
        if 'TYPE=AUDIO' in line or 'TYPE=VIDEO' in line or _is_playlist_url(absu):
            return f'URI="{_register(absu, "m3u8")}"'
        return f'URI="{_register(absu, "segment")}"'

    out = []
    prev_tag = ''
    for line in content.split('\n'):
        line = re.sub(r'URI="([^"]+)"', lambda m: _rewrite_uri(m, line), line)
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            out.append(line)
            if stripped.startswith('#EXT-X-STREAM-INF') or stripped.startswith('#EXT-X-I-FRAME-STREAM-INF'):
                prev_tag = 'playlist'
            else:
                prev_tag = ''
            continue
        # Every non-comment line in an HLS playlist is a URI - it may be
        # absolute, root-relative (/seg.m4s) or bare-relative (seg-1.m4s).
        # Resolve against the playlist base and register all of them so the
        # CDN Referer is applied to sub-playlists, keys, init segments, etc.
        absu = _resolve_url(base_url, stripped)
        if _is_playlist_url(absu) or prev_tag == 'playlist':
            out.append(_register(absu, 'm3u8'))
        else:
            # Subtitle segments (.vtt/.srt) land here too: /seg/<id>.vtt gives
            # them a real extension and text/vtt content-type, which players
            # require inside subtitle playlists.
            out.append(_register(absu, 'segment'))
        prev_tag = ''

    return '\n'.join(out)


@proxy_bp.route('/m3u8/<playlist_id>')
def proxy_m3u8(playlist_id):
    """Proxy an m3u8 playlist from the CDN, rewriting all internal URLs."""
    mapping = playlist_mappings.get(playlist_id) or playlist_mappings.get(
        playlist_id.split('.', 1)[0]
    )
    if not mapping:
        abort(404, description='Playlist mapping expired or not found')

    try:
        r = _fetch_upstream(mapping['url'], mapping.get('headers') or {})
        if r.status_code != 200:
            abort(502, description=f'Upstream returned {r.status_code}')

        content = _rewrite_m3u8_urls(r.text, mapping['url'], mapping.get('headers') or {})

        response = Response(content, mimetype='application/vnd.apple.mpegurl')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        print(f'[proxy] error proxying m3u8 {playlist_id}: {e}')
        abort(502)


@proxy_bp.route('/seg/<segment_id>')
def proxy_segment(segment_id):
    """Proxy a segment or direct media file from the CDN with the correct headers."""
    # The public URL carries a media extension (/seg/sg_abc.ts); the mapping
    # key does not.
    mapping = playlist_mappings.get(segment_id) or playlist_mappings.get(
        segment_id.split('.', 1)[0]
    )
    if not mapping:
        abort(404, description='Segment mapping expired or not found')

    upstream_headers = dict(mapping.get('headers') or {})
    # Forward the client's Range header so seeking works for direct files.
    client_range = request.headers.get('Range')
    if client_range:
        upstream_headers['Range'] = client_range

    try:
        r = _fetch_upstream(mapping['url'], upstream_headers, stream=True)
        if r.status_code not in (200, 206):
            abort(502, description=f'CDN returned {r.status_code}')

        ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip()
        if not ctype or ctype.startswith('text/html'):
            path = urlparse(mapping['url']).path.lower()
            if path.endswith('.m4s') or path.endswith('.mp4'):
                ctype = 'video/mp4'
            elif path.endswith('.aac'):
                ctype = 'audio/aac'
            elif path.endswith('.m4a'):
                ctype = 'audio/mp4'
            elif path.endswith('.mp3'):
                ctype = 'audio/mpeg'
            elif path.endswith('.vtt'):
                ctype = 'text/vtt'
            else:
                ctype = 'video/MP2T'

        response = Response(
            stream_with_context(r.iter_content(chunk_size=65536)),
            status=r.status_code,
            content_type=ctype,
        )
        for header in ('Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified'):
            if header in r.headers:
                response.headers[header] = r.headers[header]
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range, Accept-Ranges'
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response
    except Exception as e:
        print(f'[proxy] error proxying segment {segment_id}: {e}')
        abort(502)


@proxy_bp.route('/subtitles/<subtitle_id>')
def proxy_subtitle(subtitle_id):
    """Proxy subtitle files with the correct content-type.

    Some CDNs (PirateXPlay's sprintcdn edges) publish subtitles as an HLS
    playlist of .vtt segments instead of a single file. Those URLs are
    token/IP-bound, so passing the body through verbatim makes the player
    fetch the segments directly from the CDN and hang. Detect that shape and
    proxy every segment too.
    """
    mapping = subtitle_mappings.get(subtitle_id)
    if not mapping:
        abort(404, description='Subtitle mapping expired or not found')

    try:
        r = _fetch_upstream(mapping['url'], mapping.get('headers') or {})
        if r.status_code != 200:
            abort(502, description=f'Upstream returned {r.status_code}')

        body = r.text or ''
        if '#EXTM3U' in body[:1024]:
            content = _rewrite_m3u8_urls(body, mapping['url'],
                                         mapping.get('headers') or {})
            response = Response(content, mimetype='application/vnd.apple.mpegurl')
        else:
            if subtitle_id.endswith('.srt') or mapping['url'].lower().endswith('.srt'):
                content_type = 'application/x-subrip'
            elif mapping['url'].lower().endswith('.ass') or mapping['url'].lower().endswith('.ssa'):
                content_type = 'text/x-ssa'
            else:
                content_type = 'text/vtt'
            response = Response(r.content, mimetype=content_type)

        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response
    except Exception as e:
        print(f'[proxy] error proxying subtitle {subtitle_id}: {e}')
        abort(502)
