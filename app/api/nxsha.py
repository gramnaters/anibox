"""
NxSha provider (nxsha.space) - direct HLS/mp4 sources via encrypted API.
Flow (from HAR): embed/dl page -> /api/servers?q=<AES> -> /api/sources?q=<AES>
All q params and _hash responses are CryptoJS AES-256-CBC (OpenSSL salted
format, base64url), key "S8x!Jk4ZP1uG8$my".
Search uses TMDB (site search is JS/anti-bot) + servers API probe.
"""
import base64
import hashlib
import json
import os
import random
import re
import time

import requests
from cachetools import TTLCache, cached

BASE_URL = 'https://nxsha.space'
AES_KEY = b'S8x!Jk4ZP1uG8$my'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 15

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _evp_bytes_to_key(key, salt, key_len=32, iv_len=16):
    d = b''
    out = b''
    while len(out) < key_len + iv_len:
        d = hashlib.md5(d + key + salt).digest()
        out += d
    return out[:key_len], out[key_len:key_len + iv_len]


def _crypto_js_decrypt(ciphertext, key=AES_KEY):
    from Crypto.Cipher import AES
    c = ciphertext.replace('-', '+').replace('_', '/')
    c += '=' * (-len(c) % 4)
    raw = base64.b64decode(c)
    if raw[:8] == b'Salted__':
        salt, ct = raw[8:16], raw[16:]
    else:
        salt, ct = raw[:8], raw[8:]
    k, iv = _evp_bytes_to_key(key, salt)
    pad = AES.new(k, AES.MODE_CBC, iv).decrypt(ct)
    return pad[:-pad[-1]].decode('utf-8', errors='replace')


def _crypto_js_encrypt(data, key=AES_KEY):
    from Crypto.Cipher import AES
    t = json.dumps(data).encode('utf-8')
    salt = os.urandom(8)
    k, iv = _evp_bytes_to_key(key, salt)
    cipher = AES.new(k, AES.MODE_CBC, iv)
    padlen = 16 - (len(t) % 16)
    t += bytes([padlen]) * padlen
    ct = cipher.encrypt(t)
    out = base64.b64encode(b'Salted__' + salt + ct).decode()
    return out.replace('+', '-').replace('/', '_').replace('=', '')


def _encode_data(payload):
    payload['_req_ts'] = int(time.time() * 1000)
    payload['_req_salt'] = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=9))
    return _crypto_js_encrypt(payload)


def _tmdb_key():
    try:
        from config import Config
        return Config.TMDB_API_KEY or ''
    except Exception:
        return ''


class NxShaProvider:
    NAME = 'nxsha'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def _api(self, endpoint, payload):
        q = _encode_data(payload)
        r = self.session.get(f'{BASE_URL}{endpoint}?q={q}',
                             headers={'User-Agent': UA, 'Referer': f'{BASE_URL}/'},
                             timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return None
        body = r.json()
        if not body or '_hash' not in body:
            return None
        try:
            return json.loads(_crypto_js_decrypt(body['_hash']))
        except Exception as e:
            print(f'[nxsha] decrypt {endpoint} error: {e}')
            return None

    def _get_servers(self, tmdb_id, media_type, season=1, episode=1):
        payload = {'tmdbId': str(tmdb_id), 'imdb_id': '', 'type': media_type}
        if media_type == 'tv':
            payload['season'] = season
            payload['episode'] = episode
        data = self._api('/api/servers', payload)
        return (data or {}).get('servers') or []

    def _get_sources(self, scraper, tmdb_id, media_type, season=1, episode=1, ex_lang=False):
        payload = {'ex_lang': ex_lang, 'provider': scraper,
                   'tmdbId': str(tmdb_id), 'imdb_id': '', 'type': media_type}
        if media_type == 'tv':
            payload['season'] = season
            payload['episode'] = episode
        data = self._api('/api/sources', payload)
        return (data or {}).get('sources') or []

    @cached(search_cache)
    def search_anime(self, query):
        """TMDB search + probe whether nxsha has the title available."""
        results = []
        try:
            r = requests.get('https://api.themoviedb.org/3/search/tv',
                             params={'api_key': _tmdb_key(), 'query': query},
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            for item in (r.json().get('results') or [])[:4]:
                tmdb_id = str(item.get('id') or '')
                name = item.get('name') or ''
                if not tmdb_id or not name:
                    continue
                if not self._title_matches(query, name):
                    continue
                if self._exists_on_site(tmdb_id):
                    results.append({
                        'title': name,
                        'slug': tmdb_id,
                        'poster': '',
                        'type': 'series',
                        'provider': self.NAME,
                    })
                    break
        except Exception as e:
            print(f'[nxsha] search error: {e}')
        return results

    def _title_matches(self, query, name):
        """Case-insensitive, diacritic-tolerant substring match."""
        import unicodedata
        def _norm(s):
            s = unicodedata.normalize('NFKD', s.lower())
            return ''.join(c for c in s if not unicodedata.combining(c))
        return _norm(query) in _norm(name)

    def _exists_on_site(self, tmdb_id):
        """nxsha serves anything TMDB knows about; a servers probe is cheap enough."""
        try:
            servers = self._get_servers(tmdb_id, 'tv', 1, 1)
            return bool(servers)
        except Exception:
            return False

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return {
            'title': f'NxSha {slug}',
            'slug': slug,
            'type': 'series',
            'provider': self.NAME,
            'episodes': self.get_episodes(slug),
        }

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug} for i in range(1, 300)]

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        tmdb_id = self._tmdb_from_slug(slug)
        if not tmdb_id:
            return {'streams': []}
        streams = []
        try:
            servers = self._get_servers(tmdb_id, 'tv', season, episode)
            # Prefer web-supported scraper servers.
            for server in servers:
                if not server.get('web_support'):
                    continue
                scraper = server.get('scraper')
                try:
                    sources = self._get_sources(scraper, tmdb_id, 'tv', season, episode)
                except Exception as e:
                    print(f'[nxsha] sources {scraper} error: {e}')
                    continue
                for src in sources or []:
                    url = src.get('url') or ''
                    if not url:
                        continue
                    if 'goodstream.cc' in url:
                        continue
                    stype = src.get('type') or ''
                    label = src.get('label') or src.get('quality') or ''
                    if stype in ('m3u8', 'mp4'):
                        streams.append({
                            'player': 'direct_m3u8',
                            'url': url,
                            'name': f'{scraper} {label}'.strip(),
                            'referer': 'https://nxsha.space/',
                            'headers': {
                                'Referer': 'https://nxsha.space/',
                                'Origin': 'https://nxsha.space',
                            },
                        })
            # Dedupe by URL
            seen = set()
            unique = []
            for s in streams:
                if s['url'] in seen:
                    continue
                seen.add(s['url'])
                unique.append(s)
            return {'streams': unique}
        except Exception as e:
            print(f'[nxsha] episode streams error: {e}')
            return {'streams': []}

    def _tmdb_from_slug(self, slug):
        if slug and str(slug).isdigit():
            return str(slug)
        m = re.search(r'-(\d+)$', str(slug or ''))
        return m.group(1) if m else None