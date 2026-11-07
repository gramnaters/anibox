import urllib.parse, requests, re, time, inspect
from flask import Blueprint, abort, request
from cachetools import TTLCache
from app.api import ALL_PROVIDERS
from app.routes.utils import respond_with, log_error
from app.routes.proxy import _fetch_upstream
from app.players import resolve_stream, PLAYER_NAMES
from app.config_parser import parse_config, get_provider_from_config

stream_bp = Blueprint('stream', __name__)
tmdb_title_cache = TTLCache(maxsize=500, ttl=3600)
# Fully-built stream lists. Provider scraping + embed resolution is slow on
# Render's free CPU (1-3 min), which exceeds client timeouts; caching the
# result makes repeat opens instant and cuts upstream load.
_stream_cache = TTLCache(maxsize=1000, ttl=600)

# Image magic bytes -> a "video" segment that is really an ad image (pollution).
_IMAGE_MAGIC = (b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'RIFF', b'\x00\x00\x00\x0cftypwebp')
_AD_CDN_MARKERS = ('tiktokcdn', 'ibyteimg', 'ad-site')
_IP_BLOCK_MARKERS = ('ip blocked', 'access denied', 'forbidden', 'your ip has been',
                     'rate limit', 'too many requests', 'captcha', 'attention required',
                     'unusual traffic', 'verify you are human')
_pollution_cache = TTLCache(maxsize=2000, ttl=3600)


def _inspect_m3u8(url, referer=''):
    """Verify a master m3u8 -> first variant -> first segment actually returns
    video bytes (not ad images, ad-CDN playlists, HTML/IP-block pages).

    Returns ``(polluted, metadata)`` where metadata carries the playlist's
    resolution, bitrate, duration, codec and audio languages so the stream
    formatter can enrich the Stremio/AIOStreams fields without a second fetch.
    """
    cached = _pollution_cache.get(url)
    if cached is not None:
        if isinstance(cached, tuple):
            return cached
        return cached, {}  # legacy bool entry

    from app.stream_formatter import _merge_meta

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'}
    if referer:
        headers['Referer'] = referer
    elif 'watching.onl' in url:
        headers['Referer'] = 'https://megaplay.buzz/'
    elif 'itsnitrox' in url or 'nxsha' in url:
        headers['Referer'] = 'https://nxsha.space/'

    meta = {'is_hls': True}

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
            return False, meta
        master = r.text
        if _bad(master):
            _pollution_cache[url] = (True, meta)
            return True, meta

        uris = [l.strip() for l in master.splitlines() if l.strip() and not l.startswith('#') and not l.startswith('data:')]
        if not uris:
            return False, meta

        if '#EXT-X-STREAM-INF' in master:
            first = uris[0]
            variant_url = first if first.startswith('http') else url.rsplit('/', 1)[0] + '/' + first
            rv = _fetch_upstream(variant_url, headers, timeout=10)
            if rv is None or rv.status_code != 200:
                return False, meta
            variant = rv.text
        else:
            # A media playlist: the master already lists the segments.
            variant = master
            variant_url = url

        if _bad(variant):
            _pollution_cache[url] = (True, meta)
            return True, meta

        _merge_meta(master, variant, meta)

        # First segment could be directly in variant, or variant is another playlist
        segs = [l.strip() for l in variant.splitlines() if l.strip() and not l.startswith('#') and not l.startswith('data:')]
        if not segs:
            return False, meta
        seg = segs[0]
        seg_url = seg if seg.startswith('http') else variant_url.rsplit('/', 1)[0] + '/' + seg

        path = urllib.parse.urlparse(seg_url).path.lower()
        if path.endswith('.ts'):
            meta.setdefault('container', 'ts')
        elif path.endswith('.m4s') or path.endswith('.mp4'):
            meta.setdefault('container', 'mp4')

        # First segment: only need the first bytes (magic + size check)
        seg_headers = dict(headers)
        seg_headers['Range'] = 'bytes=0-16383'
        rs = _fetch_upstream(seg_url, seg_headers, timeout=12)
        if rs is None or rs.status_code != 200:
            return False, meta
        data = rs.content
        if _is_image(data):
            _pollution_cache[url] = (True, meta)
            return True, meta
        if len(data) < 100:
            return False, meta
        _pollution_cache[url] = (False, meta)
        return False, meta
    except Exception:
        return False, meta


