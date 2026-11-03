"""
Screenscape provider (screenscape.me) - direct m3u8/mp4 sources via encrypted API.

The site wraps every /api response in an encrypted envelope. We reproduce the
client crypto exactly (module 657289 from the served chunks), which is now the
"v3" flow (ECDH + HKDF-SHA256 + AES-GCM):

  - handshake: generate an ECDH P-256 keypair; POST the public key to
    /api/<tokenRoute> with header x-screenscape-bootstrap; the response is an
    ECDH envelope {pk, d, iv, v:3} -> complete handshake -> {responseKey, apiToken}
  - sources: GET /api/<routeReqId>/<serverReqId>?q=<tmdbReqId> with x-api-token;
    the response is an envelope {d, iv, ts, v:3} decrypted with HKDF-SHA256
    (salt "screenscape-resp-v3", info "<context>|<ts>") + AES-GCM.

Request routes/ids are HMAC-SHA256 signed with the responseKey (mint* helpers).
"""
import base64
import hashlib
import hmac
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit, parse_qsl, urlencode

import requests
from cachetools import TTLCache, cached
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

BASE_URL = 'https://screenscape.me'
RESP_SALT = b'screenscape-resp-v3'
ECDH_SALT = b'screenscape-ecdh-v3-salt'
ECDH_INFO = b'screenscape-ecdh-v3'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 25
SERVERS = ['streamflix', 'castel', 'hdhub', 'moviebox', 'nitro',
           'fun', 'blast', 'awsind', 'vaplayer', 'kdh']

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _hmac_hex(msg, key):
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def _b64url_decode(s):
    s = s.replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    return base64.b64decode(s)


def _nonce():
    return ''.join(random.choice('0123456789abcdef') for _ in range(18))


def _base36(n):
    chars = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while n:
        n, r = divmod(n, 36)
        out = chars[r] + out
    return out or '0'


def _create_token_route(bootstrap):
    x = f'token.{_base36(int(time.time() * 1000))}.{_nonce()}'
    return _b64url(x) + '.' + _hmac_hex(x, bootstrap)[:24]


def _create_server_route(response_key):
    x = json.dumps({'k': 'route', 'v': 'server', 't': int(time.time() * 1000),
                    'n': _nonce()}, separators=(',', ':'))
    return _b64url(x) + '.' + _hmac_hex(x, response_key)[:24]


def _create_server_req(server, response_key):
    x = f'{server}.{_base36(int(time.time() * 1000))}.{_nonce()}'
    return _b64url(x) + '.' + _hmac_hex(x, response_key)[:24]


def _create_tmdb_req(tmdb_id, season, episode, response_key):
    x = json.dumps({'k': 'tmdb', 't': int(time.time() * 1000), 'n': _nonce(),
                    'tmdbId': str(tmdb_id), 'season': season, 'episode': episode},
                   separators=(',', ':'))
    return _b64url(x) + '.' + _hmac_hex(x, response_key)[:24]


def _build_context(url, method):
    parts = urlsplit(url)
    params = sorted(parse_qsl(parts.query, keep_blank_values=True))
    return f'{method}:{parts.path}?{urlencode(params)}'


def _generate_keypair():
    """ECDH P-256 keypair -> (publicKeyB64, privateKey)."""
    private = ec.generate_private_key(ec.SECP256R1())
    public_bytes = private.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint)
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip('=')
    return public_b64, private


def _aes_gcm_decrypt(key, iv_b64, data_b64):
    iv = _b64url_decode(iv_b64)
    ct = _b64url_decode(data_b64)
    return AESGCM(key).decrypt(iv, ct, None)


def _complete_handshake(private_key, envelope):
    """ECDH + HKDF-SHA256 + AES-GCM decrypt of the handshake envelope."""
    server_pk = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), _b64url_decode(envelope['pk']))
    shared = private_key.exchange(ec.ECDH(), server_pk)
    key = HKDF(algorithm=hashes.SHA256(), length=32,
               salt=ECDH_SALT, info=ECDH_INFO).derive(shared)
    pt = _aes_gcm_decrypt(key, envelope['iv'], envelope['d'])
    return json.loads(pt.decode('utf-8'))


def _open_api_body(envelope, response_key, context):
    """HKDF-SHA256 + AES-GCM decrypt of a sources/API envelope {d, iv, ts, v:3}."""
    if envelope.get('v') != 3 or 'd' not in envelope or 'iv' not in envelope or 'ts' not in envelope:
        return None
    ts = envelope['ts']
    key = HKDF(algorithm=hashes.SHA256(), length=32,
               salt=RESP_SALT, info=f'{context}|{ts}'.encode()).derive(response_key.encode())
    pt = _aes_gcm_decrypt(key, envelope['iv'], envelope['d'])
    obj = json.loads(pt.decode('utf-8'))
    if obj.get('ts') != ts or 'body' not in obj:
        return None
    return obj['body']


def _tmdb_key():
    try:
        from config import Config
        return Config.TMDB_API_KEY or ''
    except Exception:
        return ''


