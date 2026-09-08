import urllib.parse, requests, re, time, inspect
from flask import Blueprint, abort, request
from cachetools import TTLCache
from app.api import ALL_PROVIDERS
from app.api.twopeckle import set_config as set_twopeckle_config
from app.routes.utils import respond_with, log_error
from app.routes.proxy import _fetch_upstream
from app.players import resolve_stream, PLAYER_NAMES
from app.config_parser import parse_config, get_provider_from_config

stream_bp = Blueprint('stream', __name__)
tmdb_title_cache = TTLCache(maxsize=500, ttl=3600)

# Image magic bytes -> a "video" segment that is really an ad image (pollution).
_IMAGE_MAGIC = (b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'RIFF', b'\x00\x00\x00\x0cftypwebp')
_AD_CDN_MARKERS = ('tiktokcdn', 'ibyteimg', 'ad-site')
_IP_BLOCK_MARKERS = ('ip blocked', 'access denied', 'forbidden', 'your ip has been',
                     'rate limit', 'too many requests', 'captcha', 'attention required',
                     'unusual traffic', 'verify you are human')
_pollution_cache = TTLCache(maxsize=2000, ttl=3600)


def _m3u8_is_polluted(url, referer=''):
    """Verify a master m3u8 -> first variant -> first segment actually returns
    video bytes (not ad images, ad-CDN playlists, HTML/IP-block pages)."""
    if url in _pollution_cache:
        return _pollution_cache[url]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'}
    if referer:
        headers['Referer'] = referer
    elif 'watching.onl' in url:
        headers['Referer'] = 'https://megaplay.buzz/'
    elif 'itsnitrox' in url or 'nxsha' in url:
        headers['Referer'] = 'https://nxsha.space/'

    def _bad(text):
        low = text.lower()
        return any(m in low for m in _AD_CDN_MARKERS) or any(m in low for m in _IP_BLOCK_MARKERS)

    def _is_image(data):
        return len(data) >= 4 and any(data[:len(m)] == m for m in _IMAGE_MAGIC)

    try:
        # Master playlist
        r = _fetch_upstream(url, headers, timeout=10)
        if r is None or r.status_code != 200:
            # Transient 403/timeout: don't hard-fail, the proxy retries during
            # playback. Only fail when we actually see bad content.
            return False
        master = r.text
        if _bad(master):
            _pollution_cache[url] = True
            return True

        uris = [l.strip() for l in master.splitlines() if l.strip() and not l.startswith('#') and not l.startswith('data:')]
        if not uris:
            return False
        first = uris[0]
        variant_url = first if first.startswith('http') else url.rsplit('/', 1)[0] + '/' + first

        rv = _fetch_upstream(variant_url, headers, timeout=10)
        if rv is None or rv.status_code != 200:
            return False
        variant = rv.text
        if _bad(variant):
            _pollution_cache[url] = True
            return True

        # First segment could be directly in variant, or variant is another playlist
        segs = [l.strip() for l in variant.splitlines() if l.strip() and not l.startswith('#') and not l.startswith('data:')]
        if not segs:
            return False
        seg = segs[0]
        seg_url = seg if seg.startswith('http') else variant_url.rsplit('/', 1)[0] + '/' + seg

        # First segment: only need the first bytes (magic + size check)
        seg_headers = dict(headers)
        seg_headers['Range'] = 'bytes=0-16383'
        rs = _fetch_upstream(seg_url, seg_headers, timeout=12)
        if rs is None or rs.status_code != 200:
            return False
        data = rs.content
        if _is_image(data):
            _pollution_cache[url] = True
            return True
        if len(data) < 100:
            return False
        _pollution_cache[url] = False
        return False
    except Exception:
        return False


PROVIDER_DISPLAY = {
    'multimovies': 'MultiMovies',
    'nxsha': 'NxSha',
    'watchanimeworld': 'AnimeWorld',
}


