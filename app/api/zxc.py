"""
ZXCStream provider — ZXC backend -> CF-worker proxied HLS streams.

Flow (reverse-engineered 2026-08 from player.zxcstream.xyz Next.js bundle):
  1. POST /backend/gagoka  {id, mediaType, path=server, season, episode}
       -> {token, ts}
  2. GET  /backend_/sources/<server>?<field-map params + token/ts>
       -> {success, links: [{type, link}], subtitles, meow}
  3. Each `link` is CryptoJS OpenSSL AES-CBC ("Salted__" base64) with a
     fixed passphrase -> plain worker URL (e.g. https://x.berkas001.workers.dev/?data=...)
  4. Worker serves master m3u8; variant/media playlists rewritten to stay
     on the worker; segments are raw MPEG-TS.

Valid servers (probed live): berkas (HLS), icarus (HLS), resshin (HLS).
"""
import base64
import hashlib
import json
import re
import time

import requests
from cachetools import TTLCache, cached

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:  # pragma: no cover
    Cipher = None

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36')
TIMEOUT = 20
ZXC_BASE = 'https://player.zxcstream.xyz'
SERVERS = ['berkas', 'icarus', 'resshin']
LINK_AES_PASS = ('7f4c9e2a81d63b05c4f7a9e8126d3b50e1a8c7f23d9465ab0'
                 'c6e9f1d4a7b832c')
# FIELD_MAP from bundle chunk module 55790 (rotated 2026-08)
FM = {
    'id': 'a7f39c821d604e5b9c71438f36e1547b',
    'mediaType': 'c285f914ab306d281e947a35632e816b',
    'path': '6b491e7253ad80f14d392e7561a9384c',
    'season': 'd8427b59ce306184a2f957c3613e85b',
    'episode': '91c6e4a728bd503d1f785c92346b713d',
    'ts': '61d9a5274c8e3b29af750d6384c291e6',
    'token': 'c492f7a183d6502b91e7436c538a716d',
    'title': '5e28c9147a306d531e829f3674b392a1',
    'year': 'b731e6c94f082a1639d725f8341c306e',
    'date': 'e164932c508f216ad739e5814b3027',
    'imdbId': 'f35a8c19d6740b3265e871c4933a725f',
}

_search_cache = TTLCache(maxsize=256, ttl=1800)
_streams_cache = TTLCache(maxsize=256, ttl=900)
_details_cache = TTLCache(maxsize=512, ttl=86400)
_streams_by_key = TTLCache(maxsize=128, ttl=600)


def _tmdb_key():
    try:
        from config import Config
        return Config.TMDB_API_KEY or ''
    except Exception:
        return ''


def _session():
    s = requests.Session()
    s.verify = False
    s.headers.update({'User-Agent': UA})
    return s


def _decrypt_link(b64_cipher, passphrase=LINK_AES_PASS):
    """CryptoJS OpenSSL format: b64('Salted__' + salt(8) + AES-256-CBC ct)."""
    raw = base64.b64decode(b64_cipher)
    if raw[:8] != b'Salted__' or Cipher is None:
        return ''
    salt = raw[8:16]
    pwd = passphrase.encode()
    d = b''
    prev = b''
    while len(d) < 48:
        prev = hashlib.md5(prev + pwd + salt).digest()
        d += prev
    key, iv = d[:32], d[32:48]
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    pt = dec.update(raw[16:]) + dec.finalize()
    pad = pt[-1]
    if 1 <= pad <= 16:
        pt = pt[:-pad]
    return pt.decode('utf-8', 'replace')


