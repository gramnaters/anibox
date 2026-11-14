"""
Generic HLS proxy.

Stremio's streaming server does NOT forward behaviorHints.proxyHeaders to
URLs discovered INSIDE an m3u8 playlist (sub-playlists, segments, keys).
CDNs like anvod / uwucdn / zephyr require a Referer on every request, so without a
proxy those requests 403 and playback hangs.

This blueprint fixes that by rewriting EVERY URL in a playlist to point back
at this addon (/m3u8/<id>, /seg/<id>, /subtitles/<id>). The addon fetches
from the CDN with the stored headers and streams the bytes to Stremio.

To survive server restarts, worker cycling, and Render redeployments, proxy IDs
support fully stateless tokens (prefixed with 'pl_z_', 'sg_z_', 'sub_z_')
which compress and encode the upstream target URL and Referer directly into
the URL itself. In addition, an SQLite disk database caches all registered
mappings so legacy SHA1 IDs also survive cold process restarts.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
import warnings
import zlib
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

_IMAGE_MAGIC = (b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'RIFF', b'\x00\x00\x00\x0cftypwebp')
_BYTE_PATCH_HOSTS = ('hanerix.com', 'smoothpre', 'vidhide', 'tiktokcdn.com', 'p16-ad-site-sign')

# Hosts whose segments MUST pass through Render:
# 1. Byte-patching hosts (StreamHG PNG headers on TikTok CDN)
# 2. IP/ASN-locked hosts (Byse / SprintCDN / StreamRuby / Zephyr rotating
#    edges where the signed token or Referer is tied to Render's IP / origin)
#
# IMPORTANT: Keep this in sync with _PROXY_MEDIA_HOSTS in stream.py.
_MUST_PROXY_SEGMENT_HOSTS = (
    # StreamHG / TikTok CDN byte-patching
    'hanerix.com', 'smoothpre', 'vidhide', 'tiktokcdn.com', 'p16-ad-site-sign',
    # Byse / SprintCDN / StreamRuby IP-locked rotating edges
    'sprintcdn', 'r66nv9ed.com', 'marketforecasting.cfd', 'streamruby.net',
    'vmnow.online', 'vmpx.online', 'owphbf24.com', 'byse', 'bysetayico',
    # Zephyr / FirePlayer IP-signed CDN tokens and edge servers
    'zephyrix', 'zephyrflick', 'as-cdn', 'zn-grid',
)

# ---------------------------------------------------------------------------
# SQLite Persistent Cache Setup (survives worker reboots within container)
# ---------------------------------------------------------------------------
_DB_PATH = os.environ.get('PROXY_DB_PATH')
if not _DB_PATH:
    _temp_dir = tempfile.gettempdir()
    _DB_PATH = os.path.join(_temp_dir, 'anibox_proxy_cache.db')


def _init_db():
    try:
        with sqlite3.connect(_DB_PATH, timeout=5) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS proxy_mappings (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    referer TEXT,
                    type TEXT,
                    created_at REAL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_proxy_created ON proxy_mappings(created_at)')
            conn.commit()
    except Exception as e:
        print(f'[proxy_db] init error: {e}')


_init_db()


def _db_save(mapping_id: str, url: str, referer: str, kind: str):
    """Persist mapping into local SQLite cache."""
    try:
        with sqlite3.connect(_DB_PATH, timeout=3) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO proxy_mappings (id, url, referer, type, created_at) VALUES (?, ?, ?, ?, ?)',
                (mapping_id, url, referer or '', kind or 'm3u8', time.time())
            )
            conn.commit()
    except Exception:
        pass


def _db_lookup(mapping_id: str):
    """Look up mapping from local SQLite cache."""
    try:
        with sqlite3.connect(_DB_PATH, timeout=3) as conn:
            cursor = conn.execute(
                'SELECT url, referer, type FROM proxy_mappings WHERE id = ?',
                (mapping_id,)
            )
            row = cursor.fetchone()
            if row:
                u, r, k = row
                headers = {'User-Agent': DEFAULT_UA}
                if r:
                    headers['Referer'] = r
                return {'url': u, 'headers': headers, 'type': k or 'm3u8'}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Stateless Token Encoding / Decoding (zero server state required)
# ---------------------------------------------------------------------------
def encode_proxy_token(url: str, referer: str = '', kind: str = 'm3u8') -> str:
    """Encode upstream url, referer, and kind into a stateless URL-safe token."""
    payload = {'u': url}
    if referer:
        payload['r'] = referer
    if kind and kind != 'm3u8':
        payload['k'] = kind
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    comp = zlib.compress(raw, level=9)
    return base64.urlsafe_b64encode(comp).decode('ascii').rstrip('=')


def decode_proxy_token(token: str):
    """Decode a stateless token into {'url': ..., 'headers': {...}, 'type': ...}."""
    try:
        pad = '=' * (-len(token) % 4)
        raw = zlib.decompress(base64.urlsafe_b64decode(token + pad))
        payload = json.loads(raw.decode('utf-8'))
        referer = payload.get('r', '')
        headers = {'User-Agent': DEFAULT_UA}
        if referer:
            headers['Referer'] = referer
        return {
            'url': payload['u'],
            'headers': headers,
            'type': payload.get('k', 'm3u8')
        }
    except Exception as e:
        print(f'[proxy] decode token error: {e}')
        return None


def _needs_byte_patching(url: str) -> bool:
    """Return True only for hosts whose video segments contain an image wrapper header (e.g. StreamHG PNG)."""
    low = (url or '').lower()
    return any(h in low for h in _BYTE_PATCH_HOSTS)


def _needs_proxy_segment(url: str) -> bool:
    """Return True for hosts whose video segments require proxying (headers or byte stripping)."""
    low = (url or '').lower()
    return any(h in low for h in _MUST_PROXY_SEGMENT_HOSTS) or _needs_byte_patching(url)


def _find_media_offset(data: bytes) -> int:
    """Find byte offset where real media (MPEG-TS or MP4) begins, skipping any image wrapper."""
    is_img = len(data) >= 4 and any(data[:len(m)] == m for m in _IMAGE_MAGIC)
    # Direct MPEG-TS check (3 sync bytes at stride 188)
    if len(data) >= 188 * 3 and data[0] == 0x47 and data[188] == 0x47 and data[376] == 0x47:
        return 0
    # Direct MP4 box check
    if b'ftyp' in data[:32] or b'moof' in data[:32] or b'mdat' in data[:32]:
        return 0
    # Check after PNG IEND chunk (common StreamHG / TikTok CDN wrapper)
    iend = data.find(b'IEND')
    if iend != -1 and iend + 8 + 188 * 2 < len(data):
        pos = iend + 8
        if data[pos] == 0x47 and data[pos + 188] == 0x47:
            return pos
    # General scan in first 1024 bytes for 3 consecutive TS sync bytes
    if len(data) >= 188 * 3:
        limit = min(1024, len(data) - 188 * 3)
        for pos in range(limit):
            if data[pos] == 0x47 and data[pos + 188] == 0x47 and data[pos + 376] == 0x47:
                return pos
    return -1 if is_img else 0


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
            err_str = str(e).lower()
            if 'nameresolutionerror' in err_str or 'getaddrinfo failed' in err_str or 'connection refused' in err_str:
                break
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
    """Pick a filename extension for a proxied segment URL."""
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
    """Return this addon's public base URL for the current request."""
    return _addon_base()


