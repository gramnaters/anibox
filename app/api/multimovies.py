"""
MultiMovies provider (multimovies.<tld>).
Search: WordPress `/?s=` result-items. Details/episodes: tvshows/movies pages.
Streams: per-episode page post_id -> doo_player_ajax -> embed URLs. The GD
MIRROR server (streams.iqsmartgames.com) is resolved via the shared
iqsmartgames flow; other servers have no handler yet.
"""
import re
import time
import html
import requests
from cachetools import TTLCache, cached
from bs4 import BeautifulSoup

from app.api.iqsmart_common import resolve_embed, _resolve_fileslug

DOMAINS = [
    'https://multimovies.beer',
    'https://multimovies.motorcycles',
    'https://multimovies.makeup',
    'https://multimovies.autos',
    'https://multimovies.homes',
    'https://multimovies.website',
    'https://multimovies.cfd',
]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 20

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)
_domain = {'url': None, 'ts': 0}


def _live_domain():
    now = time.time()
    if _domain['url'] and now - _domain['ts'] < 3600:
        return _domain['url']
    for d in DOMAINS:
        try:
            r = requests.get(d, timeout=12, verify=False, headers={'User-Agent': UA})
            if r.status_code != 200:
                continue
            if '/movies/' not in r.text and '/tvshows/' not in r.text:
                continue
            _domain['url'] = d
            _domain['ts'] = now
            return d
        except Exception:
            continue
    return DOMAINS[0]


class MultiMoviesProvider:
    NAME = 'multimovies'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        dom = _live_domain()
        r = self.session.get(f'{dom}/', params={'s': query}, timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, 'html.parser')
        results = []
        q = query.lower()
        for item in soup.select('div.result-item'):
            link = item.find('a', href=True)
            if not link:
                continue
            href = link.get('href', '')
            m = re.search(r'/((?:movies|tvseries|tvshows|series))/([^/?#]+)', href)
            if not m:
                continue
            kind, basename = m.group(1), m.group(2)
            title_el = item.select_one('div.title a') or item.find(['h2', 'h3', 'h4'])
            title = title_el.get_text(strip=True) if title_el else ''
            if not title or q not in title.lower():
                continue
            img = item.find('img')
            poster = img.get('src', '') if img else ''
            results.append({
                'title': title,
                'slug': f'{kind}/{basename}',
                'poster': poster,
                'type': 'movie' if 'movie' in kind else 'series',
                'provider': self.NAME,
            })
        return results

    def get_home_catalog(self) -> list:
        return []

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        if '/' not in (slug or ''):
            return None
        kind, basename = slug.split('/', 1)
        dom = _live_domain()
        r = self.session.get(f'{dom}/{slug}/', timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        img = soup.select_one('li.divider > a img') or soup.find('img')
        poster = (img.get('src') or img.get('data-src') or '') if img else ''
        title_el = soup.select_one('h1') or soup.select_one('h2') or soup.select_one('.title')
        title = title_el.get_text(strip=True) if title_el else basename.replace('-', ' ').title()

        if 'movie' in kind:
            return {
                'title': title, 'slug': slug, 'poster': poster, 'type': 'movie',
                'provider': self.NAME,
                'episodes': [{'season': 1, 'episode': 1, 'title': title, 'slug': slug}],
            }

        episodes = []
        for li in soup.select('#seasons ul.episodios li') or soup.select('ul.episodios li'):
            num = li.select_one('div.numerando')
            el = li.select_one('div.episodiotitle a[href]')
            if not (num and el):
                continue
            mm = re.match(r'(\d+)\s*-\s*(\d+)', num.get_text(strip=True))
            if not mm:
                continue
            episodes.append({
                'season': int(mm.group(1)),
                'episode': int(mm.group(2)),
                'title': el.get_text(strip=True) or f"Episode {mm.group(2)}",
                'slug': slug,
                'ep_url': el.get('href', ''),
            })
        if not episodes:
            episodes = [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug}
                        for i in range(1, 200)]
        return {
            'title': title, 'slug': slug, 'poster': poster, 'type': 'series',
            'provider': self.NAME, 'episodes': episodes,
        }

    def get_episodes(self, slug: str) -> list:
        details = self.get_anime_details(slug)
        return details.get('episodes', []) if details else []

    @cached(streams_cache)
    def get_episode_streams(self, slug: str, season: int = 1, episode: int = 1) -> dict:
        if '/' not in (slug or ''):
            return {'streams': []}
        kind, basename = slug.split('/', 1)
        dom = _live_domain()
        try:
            if 'movie' in kind:
                pid, ptype = self._post_from_page(f'{dom}/{slug}/', 'movie')
                embeds = self._doo_player(dom, pid, 'movie') if pid else []
            else:
                ep_url = self._episode_url(slug, kind, basename, season, episode, dom)
                pid, ptype = self._post_from_page(ep_url, 'tv')
                embeds = self._doo_player(dom, pid, 'tv') if pid else []

            streams = []
            for eu in embeds:
                added = 0
                if 'iqsmartgames' in eu or 'gdmirrorbot' in eu or 'embedhelper' in eu:
                    for sd in resolve_embed(eu):
                        sd.setdefault('name', 'GDMirrorBot')
                        streams.append(sd)
                        added += 1
                if not added:
                    # Raw-sid embeds (e.g. filesforever.link/embed/<sid>): universal sid flow
                    m = re.search(r'/embed/([A-Za-z0-9_-]+)', eu or '')
                    if m and m.group(1) not in ('tv', 'movie', 'imdb'):
                        for sd in _resolve_fileslug(m.group(1)):
                            sd.setdefault('name', sd.get('name') or 'GDMulti')
                            streams.append(sd)
            # Different embeds often resolve to the same sub-hosts — dedupe so
            # Stremio gets one link per source (duplicate signed tokens confuse it)
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

    def _episode_url(self, slug, kind, basename, season, episode, dom):
        details = self.get_anime_details(slug)
        if details:
            for ep in details.get('episodes', []):
                if ep.get('season') == season and ep.get('episode') == episode and ep.get('ep_url'):
                    return ep['ep_url']
        return f'{dom}/episodes/{basename}-{season}x{episode}/'

    def _post_from_page(self, url, default_type):
        r = self.session.get(url, timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return None, default_type
        soup = BeautifulSoup(r.text, 'html.parser')
        li = soup.select_one('#playeroptionsul li[data-post]') or soup.select_one('li[data-post]')
        if not li:
            return None, default_type
        return li.get('data-post'), li.get('data-type') or default_type

    def _doo_player(self, dom, pid, ptype):
        embeds = []
        for nume in range(1, 7):
            try:
                rp = self.session.post(
                    f'{dom}/wp-admin/admin-ajax.php',
                    headers={'X-Requested-With': 'XMLHttpRequest',
                             'Content-Type': 'application/x-www-form-urlencoded',
                             'Referer': f'{dom}/'},
                    data=f'action=doo_player_ajax&post={pid}&nume={nume}&type={ptype}',
                    timeout=TIMEOUT, verify=False)
                j = rp.json()
                eu = j.get('embed_url', '')
                if not eu:
                    break
                eu = html.unescape(eu)
                im = re.search(r'<iframe[^>]+src="([^"]+)"', eu)
                if im:
                    eu = im.group(1)
                if eu:
                    embeds.append(eu)
            except Exception:
                break
        return embeds
