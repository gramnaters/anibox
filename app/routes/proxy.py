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
subtitle_mappings = TTLCache(maxsize=500, ttl=3600)

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
    return u.lower().endswith(('.vtt', '.srt', '.ass', '.ssa'))


def _rewrite_m3u8_urls(content, base_url, headers):
    """Rewrite ALL URLs in an m3u8 playlist to go through this addon."""
    addon_base = request.host_url.rstrip('/')

    def _register(u, kind):
        if kind == 'subtitle':
            sid = 'sub_' + secrets.token_hex(8)
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
        return f'{addon_base}/{route}/{pid}'

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
        if _is_subtitle_url(absu):
            out.append(_register(absu, 'subtitle'))
        elif _is_playlist_url(absu) or prev_tag == 'playlist':
            out.append(_register(absu, 'm3u8'))
        else:
            out.append(_register(absu, 'segment'))
        prev_tag = ''

    return '\n'.join(out)


@proxy_bp.route('/m3u8/<playlist_id>')
def proxy_m3u8(playlist_id):
    """Proxy an m3u8 playlist from the CDN, rewriting all internal URLs."""
    mapping = playlist_mappings.get(playlist_id)
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
    """Proxy a video segment from the CDN with the correct Referer."""
    mapping = playlist_mappings.get(segment_id)
    if not mapping:
        abort(404, description='Segment mapping expired or not found')

    try:
        r = _fetch_upstream(mapping['url'], mapping.get('headers') or {}, stream=True)
        if r.status_code != 200:
            abort(502, description=f'CDN returned {r.status_code}')

        path = urlparse(mapping['url']).path.lower()
        if path.endswith('.m4s'):
            ctype = 'video/mp4'
        elif path.endswith('.aac'):
            ctype = 'audio/aac'
        elif path.endswith('.m4a'):
            ctype = 'audio/mp4'
        elif path.endswith('.mp3'):
            ctype = 'audio/mpeg'
        elif path.endswith('.ts'):
            ctype = 'video/MP2T'
        else:
            ctype = 'video/MP2T'

        response = Response(
            stream_with_context(r.iter_content(chunk_size=65536)),
            content_type=ctype,
        )
        if 'Content-Length' in r.headers:
            response.headers['Content-Length'] = r.headers['Content-Length']
        if 'Accept-Ranges' in r.headers:
            response.headers['Accept-Ranges'] = r.headers['Accept-Ranges']
        if 'Content-Range' in r.headers:
            response.headers['Content-Range'] = r.headers['Content-Range']
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response
    except Exception as e:
        print(f'[proxy] error proxying segment {segment_id}: {e}')
        abort(502)


@proxy_bp.route('/subtitles/<subtitle_id>')
def proxy_subtitle(subtitle_id):
    """Proxy subtitle files with the correct content-type."""
    mapping = subtitle_mappings.get(subtitle_id)
    if not mapping:
        abort(404)

    try:
        r = _fetch_upstream(mapping['url'], mapping.get('headers') or {})
        if r.status_code != 200:
            abort(502)

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