def register_proxy_url(url, headers, base_url=None, kind=None, ext=None):
    """Register an upstream media URL and return a stateless, durable proxy URL.

    The returned URL encodes the target and headers directly (pl_z_<token>.m3u8),
    guaranteeing that playback will NEVER 404 even after Render redeployments or container restarts.
    """
    headers = headers or {}
    kind = kind or ('m3u8' if _is_playlist_url(url) else 'segment')
    referer = headers.get('Referer') or ''
    token = encode_proxy_token(url, referer, kind)

    prefix, route = ('pl_', 'm3u8') if kind == 'm3u8' else ('sg_', 'seg')
    pid_stateless = f'{prefix}z_{token}'

    # Also compute legacy SHA1 hash and store both in memory + SQLite
    pid_hash = prefix + hashlib.sha1((url + '|' + referer).encode()).hexdigest()[:16]
    mapping_data = {'url': url, 'headers': headers, 'type': kind}
    playlist_mappings[pid_stateless] = mapping_data
    playlist_mappings[pid_hash] = mapping_data
    _db_save(pid_stateless, url, referer, kind)
    _db_save(pid_hash, url, referer, kind)

    if kind == 'segment':
        suffix = ('.' + ext.lstrip('.')) if ext else _segment_ext(url)
    else:
        suffix = '.m3u8'
    return f'{(base_url or _addon_base()).rstrip("/")}/{route}/{pid_stateless}{suffix}'


