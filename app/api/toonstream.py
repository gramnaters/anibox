"""
ToonStream provider (toonstream.us).

Search: JSON `/search/all?q=` → {count, data:[{title, type, url}]}.
Details: `/series/{slug}` (episodes in `#episode_by_temp li`, links `/episode/{slug}-{s}x{e}/`).
Streams: episode page iframes (rubystm, filesforever, cloudy.upns, vidmoly, abyssplayer, …)
→ classified into existing player extractors.
"""
import re
import requests
from urllib.parse import urljoin
from cachetools import TTLCache, cached
from bs4 import BeautifulSoup

BASE = 'https://toonstream.us'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 20

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _classify_embed(url):
    """Map an embed host URL to a player key handled by app.players."""
    u = url.lower()
    if 'rubystm' in u or 'streamruby' in u or 'vidhide' in u:
        return 'streamruby'
    if 'filesforever' in u or 'gdmirrorbot' in u or '/embed/' in u:
        return 'gdmirrorbot'
    if 'cloudy.upns' in u or 'upns' in u or 'uns.bio' in u:
        return 'upnshare'
    if 'vidmoly' in u:
        return 'vidmoly'
    if 'abyssplayer' in u:
        return 'abyss'
    if 'dood' in u:
        return 'doodstream'
    if 'streamtape' in u:
        return 'streamtape'
    if 'turbovid' in u or 'emturbovid' in u:
        return 'turbovid'
    if 'filemoon' in u or 'bysetayico' in u or 'byseze' in u:
        return 'filemoon'
    if 'strmup' in u or 'streamwish' in u:
        return 'filemoon'
    if 'hanerix' in u or 'smoothpre' in u:
        return 'streamhg'
    return ''


class ToonStreamProvider:
    NAME = 'toonstream'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        try:
            r = self.session.get(f'{BASE}/search/all', params={'q': query},
                                 headers={'X-Requested-With': 'XMLHttpRequest'},
                                 timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            data = r.json().get('data') or []
        except Exception:
            return []
        results = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = item.get('title', '')
            itype = item.get('type', '')
            url = item.get('url', '')
            if not title or not url:
                continue
            url = urljoin(BASE + '/', url)
            kind = 'series' if itype == 'series' else 'movie'
            results.append({
                'title': title,
                'slug': f'{kind}/{url.rstrip("/").split("/")[-1]}',
                'poster': '',
                'type': 'movie' if kind == 'movie' else 'series',
                'provider': self.NAME,
                'url': url,
            })
        return results

    def get_home_catalog(self) -> list:
        return []

    def _slug_url(self, slug):
        """slug is 'series/<basename>' or 'movie/<basename>'; rebuild full URL."""
        if '/' not in slug:
            return None
        kind, basename = slug.split('/', 1)
        prefix = 'movies' if kind == 'movie' else 'series'
        return f'{BASE}/{prefix}/{basename}/'

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        url = self._slug_url(slug)
        if not url:
            return None
        try:
            r = self.session.get(url, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, 'html.parser')
        except Exception:
            return None

        title = ''
        h1 = soup.select_one('h1.entry-title') or soup.select_one('h1')
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            og = soup.select_one('meta[property="og:title"]')
            title = og.get('content', '').strip() if og else slug.split('/')[-1].replace('-', ' ').title()
        img = soup.select_one('div.bghd img') or soup.select_one('.post-thumbnail img')
        poster = (img.get('src') or img.get('data-src') or '') if img else ''

        kind = slug.split('/', 1)[0]
        if kind == 'movie':
            return {
                'title': title, 'slug': slug, 'poster': poster, 'type': 'movie',
                'provider': self.NAME,
                'episodes': [{'season': 1, 'episode': 1, 'title': title, 'slug': slug, 'ep_url': url}],
            }

        episodes = []
        for li in soup.select('#episode_by_temp li, .post-lst li'):
            a = li.select_one('a[href]')
            if not a:
                continue
            href = a.get('href', '')
            m = re.search(r'-(\d+)x(\d+)/?$', href)
            if not m:
                continue
            s, e = int(m.group(1)), int(m.group(2))
            name = li.select_one('.num-epi, h2.entry-title, header.entry-header span')
            etitle = name.get_text(strip=True) if name else f'Episode {e}'
            episodes.append({
                'season': s, 'episode': e, 'title': etitle, 'slug': slug,
                'ep_url': urljoin(BASE + '/', href),
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
        kind = slug.split('/', 1)[0] if '/' in slug else ''
        details = self.get_anime_details(slug)
        ep_url = None
        if details:
            for ep in details.get('episodes', []):
                if ep.get('season') == season and ep.get('episode') == episode:
                    ep_url = ep.get('ep_url')
                    break
        if not ep_url:
            if kind == 'movie':
                ep_url = self._slug_url(slug)
            else:
                base = self._slug_url(slug)
                if base:
                    ep_url = f'{base.rstrip("/")}-{season}x{episode}/'

        streams = []
        if ep_url:
            try:
                r = self.session.get(ep_url, timeout=TIMEOUT, verify=False)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    for ifr in soup.select('iframe[src], iframe[data-src]'):
                        src = ifr.get('src') or ifr.get('data-src') or ''
                        if not src.startswith('http'):
                            continue
                        player = _classify_embed(src)
                        if not player:
                            continue
                        streams.append({'player': player, 'url': src, 'name': self.NAME})
            except Exception as e:
                print(f'[toonstream] streams error: {e}')
        return {'streams': streams}
