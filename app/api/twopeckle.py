"""
2Peckle movie provider (Showbox discovery + FebBox CDN signed URLs).

Replicates PenguPlay's 2peckle source exactly. Fully self-contained — no Pengu
backend needed. Reversed from live traffic:

  1. Showbox API (mbpapi.shegu.net, Search5) -> movie id
  2. showbox.media/index/share_link?id=<mid>&type=1  (public) -> share key
  3. febbox.com/file/file_share_list?share_key=...    (public) -> file fids
4. febbox.com/file/file_download (ui cookie) -> data[0].quality_list with
      the ORG original + direct-MP4 transcode ladder (signed URLs, is_265,
      exact file_size), merged with febbox.com/console/video_quality_list
      which adds the adaptive HLS ladder (hls.shegu.net, 360p-4K).

Serves every share file at all qualities: originals, direct-MP4 transcodes
and HLS playlists, 4K included. URLs are signed (~4h TTL), Range supported.

Auth: the FebBox `ui` cookie (a long-lived JWT, ~1 year). Provide it either
via the addon config field `febbox_ui` or the FEBBOX_UI environment variable.
"""
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
import base64

import requests
from cachetools import TTLCache, cached
from Crypto.Cipher import DES3

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36')
TIMEOUT = 25

FEBBOX = 'https://www.febbox.com'
SHOWBOX = 'https://www.showbox.media'

# --- FebBox Open Platform (Pengu's cookie-free signing path) ---
# client_id/client_secret from https://www.febbox.com/open/main (one-time, free).
# Signs download URLs with a Bearer token — no user cookie, no per-user quota;
# the resulting signed CDN URL is anonymous + ~4h TTL, so one signing call
# serves every viewer in the window (this is what "removes the limits" means).
OPENAPI = 'https://api.febbox.com'
_openapi_token = {'token': '', 'exp': 0.0}
_openapi_lock = threading.Lock()


def _openapi_creds():
    cid = (os.environ.get('FEBBOX_CLIENT_ID', '')
           or os.environ.get('FEBBOX_APP_ID', ''))
    csec = (os.environ.get('FEBBOX_CLIENT_SECRET', '')
            or os.environ.get('FEBBOX_APP_SECRET', ''))
    return cid.strip(), csec.strip()


def _openapi_token():
    cid, csec = _openapi_creds()
    if not cid or not csec:
        return ''
    with _openapi_lock:
        if _openapi_token['token'] and time.time() < _openapi_token['exp'] - 120:
            return _openapi_token['token']
        try:
            r = requests.post(f'{OPENAPI}/oauth/token',
                              data={'client_id': cid, 'client_secret': csec,
                                    'grant_type': 'client_credentials'},
                              timeout=15, verify=False)
            d = r.json()
            if d.get('code') != 1:
                print(f'[2peckle] openapi token failed: {d.get("msg")}')
                return ''
            data = d.get('data') or {}
            _openapi_token['token'] = data.get('access_token', '')
            _openapi_token['exp'] = time.time() + int(data.get('expires_in') or 3600)
            return _openapi_token['token']
        except Exception as e:
            print(f'[2peckle] openapi token error: {e}')
            return ''


def _openapi_variants(fid):
    """Signed CDN URL(s) for a fid via the Open Platform API (cookie-free)."""
    token = _openapi_token()
    if not token:
        return None
    try:
        r = requests.post(f'{OPENAPI}/oauth',
                          data={'module': 'file_get_download_url', 'fids[]': fid},
                          headers={'Authorization': f'Bearer {token}'},
                          timeout=20, verify=False)
        d = r.json()
        if d.get('code') != 1:
            print(f'[2peckle] openapi download_url fid={fid}: {d.get("msg")}')
            return None
        data = d.get('data') or []
        if isinstance(data, dict):
            data = [data]
        variants = []
        for e in data:
            url = e.get('url') or e.get('download_url')
            if not url:
                continue
            q = _parse_quality((e.get('file_name') or '') + ' ' + url)
            variants.append({'url': url, 'quality': q, 'codec': '',
                             'size': e.get('file_size') or 0,
                             'is_hls': 'hls.' in url or '.m3u8' in url})
        return variants or None
    except Exception as e:
        print(f'[2peckle] openapi error fid={fid}: {e}')
        return None