class ScreenscapeProvider:
    NAME = 'screenscape'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self._auth_lock = threading.Lock()
        self._auth = None  # {'responseKey', 'apiToken', 'exp'}

    def _api_headers(self, extra=None):
        h = {
            'x-screenscape-client': 'web-player',
            'referer': f'{BASE_URL}/',
            'Origin': BASE_URL,
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'content-type': 'text/plain;charset=UTF-8',
            'accept': '*/*',
        }
        if extra:
            h.update(extra)
        return h

    def _ensure_auth(self):
        """ECDH handshake POST, cached until it expires (27 min server-side)."""
        now = time.time()
        with self._auth_lock:
            if self._auth and self._auth['exp'] > now + 60:
                return self._auth
            public_b64, private_key = _generate_keypair()
            route = _create_token_route(public_b64)
            url = f'{BASE_URL}/api/{route}'
            r = self.session.post(url, headers=self._api_headers(
                {'x-screenscape-bootstrap': public_b64}), timeout=TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(f'screenscape auth status {r.status_code}')
            pt = _complete_handshake(private_key, r.json())
            if not pt or not pt.get('responseKey') or not pt.get('apiToken'):
                raise RuntimeError('screenscape auth decrypt failed')
            self._auth = {
                'responseKey': pt['responseKey'],
                'apiToken': pt['apiToken'],
                'exp': now + 27 * 60,
            }
            return self._auth

    def _fetch_server_streams(self, auth, server, tmdb_id, season, episode):
        try:
            response_key = auth['responseKey']
            l = _create_server_route(response_key)
            n = _create_server_req(server, response_key)
            q = _create_tmdb_req(tmdb_id, season, episode, response_key)
            url = f'{BASE_URL}/api/{l}/{n}?q={q}'
            r = self.session.get(url, headers=self._api_headers(
                {'x-api-token': auth['apiToken']}), timeout=TIMEOUT)
            if r.status_code != 200:
                return []
            pt = _open_api_body(r.json(), response_key, _build_context(url, 'GET'))
            if not pt:
                return []
            return (pt.get('streams') or [])
        except Exception as e:
            print(f'[screenscape] {server} error: {e}')
            return []

    def _collect_streams(self, tmdb_id, season, episode):
        auth = self._ensure_auth()
        if season is None:
            season_arg, episode_arg = None, None
        else:
            season_arg, episode_arg = season, episode

        results = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(self._fetch_server_streams, auth, sv,
                              tmdb_id, season_arg, episode_arg): sv
                    for sv in SERVERS}
            for fut in as_completed(futs):
                for st in fut.result() or []:
                    results.append(st)

        # Movies requested as s1e1 fall back to a null-season (movie-style) query.
        if not results and season == 1 and episode == 1:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = {ex.submit(self._fetch_server_streams, auth, sv,
                                  tmdb_id, None, None): sv
                        for sv in SERVERS}
                for fut in as_completed(futs):
                    for st in fut.result() or []:
                        results.append(st)
        return results

    def _streams_to_out(self, raw_streams):
        out = []
        seen = set()
        for st in raw_streams or []:
            if st.get('downloadOnly'):
                continue
            url = st.get('url') or ''
            if not url or url in seen:
                continue
            seen.add(url)
            hdrs = st.get('headers') or {}
            name = st.get('name') or st.get('title') or 'Screenscape'
            out.append({
                'player': 'direct_m3u8',
                'url': url,
                'name': name,
                'referer': hdrs.get('Referer') or hdrs.get('referer') or f'{BASE_URL}/',
                'headers': hdrs or {'Referer': f'{BASE_URL}/'},
            })
        return out

    @cached(search_cache)
    def search_anime(self, query):
        """TMDB search (series first) -> tmdb id slug. Screenscape serves most titles."""
        results = []
        try:
            r = requests.get('https://api.themoviedb.org/3/search/tv',
                             params={'api_key': _tmdb_key(), 'query': query},
                             timeout=TIMEOUT)
            if r.status_code == 200:
                for item in (r.json().get('results') or [])[:4]:
                    tmdb_id = str(item.get('id') or '')
                    name = item.get('name') or ''
                    if not tmdb_id or not name:
                        continue
                    if self._title_matches(query, name):
                        results.append({
                            'title': name, 'slug': tmdb_id, 'poster': '',
                            'type': 'series', 'provider': self.NAME,
                        })
                        break
            if not results:
                rm = requests.get('https://api.themoviedb.org/3/search/movie',
                                  params={'api_key': _tmdb_key(), 'query': query},
                                  timeout=TIMEOUT)
                if rm.status_code == 200:
                    for item in (rm.json().get('results') or [])[:4]:
                        tmdb_id = str(item.get('id') or '')
                        name = item.get('title') or ''
                        if not tmdb_id or not name:
                            continue
                        if self._title_matches(query, name):
                            results.append({
                                'title': name, 'slug': tmdb_id, 'poster': '',
                                'type': 'movie', 'provider': self.NAME,
                            })
                            break
        except Exception as e:
            print(f'[screenscape] search error: {e}')
        return results

    def _title_matches(self, query, name):
        import unicodedata
        def _norm(s):
            s = unicodedata.normalize('NFKD', s.lower())
            return ''.join(c for c in s if not unicodedata.combining(c))
        return _norm(query) in _norm(name)

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return {
            'title': f'Screenscape {slug}',
            'slug': slug,
            'type': 'series',
            'provider': self.NAME,
            'episodes': self.get_episodes(slug),
        }

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug}
                for i in range(1, 300)]

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        tmdb_id = self._tmdb_from_slug(slug)
        if not tmdb_id:
            return {'streams': []}
        try:
            raw = self._collect_streams(tmdb_id, season, episode)
            return {'streams': self._streams_to_out(raw)}
        except Exception as e:
            print(f'[screenscape] episode streams error: {e}')
            return {'streams': []}

    def _tmdb_from_slug(self, slug):
        if slug and str(slug).isdigit():
            return str(slug)
        import re
        m = re.search(r'-(\d+)$', str(slug or ''))
        return m.group(1) if m else None