def _rewrite_m3u8_urls(content, base_url, headers):
    """Rewrite ALL URLs in an m3u8 playlist into stateless proxy URLs."""
    addon_base = _addon_base()
    referer = ((headers or {}).get('Referer') or '')

    def _register(u, kind):
        token = encode_proxy_token(u, referer, kind)
        if kind == 'subtitle':
            sid_stateless = f'sub_z_{token}'
            sid_hash = 'sub_' + hashlib.sha1((u + '|' + referer).encode()).hexdigest()[:16]
            m_data = {'url': u, 'headers': headers}
            subtitle_mappings[sid_stateless] = m_data
            subtitle_mappings[sid_hash] = m_data
            _db_save(sid_stateless, u, referer, 'subtitle')
            _db_save(sid_hash, u, referer, 'subtitle')
            return f'{addon_base}/subtitles/{sid_stateless}'

        prefix, route = ('pl_', 'm3u8') if kind == 'm3u8' else ('sg_', 'seg')
        pid_stateless = f'{prefix}z_{token}'
        pid_hash = prefix + hashlib.sha1((u + '|' + referer).encode()).hexdigest()[:16]
        m_data = {'url': u, 'headers': headers, 'type': kind}
        playlist_mappings[pid_stateless] = m_data
        playlist_mappings[pid_hash] = m_data
        _db_save(pid_stateless, u, referer, kind)
        _db_save(pid_hash, u, referer, kind)

        suffix = _segment_ext(u) if kind == 'segment' else '.m3u8'
        return f'{addon_base}/{route}/{pid_stateless}{suffix}'

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
        absu = _resolve_url(base_url, stripped)
        if _is_playlist_url(absu) or prev_tag == 'playlist':
            out.append(_register(absu, 'm3u8'))
        elif _needs_proxy_segment(absu):
            # Proxy segments that need byte stripping or are IP/Referer bound
            out.append(_register(absu, 'segment'))
        else:
            # Safe direct CDN URL for video segment: ExoPlayer/mpv downloads directly
            out.append(absu)
        prev_tag = ''

    return '\n'.join(out)