# --- Showbox API client (mbpapi.shegu.net, triple-DES encrypted) ---
_SB_BASE = 'https://mbpapi.shegu.net/api/api_client/index/'
_SB_APP_KEY = 'moviebox'
_SB_KEY = b'123d6cedf626dy54233aa1w6'
_SB_IV = b'wEiphTn!'
_SB_DEFAULTS = {
    'CHILD_MODE': '0', 'APP_VERSION': '11.5', 'LANG': 'en',
    'PLATFORM': 'android', 'CHANNEL': 'Website', 'APPID': '27',
    'VERSION': '129', 'MEDIUM': 'Website',
}


def _sb_encrypt(text):
    cipher = DES3.new(_SB_KEY, DES3.MODE_CBC, _SB_IV)
    raw = text.encode('utf-8')
    pad = 8 - len(raw) % 8
    raw += bytes([pad]) * pad
    return base64.b64encode(cipher.encrypt(raw)).decode()


def _sb_md5(s):
    if isinstance(s, str):
        s = s.encode()
    return hashlib.md5(s).hexdigest()


def _showbox_request(module, params=None, timeout=TIMEOUT):
    data = dict(_SB_DEFAULTS)
    data['expired_date'] = int(time.time()) + 12 * 3600
    data['module'] = module
    data.update(params or {})
    enc = _sb_encrypt(json.dumps(data, separators=(',', ':')))
    app_key = _sb_md5(_SB_APP_KEY)
    verify = _sb_md5(app_key + '123d6cedf626dy54233aa1w6' + enc)
    body = json.dumps({'app_key': app_key, 'verify': verify, 'encrypt_data': enc})
    form = {
        'data': base64.b64encode(body.encode()).decode(),
        'appid': _SB_DEFAULTS['APPID'],
        'platform': _SB_DEFAULTS['PLATFORM'],
        'version': _SB_DEFAULTS['VERSION'],
        'medium': _SB_DEFAULTS['MEDIUM'],
    }
    h = {'Platform': 'android', 'Content-Type': 'application/x-www-form-urlencoded',
         'User-Agent': 'okhttp/3.2.0'}
    form_str = '&'.join(f'{k}={v}' for k, v in form.items())
    import secrets
    return requests.post(_SB_BASE, data=form_str + '&token' + secrets.token_hex(16),
                         headers=h, timeout=timeout, verify=False)

# Pipeline results (signed URLs valid ~4h) -> cache ~3.5h.
streams_cache = TTLCache(maxsize=256, ttl=3.5 * 3600)
search_cache = TTLCache(maxsize=512, ttl=6 * 3600)
share_cache = TTLCache(maxsize=1024, ttl=6 * 3600)
url_cache = TTLCache(maxsize=2048, ttl=3.5 * 3600)

# Per-(share_key, fid) signed-variant cache. KEY2 expiry is read from the
# signed URLs themselves, so one signing round serves all viewers for the
# ~4h window instead of one API round per stream request.
_SIGN_CACHE = {}
_SIGN_LOCK = threading.Lock()
_SIGN_MARGIN = 900


def _key2_expiry(url):
    m = re.search(r'[?&]KEY2=(\d+)', url or '')
    return int(m.group(1)) if m else 0

# Set per-request by the stream route (config carries the ui cookie).
_active_config = {}


def set_config(config):
    _active_config.clear()
    _active_config.update(config or {})


def _ui_cookie():
    ui = _active_config.get('febbox_ui') or os.environ.get('FEBBOX_UI', '')
    if not ui:
        return ''
    ci = _active_config.get('febbox_ci') or os.environ.get('FEBBOX_CI', '')
    parts = [f'ci={ci}', f'ui={ui}'] if ci else [f'ui={ui}']
    return '; '.join(p for p in parts)


def _headers(referer=None):
    h = {'User-Agent': UA, 'Accept': 'application/json, text/javascript, */*; q=0.01'}
    if referer:
        h['Referer'] = referer
        h['X-Requested-With'] = 'XMLHttpRequest'
    return h