def _zxc_details(tmdb_id, media_type):
    """ZXC's own TMDB proxy — no API key needed, returns everything at once."""
    ck = f'zxc_{media_type}_{tmdb_id}'
    if ck in _details_cache:
        return _details_cache[ck]
    for attempt in range(2):
        try:
            r = requests.get(f'{ZXC_BASE}/backend/tmdb/details/{media_type}/{tmdb_id}',
                             params={'language': 'en-US'},
                             headers={'User-Agent': UA, 'Referer': f'{ZXC_BASE}/'},
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return None
            j = r.json()
            title = j.get('title') or j.get('name') or ''
            if not title:
                return None
            info = {'title': title,
                    'year': (j.get('release_date') or '')[:4],
                    'date': j.get('release_date') or '',
                    'imdbId': j.get('imdb_id') or ''}
            _details_cache[ck] = info
            return info
        except Exception as e:
            if attempt:
                print(f'[zxc] details {media_type}/{tmdb_id} error: {e}')
    return None


def _tmdb_details(tmdb_id):
    if tmdb_id in _details_cache:
        return _details_cache[tmdb_id]
    try:
        r = requests.get(f'https://api.themoviedb.org/3/movie/{tmdb_id}',
                         params={'api_key': _tmdb_key()}, timeout=15, verify=False)
        if r.status_code != 200:
            return None
        j = r.json()
        info = {'title': j.get('title') or j.get('original_title') or '',
                'year': (j.get('release_date') or '')[:4],
                'date': j.get('release_date') or '',
                'imdbId': j.get('imdb_id') or ''}
        if not info['imdbId']:
            try:
                r2 = requests.get(f'https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids',
                                  params={'api_key': _tmdb_key()}, timeout=10, verify=False)
                if r2.status_code == 200:
                    info['imdbId'] = r2.json().get('imdb_id') or ''
            except Exception:
                pass
        _details_cache[tmdb_id] = info
        return info
    except Exception as e:
        print(f'[zxc] tmdb movie error: {e}')
        return None


def _tmdb_tv_details(tmdb_id):
    try:
        r = requests.get(f'https://api.themoviedb.org/3/tv/{tmdb_id}',
                         params={'api_key': _tmdb_key()}, timeout=10, verify=False)
        if r.status_code != 200:
            return None
        j = r.json()
        info = {'title': j.get('name') or j.get('original_name') or '',
                'year': (j.get('first_air_date') or '')[:4],
                'date': j.get('first_air_date') or '',
                'imdbId': ''}
        try:
            r2 = requests.get(f'https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids',
                              params={'api_key': _tmdb_key()}, timeout=8, verify=False)
            if r2.status_code == 200:
                info['imdbId'] = r2.json().get('imdb_id') or ''
        except Exception:
            pass
        return info
    except Exception as e:
        print(f'[zxc] tmdb tv error: {e}')
        return None


# ======================================================================
# Gagoka -> Sources flow
# ======================================================================

def _server_streams(s, tmdb_id, media_type, server, season, episode,
                    info, ref):
    """One server end-to-end -> list of {url, quality, hls} dicts."""
    body = {FM['id']: str(tmdb_id), FM['mediaType']: media_type, FM['path']: server}
    if media_type == 'tv':
        body[FM['season']] = season
        body[FM['episode']] = episode
    try:
        r = s.post(f'{ZXC_BASE}/backend/gagoka', json=body,
                   headers={'Origin': ZXC_BASE, 'Referer': ref,
                            'Content-Type': 'application/json'},
                   timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        g = r.json()
        token, ts = g.get('token'), g.get('ts')
        if not token:
            return []
    except Exception as e:
        print(f'[zxc] gagoka {server} error: {e}')
        return []

    q = {FM['id']: str(tmdb_id), FM['path']: server, FM['mediaType']: media_type,
         FM['ts']: str(ts), FM['token']: token,
         FM['title']: info.get('title') or '', FM['year']: info.get('year') or '',
         FM['date']: info.get('date') or '', FM['imdbId']: info.get('imdbId') or ''}
    if media_type == 'tv':
        q[FM['season']] = str(season)
        q[FM['episode']] = str(episode)
    try:
        r2 = s.get(f'{ZXC_BASE}/backend_/sources/{server}', params=q,
                   headers={'Referer': ref}, timeout=TIMEOUT)
        if r2.status_code != 200:
            return []
        d = r2.json()
        if not d.get('success'):
            return []
    except Exception as e:
        print(f'[zxc] sources {server} error: {e}')
        return []

    out = []
    for item in d.get('links') or []:
        enc = item.get('link') or ''
        url = _decrypt_link(enc) if enc else ''
        if not url.startswith('http'):
            continue
        quality = _probe_quality(s, url)
        out.append({'url': url, 'quality': quality,
                    'hls': item.get('type', 'hls') != 'mp4'})
    return out


def _probe_quality(s, url):
    """Fetch master m3u8; return best height (0 if unknown)."""
    try:
        r = s.get(url, headers={'Referer': f'{ZXC_BASE}/'}, timeout=TIMEOUT)
        if r.status_code != 200:
            return 0
        text = r.text
        heights = [int(h) for h in re.findall(r'RESOLUTION=\d+x(\d+)', text)]
        if heights:
            return max(heights)
        m = re.findall(r'\b(\d{3,4})p\b', url.lower())
        return max(int(x) for x in m) if m else 0
    except Exception:
        return 0


# ======================================================================
# Main Provider Class
# ======================================================================

class ZXCProvider:
    NAME = 'zxc'

    @cached(_search_cache)
    def search_anime(self, query):
        results = []
        try:
            r = requests.get('https://api.themoviedb.org/3/search/multi',
                             params={'api_key': _tmdb_key(), 'query': query},
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            for item in (r.json().get('results') or [])[:8]:
                mtype = item.get('media_type', '')
                if mtype not in ('movie', 'tv'):
                    continue
                tmdb_id = str(item.get('id') or '')
                title = item.get('title') or item.get('name') or ''
                if not tmdb_id or not title:
                    continue
                year = (item.get('release_date') or item.get('first_air_date') or '')[:4]
                results.append({
                    'title': title,
                    'slug': tmdb_id,
                    'poster': item.get('poster_path') or '',
                    'type': mtype,
                    'provider': self.NAME,
                    'tmdb_id': tmdb_id,
                    'year': year,
                })
        except Exception as e:
            print(f'[zxc] search error: {e}')
        return results

    @cached(cache=_streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1, media_type=None):
        tmdb_id = str(slug or '')
        if not tmdb_id:
            return {'streams': []}
        if media_type in ('tv', 'series'):
            candidates = ['tv']
        elif media_type == 'movie':
            candidates = ['movie']
        else:
            candidates = ['movie', 'tv']
        for mtype in candidates:
            info = _zxc_details(tmdb_id, mtype)
            if not info:
                info = (_tmdb_tv_details(tmdb_id) if mtype == 'tv'
                        else _tmdb_details(tmdb_id))
            if not info or not info.get('title'):
                continue
            result = self._fetch_for_type(tmdb_id, mtype, season, episode, info)
            if result:
                return {'streams': result}
        return {'streams': []}

    def _fetch_for_type(self, tmdb_id, media_type, season, episode, info):
        key = f'{tmdb_id}_{media_type}_{season}_{episode}'
        if key in _streams_by_key:
            return _streams_by_key[key]
        ref = (f'{ZXC_BASE}/player/{media_type}/{tmdb_id}/{season}/{episode}'
               f'?server=0&subLang=english')
        s = _session()
        streams = []
        seen_urls = set()
        for server in SERVERS:
            for item in _server_streams(s, tmdb_id, media_type, server,
                                        season, episode, info, ref):
                if item['url'] in seen_urls:
                    continue
                seen_urls.add(item['url'])
                streams.append(_stremio_stream(server, item))
        if not streams:
            return None
        _streams_by_key[key] = streams
        return streams

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return {'title': f'ZXC {slug}', 'slug': slug, 'type': 'movie',
                'provider': self.NAME}

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': 1, 'title': slug, 'slug': slug}]


def _quality_label(q):
    return {2160: '4K', 1440: '1440p', 1080: '1080p', 720: '720p',
            480: '480p', 360: '360p'}.get(q, f'{q}p' if q else 'SD')


def _stremio_stream(server, item):
    q = item.get('quality') or 0
    st = {'url': item['url'],
          'name': f'ZXC {server}',
          'title': f'{_quality_label(q)} | ZXC {server}'}
    if item.get('hls', True):
        st['behaviorHints'] = {'notWebReady': True, 'bingeGroup': 'zxc'}
        st['proxyHeaders'] = {'request': {'Referer': f'{ZXC_BASE}/',
                                          'User-Agent': UA}}
    return st