def _tmdb_key():
    from config import Config
    return Config.TMDB_API_KEY or ''


def _get_title_from_tmdb(tmdb_id, content_type='movie'):
    key = f'title:{content_type}:{tmdb_id}'
    if key in tmdb_title_cache: return tmdb_title_cache[key]
    try:
        if content_type == 'series':
            r = requests.get(f'https://api.themoviedb.org/3/tv/{tmdb_id}',
                            params={'api_key': _tmdb_key()}, timeout=10)
            r.raise_for_status()
            j = r.json()
            title = j.get('name', '') or j.get('original_name', '')
            if title:
                tmdb_title_cache[key] = title
                return title
            return ''
        r = requests.get(f'https://api.themoviedb.org/3/movie/{tmdb_id}',
                        params={'api_key': _tmdb_key()}, timeout=10)
        r.raise_for_status()
        j = r.json()
        title = j.get('title', '') or j.get('original_title', '')
        tmdb_title_cache[key] = title
        return title
    except:
        return ''


def _search_providers_for_title(title, enabled_providers):
    """Search anime sites by title, return list of (provider_name, slug)"""
    results = []
    for pname in enabled_providers:
        provider = ALL_PROVIDERS.get(pname)
        if not provider: continue
        try:
            items = provider.search_anime(title)
            for item in items:
                results.append((pname, item['slug']))
                break
        except: pass
    return results


def _quality_from_name(name):
    name_lower = name.lower()
    if '2160' in name_lower or '4k' in name_lower: return '4K'
    if '1080' in name_lower: return '1080p'
    if '720' in name_lower: return '720p'
    if '480' in name_lower: return '480p'
    if '360' in name_lower: return '360p'
    return ''


def _referer_for_url(url):
    """Return the correct Referer header for a stream URL"""
    if 'zephyrix' in url or 'zephyrflick' in url:
        return 'https://play.zephyrix.top/'
    if 'itsnitrox' in url or 'nxsha' in url:
        return 'https://nxsha.space/'
    if 'workers.dev' in url and ('streamflix' in url or 'stream.streamflix' in url):
        return 'https://nxsha.space/'
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f'{parsed.scheme}://{parsed.hostname}/'


def _make_title(provider_name, player_key, extra='', label=''):
    site = PROVIDER_DISPLAY.get(provider_name, provider_name)
    player = label or PLAYER_NAMES.get(player_key, player_key)
    parts = [site, player]
    if extra:
        parts.append(extra)
    return ' / '.join(parts)


