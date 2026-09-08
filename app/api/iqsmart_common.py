"""
Shared iqsmartgames (GDMirrorBot / embedhelper2) stream resolution flow.

Used by AniMoye and MultiMovies providers. Flow per embed:
  embed page (prime) -> myseriesapi (fileslugs) -> pro.iqsmartgames.com
  evid/<fileslug> -> embedhelper2.php (sources + mresult) -> sub-host URLs
  -> classified into player keys handled by app.players modules.
"""
import re
import json
import time
import base64
import requests
from cachetools import TTLCache

STREAMS_URL = 'https://streams.iqsmartgames.com'
PLAYER_URL = 'https://pro.iqsmartgames.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 15

session = requests.Session()
session.headers.update({'User-Agent': UA})

RETRYABLE = (403, 429, 500, 502, 503, 504, 522, 524)

# Circuit breaker: if the iqsmart origin is down (522/timeouts), fail fast.
_circuit = {'open_until': 0, 'failures': 0}
_health_cache = {'ts': 0, 'ok': True}
CIRCUIT_MAX_FAILURES = 3
CIRCUIT_COOLDOWN = 300  # seconds

def _circuit_open():
    return time.time() < _circuit['open_until']

def _circuit_hit():
    _circuit['failures'] += 1
    if _circuit['failures'] >= CIRCUIT_MAX_FAILURES:
        _circuit['open_until'] = time.time() + CIRCUIT_COOLDOWN
        print(f'[iqsmart] circuit breaker opened for {CIRCUIT_COOLDOWN}s')

def _circuit_ok():
    if _circuit_open():
        return False
    _circuit['failures'] = 0
    return True


def _origin_healthy():
    """Fast single-shot probe (no retries) so we fail immediately if the
    iqsmart origin is down instead of burning retries in resolve_tv."""
    if _circuit_open():
        return False
    now = time.time()
    if now - _health_cache['ts'] < 10:
        return _health_cache['ok']
    try:
        r = session.get(f'{STREAMS_URL}/', timeout=6, verify=False)
        ok = r.status_code == 200
    except Exception:
        ok = False
    _health_cache['ts'] = now
    _health_cache['ok'] = ok
    return ok


