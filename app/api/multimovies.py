"""
MultiMovies provider (multimovies.<tld>).

The site has migrated to a rotating domain + a new "Cinema" frontend theme:
  - live domain: m1.multimovies.courses (also published in phisher's remote
    domains.json, which we fetch as the source of truth)
  - search:     GET /search?q=  ->  article.poster-card  ->  /movie/{slug}-{id}
                or /series/{slug}-{id}
  - series:     /series/{slug}-{id}  ->  episode links
                /series/{slug}-{id}/season/{s}/episode/{e}
  - streams:    button.server-chip[data-url] (no more doo_player_ajax)

Each server chip's data-url is dispatched by host:
  - rozgarlelo.modiplay.xyz  -> proxy.php -> var src stream_proxy.php -> m3u8
  - streams.iqsmartgames.com -> shared iqsmartgames flow
  - web.nxsha.app            -> nxsha.space encrypted API
  - embed.vidrift.net        -> direct .m3u8 in the embed HTML
  - embed.filmu.in           -> direct .m3u8 in the embed HTML
  - vidout.pages.dev         -> direct .m3u8 in the embed HTML
  - screenscape/peachify/nhdapi/nexus/vidbolt -> dead or JS-only (skipped)
"""
import html
import re
import time

import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached

from app.api.iqsmart_common import resolve_embed

DOMAINS_URL = ('https://raw.githubusercontent.com/phisher98/TVVVV/'
               'refs/heads/main/domains.json')
DOMAINS = [
    'https://m1.multimovies.courses',
    'https://multimovies.garden',
    'https://multimovies.makeup',
    'https://multimovies.beer',
    'https://multimovies.motorcycles',
]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 20

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)
_domain = {'url': None, 'ts': 0}


def _unescape(s):
    """HTML-unescape until stable (server double-encodes &amp;s sometimes)."""
    s = html.unescape(s or '')
    for _ in range(3):
        n = html.unescape(s)
        if n == s:
            break
        s = n
    return s


def _live_domain():
    """Resolve the current MultiMovies domain: remote domains.json first,
    then a probe of the static fallback list."""
    now = time.time()
    if _domain['url'] and now - _domain['ts'] < 3600:
        return _domain['url']
    # 1) remote source of truth
    try:
        d = requests.get(DOMAINS_URL, timeout=12, verify=False,
                         headers={'User-Agent': UA}).json()
        mm = d.get('MultiMovies') or d.get('multimovies')
        if mm and str(mm).startswith('http'):
            _domain['url'] = str(mm).rstrip('/')
            _domain['ts'] = now
            return _domain['url']
    except Exception:
        pass
    # 2) static fallback probe (new theme marker = 'poster-card' or 'server-chip')
    for d in DOMAINS:
        try:
            r = requests.get(d, timeout=12, verify=False, headers={'User-Agent': UA})
            if r.status_code == 200 and ('poster-card' in r.text or 'server-chip' in r.text):
                _domain['url'] = d.rstrip('/')
                _domain['ts'] = now
                return _domain['url']
        except Exception:
            continue
    return DOMAINS[0]