def _get(url, referer=None, cookie=None, timeout=TIMEOUT, tries=3):
    h = _headers(referer)
    if cookie:
        h['Cookie'] = cookie
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=h, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
            last = f'status {r.status_code}'
        except Exception as e:
            last = str(e)[:100]
        time.sleep(1 + i)
    raise RuntimeError(f'GET {url[:80]} failed: {last}')


def _post(url, data, referer, cookie=None, timeout=TIMEOUT, tries=3):
    h = _headers(referer)
    if cookie:
        h['Cookie'] = cookie
    last = None
    for i in range(tries):
        try:
            r = requests.post(url, headers=h, data=data,
                              timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
            last = f'status {r.status_code}'
        except Exception as e:
            last = str(e)[:100]
        time.sleep(1 + i)
    raise RuntimeError(f'POST {url[:80]} failed: {last}')


def _norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def _best_match(hits, query):
    q = _norm(query)
    best = None
    best_score = -1
    for h in hits:
        if h.get('box_type') != 1:
            continue
        title = h.get('title') or ''
        t = _norm(title)
        if t == q:
            score = 100
        elif t.startswith(q) or q.startswith(t):
            score = 60
        elif q in t or t in q:
            score = 40
        else:
            score = 0
        if score > best_score:
            best_score = score
            best = h
    return best


@cached(search_cache)
def _showbox_search(title):
    try:
        r = _showbox_request('Search5', {'page': 1, 'type': 'all', 'keyword': title,
                                         'pagelimit': 20})
        d = r.json()
        if d.get('code') != 1:
            return []
        data = d.get('data', {})
        if isinstance(data, dict):
            data = data.get('list', data)
        return data or []
    except Exception as e:
        print(f'[2peckle] search error: {e}')
        return []


@cached(share_cache)
def _share_key(movie_id):
    # Try type=1 (movie) then type=2 (different FebBox share — Pengu: "not just showbox")
    last_err = None
    for t in ('1', '2'):
        try:
            r = _get(f'{SHOWBOX}/index/share_link?id={movie_id}&type={t}')
            d = r.json()
            link = (d.get('data') or {}).get('link') or ''
            if link:
                return link.rsplit('/', 1)[-1]
            last_err = f'type {t} empty'
        except Exception as e:
            last_err = str(e)[:80]
    raise RuntimeError(f'share_link empty for {movie_id}: {last_err}')


@cached(share_cache)
def _share_files(share_key):
    url = (f'{FEBBOX}/file/file_share_list?share_key={share_key}'
           f'&pwd=&parent_id=0&is_html=0')
    r = _get(url, referer=f'{FEBBOX}/share/{share_key}')
    d = r.json()
    if d.get('code') != 1:
        raise RuntimeError(f'file_share_list failed: {d.get("msg")}')
    return d.get('data', {}).get('file_list', []) or []


def _parse_quality(name):
    n = name.lower()
    if '2160' in n or '4k' in n:
        return 2160
    if '1080' in n:
        return 1080
    if '720' in n:
        return 720
    if '480' in n:
        return 480
    if '360' in n:
        return 360
    return 0


def _quality_label_from_int(q):
    return {2160: '4K', 1080: '1080p', 720: '720p', 480: '480p', 360: '360p'}.get(q, 'HD')


def _format_size(b):
    try:
        b = int(b or 0)
    except (TypeError, ValueError):
        return ''
    if b <= 0:
        return ''
    if b >= 1 << 30:
        return f'{b / (1 << 30):.2f} GB'
    if b >= 1 << 20:
        return f'{b / (1 << 20):.2f} MB'
    return f'{b / (1 << 10):.0f} KB'


def _parse_vq_html(html):
    """Parse video_quality_list html into variant dicts.

    Direct MP4 transcodes live under /vip/p1/movie_mp4_h264|h265/...; the
    adaptive HLS ladder (360p-4K) lives on hls.shegu.net with per-variant
    signed playlists. Quality and size come from the label text (the HLS URLs
    carry no resolution).
    """
    variants = []
    for m in re.finditer(r'<div class="file_quality"[^>]*data-url="([^"]+)"[^>]*>(.*?)</div>',
                         html, re.S):
        url = m.group(1).replace('\\/', '/')
        label = re.sub(r'<[^>]+>', ' ', m.group(2))
        label = re.sub(r'\s+', ' ', label).strip()
        n = url.lower()
        is_hls = 'hls.' in n or '.m3u8' in n
        q = _parse_quality(label) or _parse_quality(url)
        codec = ('HLS' if is_hls
                 else ('H265' if ('h265' in n or 'hevc' in n)
                       else ('H264' if 'h264' in n else '')))
        size = 0
        sizes = re.findall(r'([\d.]+)\s*(GB|MB)\b', label, re.I)
        if sizes:
            num = float(sizes[-1][0])
            unit = sizes[-1][1].upper()
            size = int(round(num * ((1 << 30) if unit == 'GB' else (1 << 20))))
        variants.append({'url': url, 'quality': q, 'codec': codec,
                         'size': size, 'is_hls': is_hls})
    return variants


def _file_variants(share_key, fid, cookie):
    """Every playable variant of a file.

    Merges the originals + direct-MP4 transcode ladder (from
    /file/file_download's quality_list) with the adaptive HLS ladder (from
    /console/video_quality_list). Dedupes by URL.

    Signed URLs are anonymous-playable and stay valid ~4h (KEY2 = issue +
    14400s), so results are cached until shortly before expiry: one signing
    call serves every viewer in the window and FebBox API volume stays
    near-zero regardless of user count.
    """
    ckey = (share_key, fid)
    now = time.time()
    with _SIGN_LOCK:
        hit = _SIGN_CACHE.get(ckey)
        if hit and hit[0] > now:
            return hit[1]

    # Cookie-free path: FebBox Open Platform (app_id/app_secret in env).
    oa = _openapi_variants(fid)
    if oa:
        exps = [_key2_expiry(v.get('url', '')) for v in oa]
        exp = min((e for e in exps if e), default=0)
        expires = (exp - _SIGN_MARGIN) if exp > now + _SIGN_MARGIN else now + 3 * 3600
        with _SIGN_LOCK:
            _SIGN_CACHE[ckey] = (expires, oa)
        return oa

    variants = []
    seen = set()
    try:
        r = _post(f'{FEBBOX}/file/file_download',
                  {'share_key': share_key, 'fid': fid},
                  referer=f'{FEBBOX}/share/{share_key}', cookie=cookie)
        d = r.json()
        if d.get('code') == 1:
            data = d.get('data') or []
            if data:
                fname = data[0].get('file_name') or ''
                for e in data[0].get('quality_list') or []:
                    url = e.get('download_url')
                    if not url or url.split('?', 1)[0] in seen:
                        continue
                    seen.add(url.split('?', 1)[0])
                    n = url.lower()
                    qual = (e.get('quality') or '').strip().upper()
                    q = {'4K': 2160, '1080P': 1080, '720P': 720,
                         '480P': 480, '360P': 360}.get(qual, 0)
                    if not q:
                        if qual == 'ORG':
                            q = _parse_quality(fname)
                        else:
                            q = _parse_quality(url.split('?', 1)[0])
                    codec = '' if qual == 'ORG' else ('H265' if e.get('is_265') else 'H264')
                    variants.append({'url': url, 'quality': q, 'codec': codec,
                                     'size': e.get('file_size') or 0,
                                     'is_hls': 'hls.' in n or '.m3u8' in n})
    except Exception as e:
        print(f'[2peckle] file_download error fid={fid}: {e}')
    try:
        r = _get(f'{FEBBOX}/console/video_quality_list?fid={fid}',
                 referer=f'{FEBBOX}/share/{share_key}', cookie=cookie)
        for v in _parse_vq_html(r.json().get('html', '')):
            if v['url'].split('?', 1)[0] in seen:
                continue
            variants.append(v)
    except Exception as e:
        print(f'[2peckle] video_quality_list error fid={fid}: {e}')

    exps = [_key2_expiry(v.get('url', '')) for v in variants]
    exp = min((e for e in exps if e), default=0)
    expires = (exp - _SIGN_MARGIN) if exp > now + _SIGN_MARGIN else now + 1800
    with _SIGN_LOCK:
        if len(_SIGN_CACHE) > 4096:
            for k in [k for k, v in _SIGN_CACHE.items() if v[0] <= now][:512]:
                _SIGN_CACHE.pop(k, None)
        _SIGN_CACHE[ckey] = (expires, variants)
    return variants


class TwoPeckleProvider:
    NAME = '2peckle'
    uses_config = True

    def search_anime(self, query):
        """Showbox Search5 -> best movie match, slug = showbox movie id."""
        hits = _showbox_search(query)
        hit = _best_match(hits, query)
        if not hit:
            return []
        slug = str(hit.get('id') or '')
        if not slug:
            return []
        return [{'title': hit.get('title') or query, 'slug': slug,
                 'type': 'movie', 'provider': self.NAME}]

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        """Movies requested as s1e1 -> signed FebBox MP4/MKV + HLS URLs.

        Serves every share file's originals and direct-MP4 transcode ladder
        plus the adaptive HLS ladder, at all qualities including 4K.
        """
        if season > 1 or episode > 1:
            return {'streams': []}
        movie_id = str(slug or '')
        if not movie_id:
            return {'streams': []}
        try:
            # Pengu: "yup i bypass the need for a cookie" — try anon first, fall back to server ui
            # and merge both FebBox shares (showbox type1 + different share type2)
            cookies_to_try = []
            ui = _ui_cookie()
            if ui:
                cookies_to_try.append(ui)
            cookies_to_try.append('')  # anon bypass attempt (different share may allow it)
            tried_keys = set()
            all_files = []
            for t in ('1', '2'):
                try:
                    rk = _get(f'{SHOWBOX}/index/share_link?id={movie_id}&type={t}').json()
                    link = (rk.get('data') or {}).get('link') or ''
                    if not link:
                        continue
                    k = link.rsplit('/', 1)[-1]
                    if k in tried_keys:
                        continue
                    tried_keys.add(k)
                    fl = _share_files(k)
                    # tag files with their share key for later signing
                    for f in fl:
                        f['_share_key'] = k
                    all_files.extend(fl)
                except Exception as e:
                    print(f'[2peckle] share type {t} failed: {e}')
            if not all_files:
                # fallback to single-key path for backward compat
                try:
                    key = _share_key(movie_id)
                    all_files = _share_files(key)
                    for f in all_files:
                        f['_share_key'] = key
                except Exception as e:
                    print(f'[2peckle] pipeline error for {movie_id}: {e}')
                    return {'streams': []}
            if not all_files:
                return {'streams': []}
            # Try signing with available cookies (anon first = Pengu's "bypass", then server ui)
            # _SIGN_CACHE is keyed on (share_key, fid) so anon vs ui are cached separately
            streams = []
            seen = set()
            for cookie in cookies_to_try:
                if streams:
                    break
                for f in all_files:
                    fid = f.get('fid')
                    fname = f.get('file_name') or f.get('name') or ''
                    if not fid:
                        continue
                    sk = f.get('_share_key') or ''
                    for v in _file_variants(sk, fid, cookie):
                        url = v['url']
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        quality = _quality_label_from_int(v['quality'])
                        name = f'2Peckle {quality}'
                        if v['codec']:
                            name += f' {v["codec"]}'
                        size = _format_size(v['size']) or f.get('file_size') or ''
                        if size:
                            name += f' · {size}'
                        streams.append({'player': 'direct_m3u8', 'url': url, 'name': name})
                if len(streams) >= 40:
                    break
        except Exception as e:
            print(f'[2peckle] pipeline error for {movie_id}: {e}')
            return {'streams': []}

        if not streams:
            return {'streams': []}
        return {'streams': streams}

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return {'title': f'2Peckle {slug}', 'slug': slug, 'type': 'movie',
                'provider': self.NAME}

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': 1, 'title': slug, 'slug': slug}]