def _get_retry(url, headers=None, params=None, max_retries=2, timeout=15):
    """GET with backoff retry on timeout/5xx (iqsmart origin is flaky)."""
    last = None
    for attempt in range(max_retries):
        try:
            r = session.get(url, headers=headers, params=params, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
            if r.status_code in RETRYABLE:
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


def _post_retry(url, data=None, headers=None, max_retries=2, timeout=15):
    """POST with backoff retry on timeout/5xx."""
    last = None
    for attempt in range(max_retries):
        try:
            r = session.post(url, data=data, headers=headers, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
            if r.status_code in RETRYABLE:
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

# URL host fragment -> package player key (must have a handler module).
HOST_PLAYER = (
    ('abyssplayer', 'abyss'),
    ('abysssplayer', 'abyss'),
    ('krakenfiles', 'krakenfiles'),
    ('earnvids', 'earnvids'),
    ('strp2p', 'streamp2p'),
    ('p2pplay', 'streamp2p'),
    ('upns', 'upnshare'),
    ('uns.bio', 'upnshare'),
    ('rpmstream', 'rpmshare'),
    ('rpmplay', 'rpmshare'),
    ('rpmhub', 'rpmshare'),
    ('hanerix', 'streamhg'),
    ('smoothpre', 'streamhg'),
    ('vidhide', 'streamhg'),
    ('filemoon', 'filemoon'),
    ('byse', 'filemoon'),
    ('dood', 'dood'),
    ('streamtape', 'streamtape'),
    ('vidmoly', 'vidmoly'),
)


def resolve_embed(embed_url):
    """Resolve an iqsmartgames embed URL like
    https://streams.iqsmartgames.com/embed/tv/{tmdb}/{s}/{e}?key={key}
    or https://streams.iqsmartgames.com/embed/movie/{imdb}?key={key}
    into a list of stream dicts."""
    m = re.search(r'/embed/tv/(\d+)/(\d+)/(\d+)\?key=([A-Za-z0-9_-]+)', embed_url)
    if m:
        tmdb_id, season, episode, key = m.groups()
        return resolve_tv(tmdb_id, int(season), int(episode), key)
    m = re.search(r'/embed/movie/([A-Za-z0-9]+)\?key=([A-Za-z0-9_-]+)', embed_url)
    if m:
        video_id, key = m.groups()
        return resolve_movie(video_id, key)
    return []


def resolve_movie(video_id, my_key):
    """Resolve a movie imdb/tmdb id + key combo into stream dicts
    via mymovieapi -> fileslugs -> embedhelper2 sub-hosts."""
    id_param = 'imdbid' if video_id.startswith('tt') else 'tmdbid'
    embed_url = f'{STREAMS_URL}/embed/movie/{video_id}?key={my_key}'
    try:
        session.get(f'{STREAMS_URL}/', timeout=TIMEOUT, verify=False)
        session.get(embed_url, timeout=TIMEOUT, verify=False)
    except Exception:
        pass
    headers = {
        'User-Agent': UA,
        'Referer': embed_url,
        'Origin': STREAMS_URL,
        'X-Requested-With': 'XMLHttpRequest',
    }
    try:
        r = _get_retry(f'{STREAMS_URL}/mymovieapi',
                       params={id_param: video_id, 'key': my_key},
                       headers=headers)
        if r is None or r.status_code != 200:
            return []
        data = (r.json() or {}).get('data') or []
    except Exception:
        return []
    fileslugs = [d.get('fileslug') for d in data if isinstance(d, dict) and d.get('fileslug')]
    streams = []
    seen = set()
    for fileslug in fileslugs:
        for sd in _resolve_fileslug(fileslug):
            url = sd.get('url', '')
            if not url or url in seen:
                continue
            seen.add(url)
            streams.append(sd)
    return streams


def resolve_tv(tmdb_id, season, episode, my_key):
    """Resolve a tmdb/season/episode/key combo into stream dicts."""
    if not _circuit_ok():
        print('[iqsmart] circuit open, skipping resolution')
        return []
    if not _origin_healthy():
        _circuit_hit()
        print('[iqsmart] origin unhealthy, opening circuit')
        return []
    try:
        fileslugs = _get_fileslugs(tmdb_id, season, episode, my_key)
    except Exception:
        return []
    if not fileslugs:
        # Origin likely down -> open circuit
        _circuit_hit()
    streams = []
    seen = set()
    for fileslug in fileslugs:
        for sd in _resolve_fileslug(fileslug):
            url = sd.get('url', '')
            if not url or url in seen:
                continue
            seen.add(url)
            streams.append(sd)
    return streams


def _get_fileslugs(tmdb_id, season, episode, my_key):
    # Prime the streams domain so myseriesapi isn't challenged ("Invalid dg")
    embed_url = f'{STREAMS_URL}/embed/tv/{tmdb_id}/{season}/{episode}?key={my_key}'
    try:
        session.get(f'{STREAMS_URL}/', timeout=TIMEOUT, verify=False)
        session.get(embed_url, timeout=TIMEOUT, verify=False)
    except Exception:
        pass
    headers = {
        'User-Agent': UA,
        'Referer': embed_url,
        'Origin': STREAMS_URL,
        'X-Requested-With': 'XMLHttpRequest',
    }
    r = _get_retry(f'{STREAMS_URL}/myseriesapi',
                   params={'tmdbid': tmdb_id, 'season': season,
                           'epname': episode, 'key': my_key},
                   headers=headers)
    if r is None or r.status_code != 200:
        return []
    try:
        data = (r.json() or {}).get('data') or []
    except Exception:
        return []
    return [d.get('fileslug') for d in data if isinstance(d, dict) and d.get('fileslug')]


def _resolve_fileslug(fileslug):
    evid_url = f'{PLAYER_URL}/evid/{fileslug}'
    try:
        session.get(evid_url, timeout=TIMEOUT, verify=False)
    except Exception:
        pass
    try:
        r = _post_retry(f'{PLAYER_URL}/embedhelper2.php',
                        data={'sid': fileslug, 'UserFavSite': '', 'currentDomain': '[]'},
                        headers={'User-Agent': UA, 'Origin': PLAYER_URL,
                                 'Referer': evid_url,
                                 'Content-Type': 'application/x-www-form-urlencoded'})
        if r is None or r.status_code != 200:
            return []
        j = r.json()
        mresult = _decode_mresult(j.get('mresult'))
        sources = j.get('sources', {})
        if isinstance(sources, list):
            sources = {x.get('key', str(i)): x for i, x in enumerate(sources) if isinstance(x, dict)}
        if not isinstance(sources, dict):
            return []
        out = []
        for key, cfg in sources.items():
            if not isinstance(cfg, dict):
                continue
            site_url = cfg.get('siteUrl', '')
            stream_id = mresult.get(key, '')
            if not site_url or not stream_id:
                continue
            url = site_url + stream_id + (cfg.get('embed_suffix') or '')
            player = _classify_host(url)
            if not player:
                continue
            out.append({
                'player': player,
                'url': url,
                'name': cfg.get('friendlyName') or key,
            })
        return out
    except Exception:
        return []


def _decode_mresult(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        decoded = base64.b64decode(raw).decode('utf-8')
        return json.loads(decoded)
    except Exception:
        try:
            return json.loads(raw)
        except Exception:
            return {}


def _classify_host(url):
    u = url.lower()
    for frag, player in HOST_PLAYER:
        if frag in u:
            return player
    return ''
