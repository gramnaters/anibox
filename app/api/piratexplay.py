"""
PirateXPlay provider (piratexplay.cc).

Search: JSON `/api/search.php/?keyword=` → {data:[{tmdb:{title,type,url}}]}.
Details: `/series/{slug}` + `/movies/{slug}` (episodes `#episode_by_temp li`, links
`/episode/{slug}-{s}x{e}/`). Streams: episode page iframes → `/public/player/index11.php?id=`
→ data-link server URLs (bysezejataos, strmup, turbovidhls, abyssplayer, iqsmartgames, …)
→ classified into existing player extractors.
"""
import re
import requests
from urllib.parse import urljoin
from cachetools import TTLCache, cached
from bs4 import BeautifulSoup

BASE = 'https://piratexplay.cc'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 20

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _classify_embed(url):
    u = url.lower()
    if 'iqsmartgames' in u or 'gdmirrorbot' in u:
        return 'gdmirrorbot'
    if 'turbovid' in u or 'emturbovid' in u:
        return 'turbovid'
    if 'abyssplayer' in u:
        return 'abyss'
    if 'byseze' in u or 'bysevepoin' in u or 'n1mwq' in u or 'byse' in u:
        return 'byse'
    if 'bysetayico' in u or 'filemoon' in u:
        return 'filemoon'
    if 'strmup' in u or 'streamwish' in u or 'pixdrive' in u:
        return 'filemoon'
    if 'rubystm' in u or 'streamruby' in u:
        return 'streamruby'
    if 'cloudy.upns' in u or 'upns' in u or 'uns.bio' in u:
        return 'upnshare'
    if 'vidmoly' in u:
        return 'vidmoly'
    if 'dood' in u:
        return 'doodstream'
    if 'streamtape' in u:
        return 'streamtape'
    if 'hanerix' in u or 'smoothpre' in u:
        return 'streamhg'
    return ''


class PirateXPlayProvider:
    NAME = 'piratexplay'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        try:
            r = self.session.get(f'{BASE}/api/search.php/',
                                 params={'keyword': query},
                                 headers={'X-Requested-With': 'XMLHttpRequest'},
                                 timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            data = r.json().get('data') or []
        except Exception:
            return []
        results = []
        for item in data:
            tmdb = (item or {}).get('tmdb') or {}
            if not isinstance(tmdb, dict):
                continue
            title = tmdb.get('title', '')
            itype = tmdb.get('type', '')
            basename = tmdb.get('url', '')
            if not title or not basename:
                continue
            kind = 'series' if itype == 'series' else 'movie'
            prefix = 'series' if kind == 'series' else 'movies'
            results.append({
                'title': title,
                'slug': f'{kind}/{basename}',
                'poster': '',
                'type': 'movie' if kind == 'movie' else 'series',
                'provider': self.NAME,
                'url': f'{BASE}/{prefix}/{basename}/',
            })
        return results

    def get_home_catalog(self) -> list:
        return []

    def _slug_url(self, slug):
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

    def _resolve_player_links(self, player_url, referer):
        """Follow an index11.php player page → data-link server URLs."""
        links = []
        try:
            r = self.session.get(player_url, headers={'Referer': referer}, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return links
            soup = BeautifulSoup(r.text, 'html.parser')
            for opt in soup.select('.server-option[data-link]'):
                dl = opt.get('data-link', '')
                if dl.startswith('http'):
                    links.append(dl)
            fr = soup.select_one('#playerFrame')
            if fr and fr.get('src'):
                links.append(fr.get('src'))
        except Exception as e:
            print(f'[piratexplay] player error: {e}')
        return links

    @cached(streams_cache)
    def get_episode_streams(self, slug: str, season: int = 1, episode: int = 1) -> dict:
        kind = slug.split('/', 1)[0] if '/' in slug else ''
        # PirateXPlay indexes each season as its own series
        # ("naruto-season-5-46260"). If the requested season differs, the site
        # has no episode for it - don't fabricate a URL.
        slug_season = re.search(r'season-(\d+)-', slug)
        if slug_season and int(slug_season.group(1)) != season:
            return {'streams': []}
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
                    seen = set()
                    for ifr in soup.select('iframe[src], iframe[data-src]'):
                        src = ifr.get('src') or ifr.get('data-src') or ''
                        if not src.startswith('http'):
                            continue
                        # index11.php player pages need following to data-links
                        if 'index11.php' in src:
                            for dl in self._resolve_player_links(src, ep_url):
                                p = _classify_embed(dl)
                                if p and dl not in seen:
                                    seen.add(dl)
                                    streams.append({'player': p, 'url': dl, 'name': self.NAME})
                        else:
                            p = _classify_embed(src)
                            if p and src not in seen:
                                seen.add(src)
                                streams.append({'player': p, 'url': src, 'name': self.NAME})
            except Exception as e:
                print(f'[piratexplay] streams error: {e}')
        return {'streams': streams}