PROVIDER_DISPLAY = {
    'multimovies': 'MultiMovies',
    'nxsha': 'NxSha',
    'watchanimeworld': 'AnimeWorld',
    'toonstream': 'ToonStream',
    'piratexplay': 'PirateXPlay',
    'screenscape': 'ScreenScape',
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


_TITLE_STOPWORDS = {'the', 'a', 'an', 'of', 'and', 'to', 'in', 'on', 'for', 'part'}


def _norm_title(text):
    """Lowercase, drop punctuation/years, collapse whitespace."""
    text = str(text or '').lower()
    text = re.sub(r'\(\s*\d{4}\s*\)|\b(19|20)\d{2}\b', ' ', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return ' '.join(text.split())


def _match_title(query, candidates, content_type=None, season=None):
    """Pick the candidate whose title contains the query phrase.

    Search endpoints return whatever they think is relevant (ToonStream puts
    "LEGO One Piece" first for "One Piece", PirateXPlay invents matches), so a
    plain first-result pick leaks streams for the wrong show. We require the
    query phrase to appear contiguously in the candidate title and prefer the
    tightest match. Returns None when nothing matches.
    """
    q = _norm_title(query)
    if not q:
        return candidates[0] if candidates else None

    best, best_key = None, None
    for item in candidates:
        t = _norm_title(item.get('title', ''))
        if not t:
            continue
        pos = t.find(q)
        if pos < 0:
            # Allow the reverse ("Naruto Shippuden" vs query "Naruto").
            rev = q.find(t)
            if rev < 0:
                continue
            pos = 0
        extra = len(set(t.split()) - set(q.split()) - _TITLE_STOPWORDS)
        itype = item.get('type')
        type_mismatch = 0 if (not content_type or not itype or itype == content_type) else 1
        # Some providers' slugs carry the season ("...-season-5-46260").
        slug = item.get('slug') or ''
        season_in_slug = re.search(r'season-(\d+)-', slug)
        season_rank = 0
        if season_in_slug and season is not None:
            season_rank = 0 if int(season_in_slug.group(1)) == season else 1
        key = (type_mismatch, season_rank, 0 if t == q else 1, pos, extra, len(t))
        if best_key is None or key < best_key:
            best, best_key = item, key
    return best


def _search_providers_for_title(title, enabled_providers, content_type=None, season=None):
    """Search anime sites by title, return list of (provider_name, slug)"""
    results = []
    for pname in enabled_providers:
        provider = ALL_PROVIDERS.get(pname)
        if not provider: continue
        try:
            items = provider.search_anime(title)
            match = _match_title(title, items or [], content_type, season)
            if match and match.get('slug'):
                results.append((pname, match['slug']))
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


# Host substring -> Referer. Order matters (first match wins). These CDNs
# reject their own host as the referer and require the embedder's origin.
_REFERER_MAP = (
    # Abyss player CDN (PirateXPlay abyss/byse/gdmirror sources)
    ('sssrr.org', 'https://abyssplayer.com/'),
    ('zephyrix', 'https://play.zephyrix.top/'),
    ('zephyrflick', 'https://play.zephyrix.top/'),
    ('itsnitrox', 'https://nxsha.space/'),
    ('aurorionacademy', 'https://nxsha.space/'),
    ('hscow.com', 'https://nxsha.space/'),
    ('nxstreamhub', 'https://nxsha.space/'),
    ('streamflix', 'https://screenscape.me/'),
    ('rousav.tech', 'https://m1.multimovies.courses/'),
    ('vidrift', 'https://embed.vidrift.net/'),
    ('vidmmo', 'https://m1.multimovies.courses/'),
    ('vmpx.online', 'https://streamruby.net/'),
    ('sprintcdn', 'https://streamruby.net/'),
    ('owphbf24.com', 'https://streamruby.net/'),
)


# Generic CDN workers (Cloudflare) that gate on the embedder's Origin/Referer.
_PROVIDER_REFERER = {
    'multimovies': 'https://m1.multimovies.courses/',
    'nxsha': 'https://nxsha.space/',
    'screenscape': 'https://screenscape.me/',
    'piratexplay': 'https://piratexplay.cc/',
    'animeworld': 'https://watchanimeworld.com/',
    'toonstream': 'https://toonstream.us/',
}


# Media CDNs that reject browser Origin headers or need per-request headers on
# every sub-playlist/segment. Served through the addon's HLS proxy instead.
#
# NOTE: Abyss (sssrr.org) is deliberately NOT proxied. It serves real video
# with just a Referer — which players already send via proxyHeaders — and only
# 404s when a browser Origin header is present. ExoPlayer (Nuvio) and mpv never
# send Origin, so direct playback works and keeps the (large) MP4 traffic off
# this server. StreamRuby's rotating edges and StreamHG are IP/header bound.
_PROXY_MEDIA_HOSTS = (
    'r66nv9ed.com', 'marketforecasting.cfd',                 # Byse / StreamRuby edge
    'streamruby.net', 'vmnow.online',                        # StreamRuby
    'hanerix.com', 'smoothpre', 'vidhide',                   # StreamHG
    'zephyrix', 'zephyrflick', 'as-cdn',                     # Zephyr / FirePlayer
    'vmpx.online', 'owphbf24.com', 'sprintcdn',              # StreamRuby rotating edges
)


def _referer_for_url(url, provider=None):
    """Return the correct Referer header for a stream URL"""
    # workers.dev proxies reject their own host; use the embedder origin.
    if 'workers.dev' in url and provider in _PROVIDER_REFERER:
        return _PROVIDER_REFERER[provider]
    for needle, referer in _REFERER_MAP:
        if needle in url:
            return referer
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

    cache_key = (content_type, content_id, tuple(sorted(enabled_providers)),
                 str(config.get('formatter_style') or 'rich').lower())
    cached = _stream_cache.get(cache_key)
    if cached is not None:
        print(f'[stream] cache hit {content_id} ({len(cached)} streams)')
        return respond_with({'streams': cached})

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

    provider_slugs = _search_providers_for_title(title, enabled_providers, content_type, season)
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
                referer = _referer_for_url(url, pname)
        else:
            referer = _referer_for_url(url, pname)

        # Filter non-playable / ad-polluted / IP-blocked m3u8 streams.
        style = str(config.get('formatter_style') or 'rich').lower()
        if style not in ('rich', 'aiostreams', 'compact', 'plain'):
            style = 'rich'

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
            'Referer': referer,
        }

        from app.stream_formatter import (
            format_stream, infer_languages, probe_direct,
        )

        meta = {}
        # Zephyr-style masters arrive as .../master.txt, which is still HLS.
        is_hls = 'm3u8' in url or '/cdn/hls/' in url
        if is_hls:
            polluted, meta = _inspect_m3u8(url, referer)
            if polluted:
                print(f'[stream] filtered polluted/blocked: {url[:80]}')
                return None
            meta.setdefault('is_hls', True)
        else:
            meta.update(probe_direct(url, headers))

        hint_quality = _quality_from_name(sd.get('name') or '') or _quality_from_name(url)
        quality = meta.get('quality') or hint_quality
        meta['quality'] = quality
        meta.setdefault('quality_tag', 'WEB-DL')

        languages = infer_languages(sd, pname, meta, url)
        sd_name = (sd.get('name') or '').strip()
        if (not sd_name
                or sd_name.lower() in (pname.lower(), PROVIDER_DISPLAY.get(pname, '').lower())
                or len(sd_name) > 34 or '\u00b7' in sd_name):
            player_label = PLAYER_NAMES.get(player_key, player_key) or player_key
        else:
            player_label = sd_name
        plain_title = _make_title(pname, player_key, quality, sd.get('name') or '')

        formatted = format_stream(
            style=style,
            plain_title=plain_title,
            provider_display=PROVIDER_DISPLAY.get(pname, pname),
            player_label=player_label,
            quality=quality,
            meta=meta,
            languages=languages,
            subtitles=resolved.get('subtitles'),
            title=title,
            content_type=content_type,
            season=season,
            episode=episode,
            source_url=url,
        )

        # These CDNs reject browser Origin headers (Abyss: 404) or need the
        # Referer on every sub-playlist/segment (StreamRuby), which Stremio's
        # streaming server does not forward. Serve them through our HLS proxy.
        if any(h in url for h in _PROXY_MEDIA_HOSTS):
            try:
                from app.routes.proxy import register_proxy_url
                container = meta.get('container') or ''
                if is_hls or container == 'm3u8':
                    kind = 'm3u8'
                else:
                    # Direct file: keep the real container extension so mpv and
                    # ExoPlayer demux it correctly (extensionless MP4 etc.).
                    kind = None
                url = register_proxy_url(url, headers, base_url=_proxy_base,
                                         kind=kind, ext=container or None)
            except Exception as e:
                print(f'[stream] proxy register failed: {e}', flush=True)

        # Other hosts are served directly: Stremio forwards proxyHeaders, and
        # play/seek go straight to the file server.

        hints = dict(formatted.get('behaviorHints') or {})
        hints['notWebReady'] = False
        hints['bingeGroup'] = f'multianima-{pname}-{player_key}'
        hints['proxyHeaders'] = {
            'request': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
                'Referer': referer,
            }
        }

        stream_obj = {
            'title': formatted['title'],
            'name': formatted['name'],
            'url': url,
            'behaviorHints': hints,
        }
        if formatted.get('description'):
            stream_obj['description'] = formatted['description']
        if resolved.get('subtitles'):
            stream_obj['subtitles'] = resolved['subtitles']
        return (url, stream_obj)

    try:
        from app.routes.proxy import addon_base_url
        _proxy_base = addon_base_url()
    except Exception as e:
        print(f'[stream] addon base failed: {e}', flush=True)
        _proxy_base = ''

    with ThreadPoolExecutor(max_workers=8) as ex:
        built = list(ex.map(_build, flat))

    final = []
    seen_urls = set()
    seen_labels = set()
    for item in built:
        if not item:
            continue
        url, stream_obj = item
        if url in seen_urls:
            continue
        # Providers often list the same episode several times from different
        # mirrors (identical provider/player/quality/languages/size). Those
        # streams are indistinguishable in the UI, so keep only the first.
        label = (stream_obj.get('name'), stream_obj.get('title'),
                 stream_obj.get('description'))
        if label in seen_labels:
            continue
        seen_urls.add(url)
        seen_labels.add(label)
        final.append(stream_obj)

    print(f'[stream] {content_id} => {len(final)} streams')
    _stream_cache[cache_key] = final
    return respond_with({'streams': final})