class MultiMoviesProvider:
    NAME = 'multimovies'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    # ------------------------------------------------------------------ search
    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        dom = _live_domain()
        try:
            r = self.session.get(f'{dom}/search', params={'q': query},
                                 timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
        except Exception:
            return []
        soup = BeautifulSoup(r.text, 'html.parser')
        q = query.lower()
        results = []
        for card in soup.select('article.poster-card'):
            a = card.select_one('a.poster-art[href]')
            if not a:
                continue
            href = a.get('href', '')
            m = re.match(r'/(movie|series)/([^/?#]+)', href)
            if not m:
                continue
            kind, basename = m.group(1), m.group(2)
            title = (a.get('aria-label') or ''
                     or (a.find('img') and (a.find('img').get('alt') or '')))
            title = _unescape(title).strip()
            if not title:
                t = card.select_one('h2, h3, .poster-title, .poster-meta')
                title = t.get_text(strip=True) if t else basename.replace('-', ' ').title()
            if q and q not in title.lower():
                continue
            img = card.find('img')
            poster = (img.get('src') or img.get('data-src') or '') if img else ''
            results.append({
                'title': title,
                'slug': f'{kind}/{basename}',
                'poster': poster,
                'type': 'movie' if kind == 'movie' else 'series',
                'provider': self.NAME,
            })
        return results

    def get_home_catalog(self) -> list:
        return []

    # ----------------------------------------------------------------- details
    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        if '/' not in (slug or ''):
            return None
        kind, basename = slug.split('/', 1)
        dom = _live_domain()
        try:
            r = self.session.get(f'{dom}/{kind}/{basename}', timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return None
        except Exception:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        img = soup.select_one('img[alt]')
        poster = (img.get('src') or img.get('data-src') or '') if img else ''
        title_el = soup.select_one('h1') or soup.select_one('h2') or soup.select_one('a.poster-art')
        title = title_el.get_text(strip=True) if title_el else basename.replace('-', ' ').title()

        if kind == 'movie':
            return {
                'title': title, 'slug': slug, 'poster': poster, 'type': 'movie',
                'provider': self.NAME,
                'episodes': [{'season': 1, 'episode': 1, 'title': title, 'slug': slug}],
            }

        # series: gather episode links /series/{slug}-{id}/season/{s}/episode/{e}
        episodes = []
        seen = set()
        for a in soup.select('a[href*="/season/"][href*="/episode/"]'):
            href = a.get('href', '')
            m = re.search(r'/season/(\d+)/episode/(\d+)', href)
            if not m:
                continue
            s, e = int(m.group(1)), int(m.group(2))
            key = (s, e)
            if key in seen:
                continue
            seen.add(key)
            label = a.get_text(strip=True) or f'Episode {e}'
            episodes.append({
                'season': s, 'episode': e, 'title': label,
                'slug': slug, 'ep_url': href,
            })
        if not episodes:
            episodes = [{'season': 1, 'episode': i, 'title': f'Episode {i}',
                         'slug': slug} for i in range(1, 200)]
        return {
            'title': title, 'slug': slug, 'poster': poster, 'type': 'series',
            'provider': self.NAME, 'episodes': episodes,
        }

    def get_episodes(self, slug: str) -> list:
        details = self.get_anime_details(slug)
        return details.get('episodes', []) if details else []

    # ----------------------------------------------------------------- streams
    @cached(streams_cache)
    def get_episode_streams(self, slug: str, season: int = 1, episode: int = 1) -> dict:
        if '/' not in (slug or ''):
            return {'streams': []}
        kind, basename = slug.split('/', 1)
        dom = _live_domain()
        try:
            if kind == 'movie':
                page_url = f'{dom}/movie/{basename}'
            else:
                page_url = self._episode_url(slug, kind, basename, season, episode, dom)
            chips = self._server_chips(page_url)

            streams = []
            for name, url in chips:
                added = 0
                low = url.lower()
                if 'modiplay' in low:
                    for sd in self._resolve_modiplay(url):
                        sd.setdefault('name', f'ModiPlay {name}'.strip())
                        streams.append(sd)
                        added += 1
                elif 'iqsmartgames' in low or 'gdmirrorbot' in low:
                    for sd in resolve_embed(url):
                        sd.setdefault('name', f'GD Mirror {name}'.strip())
                        streams.append(sd)
                        added += 1
                elif 'nxsha' in low:
                    for sd in self._resolve_nxsha(url):
                        sd.setdefault('name', f'NxSha {name}'.strip())
                        streams.append(sd)
                        added += 1
                elif any(h in low for h in ('vidrift', 'filmu', 'vidout')):
                    for sd in self._resolve_direct(url):
                        sd.setdefault('name', name or 'MultiMovies')
                        streams.append(sd)
                        added += 1
                # else: dead/JS host, skip

            # dedupe by (player, url)
            seen = set()
            unique = []
            for sd in streams:
                key = (sd.get('player'), sd.get('url'))
                if key in seen or not sd.get('url'):
                    continue
                seen.add(key)
                unique.append(sd)
            return {'streams': unique}
        except Exception as e:
            print(f'[multimovies] streams error: {e}')
            return {'streams': []}

    # ------------------------------------------------------------------ helpers
    def _server_chips(self, page_url):
        """Parse button.server-chip[data-url] from a movie/episode page."""
        try:
            r = self.session.get(page_url, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
        except Exception:
            return []
        soup = BeautifulSoup(r.text, 'html.parser')
        out = []
        for b in soup.select('button.server-chip[data-url]'):
            url = _unescape(b.get('data-url'))
            if not url or not url.startswith('http'):
                continue
            name_el = b.select_one('.server-name')
            name = name_el.get_text(strip=True) if name_el else ''
            out.append((name, url))
        return out

    def _resolve_modiplay(self, embed_url):
        """rozgarlelo.modiplay.xyz: embed -> proxy.php -> var src (stream_proxy.php)
        -> m3u8. Verified live: returns a playable #EXTM3U."""
        out = []
        try:
            if not embed_url.startswith('http'):
                return out
            from urllib.parse import urlparse, urljoin
            r = self.session.get(embed_url, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return out
            ifm = re.search(r'<iframe[^>]+src="([^"]+)"', r.text)
            if not ifm:
                return out
            proxy = _unescape(ifm.group(1))
            proxy = urljoin(embed_url, proxy)
            rp = self.session.get(proxy, headers={'Referer': embed_url},
                                  timeout=TIMEOUT, verify=False)
            if rp.status_code != 200:
                return out
            m = re.search(r'var\s+src\s*=\s*"([^"]+)"', rp.text)
            if m:
                src = _unescape(m.group(1)).replace('\\/', '/')
                src = urljoin(proxy, src)
                out.append({
                    'player': 'direct_m3u8',
                    'url': src,
                    'name': 'ModiPlay',
                    'referer': proxy,
                })
                return out
            # fallback: any iframe in proxy.php
            m2 = re.search(r'<iframe[^>]+src="([^"]+)"', rp.text)
            if m2:
                out.append({
                    'player': 'direct_m3u8',
                    'url': urljoin(proxy, _unescape(m2.group(1))),
                    'name': 'ModiPlay',
                    'referer': proxy,
                })
        except Exception as e:
            print(f'[multimovies] modiplay error: {e}')
        return out

    def _resolve_direct(self, embed_url):
        """vidrift / filmu / vidout: the embed page already contains a direct .m3u8."""
        out = []
        try:
            if not embed_url.startswith('http'):
                return out
            from urllib.parse import urlparse
            r = self.session.get(embed_url, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return out
            host = f'{urlparse(embed_url).scheme}://{urlparse(embed_url).netloc}/'
            m3 = re.search(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', r.text)
            if not m3:
                return out
            out.append({
                'player': 'direct_m3u8',
                'url': _unescape(m3.group(0)),
                'name': 'MultiMovies',
                'referer': host,
            })
        except Exception as e:
            print(f'[multimovies] direct error: {e}')
        return out

    def _resolve_nxsha(self, embed_url):
        """web.nxsha.app/embed/{tv|movie}/{tmdb}[/{s}/{e}] -> nxsha.space encrypted API."""
        from app.api.nxsha import (
            BASE_URL, AES_KEY, _encode_data, _crypto_js_decrypt,
        )
        m = re.search(r'/embed/(tv|movie)/(\d+)(?:/(\d+)/(\d+))?', embed_url)
        if not m:
            return []
        media_type, tmdb_id = m.group(1), m.group(2)
        season, episode = (m.group(3), m.group(4)) if m.group(3) else (1, 1)
        streams = []
        try:
            servers = self._nx_api(BASE_URL, AES_KEY, _encode_data, _crypto_js_decrypt,
                                   '/api/servers',
                                   {'tmdbId': tmdb_id, 'imdb_id': '', 'type': media_type,
                                    **({'season': season, 'episode': episode}
                                       if media_type == 'tv' else {})})
            for server in (servers or {}).get('servers') or []:
                if not server.get('web_support'):
                    continue
                scraper = server.get('scraper')
                sources = self._nx_api(BASE_URL, AES_KEY, _encode_data, _crypto_js_decrypt,
                                       '/api/sources',
                                       {'ex_lang': False, 'provider': scraper,
                                        'tmdbId': tmdb_id, 'imdb_id': '', 'type': media_type,
                                        **({'season': season, 'episode': episode}
                                           if media_type == 'tv' else {})})
                for src in (sources or {}).get('sources') or []:
                    url = src.get('url') or ''
                    if not url or 'goodstream.cc' in url:
                        continue
                    stype = src.get('type') or ''
                    label = src.get('label') or src.get('quality') or ''
                    if stype in ('m3u8', 'mp4'):
                        streams.append({
                            'player': 'direct_m3u8',
                            'url': url,
                            'name': f'{scraper} {label}'.strip(),
                            'referer': f'{BASE_URL}/',
                            'headers': {'Referer': f'{BASE_URL}/',
                                        'Origin': BASE_URL},
                        })
        except Exception as e:
            print(f'[multimovies] nxsha error: {e}')
        return streams

    def _nx_api(self, base, key, encode, decrypt, endpoint, payload):
        import json as _json
        q = encode(payload)
        r = self.session.get(f'{base}{endpoint}?q={q}',
                             headers={'User-Agent': UA, 'Referer': f'{base}/'},
                             timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return None
        body = r.json()
        if not body or '_hash' not in body:
            return None
        return _json.loads(decrypt(body['_hash']))

    def _episode_url(self, slug, kind, basename, season, episode, dom):
        details = self.get_anime_details(slug)
        if details:
            for ep in details.get('episodes', []):
                if ep.get('season') == season and ep.get('episode') == episode and ep.get('ep_url'):
                    return f'{dom}{ep["ep_url"]}'
        return f'{dom}/series/{basename}/season/{season}/episode/{episode}'