@stream_bp.route('/stream/<content_type>/<content_id>.json')
@stream_bp.route('/<lang>/stream/<content_type>/<content_id>.json')
@stream_bp.route('/<config_data>/stream/<content_type>/<content_id>.json')
@stream_bp.route('/<config_data>/<lang>/stream/<content_type>/<content_id>.json')
def addon_stream(content_type, content_id, lang=None, config_data=None):
    content_id = urllib.parse.unquote(content_id)
    config = parse_config(config_data or '')
    enabled_providers = get_provider_from_config(config)
    set_twopeckle_config(config)

    parts = content_id.split(':')
    season, episode = 1, 1

    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        season = int(parts[-2])
        episode = int(parts[-1])
        base_id_parts = parts[:-2]
    else:
        base_id_parts = parts

    base_id = ':'.join(base_id_parts)

    tmdb_id = None
    if base_id.startswith('tmdb:'):
        tmdb_id = base_id.replace('tmdb:', '')
    elif base_id.startswith('hd:tmdb:'):
        tmdb_id = base_id.replace('hd:tmdb:', '')
    elif base_id.startswith('tt'):
        try:
            r = requests.get('https://api.themoviedb.org/3/find/' + base_id,
                            params={'api_key': _tmdb_key(), 'external_source': 'imdb_id'}, timeout=10)
            data = r.json()
            results = data.get('tv_results', []) or data.get('movie_results', [])
            if results:
                tmdb_id = str(results[0]['id'])
        except: pass
    elif base_id.isdigit():
        # Bare numeric TMDB id (some clients strip the catalog prefix).
        tmdb_id = base_id

    if not tmdb_id:
        return respond_with({'streams': []})

    title = _get_title_from_tmdb(tmdb_id, content_type)
    if not title:
        return respond_with({'streams': []})

    provider_slugs = _search_providers_for_title(title, enabled_providers)
    if not provider_slugs:
        return respond_with({'streams': []})

    # Collect streams from providers — keep provider info
    raw_streams = []
    for pname, slug in provider_slugs[:5]:
        provider = ALL_PROVIDERS.get(pname)
        if not provider: continue
        try:
            kwargs = {}
            if 'media_type' in inspect.signature(provider.get_episode_streams).parameters:
                kwargs['media_type'] = content_type
            data = provider.get_episode_streams(slug, season, episode, **kwargs)
            for sd in data.get('streams', []):
                sd['_provider'] = pname
                raw_streams.append(sd)
        except Exception as e:
            print(f'[stream] provider {pname}: {e}')

    # Resolve all streams (parallel — sequential resolve is what makes
    # Stremio time out on first open)
    from concurrent.futures import ThreadPoolExecutor

    def _resolve_one(sd):
        try:
            return sd, resolve_stream(sd)
        except Exception as e:
            print(f'[stream] resolve error: {e}')
            return sd, []

    with ThreadPoolExecutor(max_workers=8) as ex:
        pairs = list(ex.map(_resolve_one, raw_streams))

    # Flatten (ordered) then pollution-check in parallel
    flat = []
    for sd, resolved_list in pairs:
        pname = sd.get('_provider', 'unknown')
        player_key = sd.get('player', 'generic_embed')
        for resolved in resolved_list:
            flat.append((sd, pname, player_key, resolved))

    def _build(item):
        sd, pname, player_key, resolved = item
        url = resolved.get('url', '')
        if not url:
            return None

        # Correct Referer for header-sensitive file servers, derived from
        # the provider's sub-host page instead of the file-server IP.
        if player_key in ('rpmshare', 'rpmstream', 'streamp2p', 'upnshare', 'streamhg'):
            _pp = urllib.parse.urlparse(sd.get('url') or '')
            if _pp.scheme and _pp.hostname:
                referer = f'{_pp.scheme}://{_pp.hostname}/'
            else:
                referer = _referer_for_url(url)
        else:
            referer = _referer_for_url(url)

        # Filter non-playable / ad-polluted / IP-blocked m3u8 streams.
        if '.m3u8' in url or 'm3u8' in url:
            if _m3u8_is_polluted(url, referer):
                print(f'[stream] filtered polluted/blocked: {url[:80]}')
                return None

        quality = _quality_from_name(sd.get('name') or '') or _quality_from_name(url)
        display_title = _make_title(pname, player_key, quality, sd.get('name') or '')

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
            'Referer': referer,
        }

        # Always serve direct CDN URLs (never via the addon proxy) so play and
        # seek go straight to the file server. Stremio forwards proxyHeaders.

        stream_obj = {
            'title': display_title,
            'name': display_title,
            'url': url,
            'behaviorHints': {
                'notWebReady': False,
                'bingeGroup': f'multianima-{pname}',
                'proxyHeaders': {
                    'request': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
                        'Referer': referer,
                    }
                }
            },
        }
        if resolved.get('subtitles'):
            stream_obj['subtitles'] = resolved['subtitles']
        return (url, stream_obj)

    with ThreadPoolExecutor(max_workers=8) as ex:
        built = list(ex.map(_build, flat))

    final = []
    seen = set()
    for item in built:
        if not item:
            continue
        url, stream_obj = item
        if url in seen:
            continue
        seen.add(url)
        final.append(stream_obj)

    print(f'[stream] {content_id} => {len(final)} streams')
    return respond_with({'streams': final})