@proxy_bp.route('/m3u8/<playlist_id>')
def proxy_m3u8(playlist_id):
    """Proxy an m3u8 playlist from the CDN, rewriting all internal URLs."""
    raw_id = playlist_id.split('.', 1)[0]
    mapping = None

    # 1. Stateless token lookup (100% resilient across server redeployments)
    if raw_id.startswith('pl_z_'):
        mapping = decode_proxy_token(raw_id[5:])

    # 2. In-memory cache lookup
    if not mapping:
        mapping = playlist_mappings.get(playlist_id) or playlist_mappings.get(raw_id)

    # 3. Persistent SQLite disk lookup (for legacy SHA1 hashes or cross-process lookups)
    if not mapping:
        mapping = _db_lookup(raw_id) or _db_lookup(playlist_id)

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
    raw_id = segment_id.split('.', 1)[0]
    mapping = None

    # 1. Stateless token lookup
    if raw_id.startswith('sg_z_'):
        mapping = decode_proxy_token(raw_id[5:])

    # 2. In-memory cache lookup
    if not mapping:
        mapping = playlist_mappings.get(segment_id) or playlist_mappings.get(raw_id)

    # 3. Persistent SQLite disk lookup
    if not mapping:
        mapping = _db_lookup(raw_id) or _db_lookup(segment_id)

    if not mapping:
        abort(404, description='Segment mapping expired or not found')

    # Bandwidth optimization: If this segment does not require proxying, redirect directly to CDN
    if not _needs_proxy_segment(mapping.get('url', '')):
        from flask import redirect
        return redirect(mapping['url'], code=302)

    upstream_headers = dict(mapping.get('headers') or {})
    # Request raw uncompressed bytes from upstream CDN so video/audio segments are never double-compressed
    upstream_headers['Accept-Encoding'] = 'identity'
    # Forward the client's Range header so seeking works for direct files.
    client_range = request.headers.get('Range')
    if client_range:
        upstream_headers['Range'] = client_range

    try:
        r = _fetch_upstream(mapping['url'], upstream_headers, stream=True)
        if r.status_code not in (200, 206):
            abort(502, description=f'CDN returned {r.status_code}')

        # Determine the real media content-type:
        # Pirate CDNs (Zephyr, etc.) disguise TS segments as .js, .css, .woff to abuse CF caching.
        # We must ALWAYS force the proper binary media Content-Type so players (ExoPlayer, mpv, VLC)
        # demux the segments correctly and upstream proxies do not corrupt them with Brotli/Gzip text compression!
        raw_ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        path = urlparse(mapping['url']).path.lower()
        req_path = request.path.lower()

        if req_path.endswith('.ts') or path.endswith('.ts') or path.endswith(('.js', '.css', '.woff', '.png', '.jpg')):
            ctype = 'video/MP2T'
        elif req_path.endswith('.m4s') or path.endswith(('.m4s', '.mp4')):
            ctype = 'video/mp4'
        elif req_path.endswith('.aac') or path.endswith('.aac'):
            ctype = 'audio/aac'
        elif req_path.endswith('.m4a') or path.endswith('.m4a'):
            ctype = 'audio/mp4'
        elif req_path.endswith('.mp3') or path.endswith('.mp3'):
            ctype = 'audio/mpeg'
        elif req_path.endswith('.vtt') or path.endswith('.vtt'):
            ctype = 'text/vtt'
        elif raw_ctype.startswith(('video/', 'audio/')):
            ctype = raw_ctype
        else:
            ctype = 'video/MP2T'

        length = r.headers.get('Content-Length')
        is_large = length and length.isdigit() and int(length) > 10_000_000 and not client_range
        needs_patch = _needs_byte_patching(mapping.get('url', ''))
        if is_large or (not needs_patch and not client_range):
            # For non-patching segments (e.g. Byse/SprintCDN/Zephyr), stream directly in chunks
            response = Response(
                stream_with_context(r.iter_content(chunk_size=65536)),
                status=r.status_code,
                content_type=ctype,
            )
        else:
            content = r.content
            if needs_patch:
                offset = _find_media_offset(content)
                if offset > 0:
                    content = content[offset:]
                    ctype = 'video/MP2T'
            response = Response(content, status=r.status_code, content_type=ctype)
            response.headers['Content-Length'] = str(len(content))

        for header in ('Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified'):
            if header in r.headers and header not in response.headers:
                response.headers[header] = r.headers[header]
        response.headers['Content-Type'] = ctype
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range, Accept-Ranges'
        response.headers['Cache-Control'] = 'public, max-age=86400, no-transform'
        return response
    except Exception as e:
        print(f'[proxy] error proxying segment {segment_id}: {e}')
        abort(502)


@proxy_bp.route('/subtitles/<subtitle_id>')
def proxy_subtitle(subtitle_id):
    """Proxy subtitle files with the correct content-type."""
    raw_id = subtitle_id.split('.', 1)[0]
    mapping = None

    # 1. Stateless token lookup
    if raw_id.startswith('sub_z_'):
        mapping = decode_proxy_token(raw_id[6:])

    # 2. In-memory cache lookup
    if not mapping:
        mapping = subtitle_mappings.get(subtitle_id) or subtitle_mappings.get(raw_id)

    # 3. Persistent SQLite disk lookup
    if not mapping:
        mapping = _db_lookup(raw_id) or _db_lookup(subtitle_id)

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
