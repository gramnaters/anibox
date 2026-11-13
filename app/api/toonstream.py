"""
ToonStream provider.

The site rotated to a new "access" gate on toonstream.us: episode pages show a
24-hour shortener/ads wall instead of players. Its own "Continue" button sends
users to the `tooniboy.xyz` mirror, which serves the episode page directly with
the `#aa-options` player iframes (same DOM the CloudStream plugin parses:
`#aa-options > div > iframe` with `src`/`data-src`).

So we use tooniboy.xyz as the primary host and toonstream.us as a fallback. If a
toonstream.us page is gated, we replay the site's own client call to
`/api/access/ads/verify` (the same request the "continue with ads" button makes)
to unlock the 24-hour cookie, then refetch.

Search:  GET /search/all?q=            -> {count, data:[{title, type, url}]}
Details: /series/<slug>/ or /movies/<slug>/
         episodes in `#episode_by_temp li` / `.post-lst li`, href `/episode/<slug>-<s>x<e>/`
Streams: `#aa-options iframe` -> player extractors (abyss, streamruby, upnshare, ...)
"""
import re

import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached
from urllib.parse import urljoin, urlparse

BASES = ('https://tooniboy.xyz', 'https://toonstream.us')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 20

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _classify_embed(url):
    """Map an embed host URL to a player key handled by app.players."""
    u = url.lower()
    if 'rubystm' in u or 'streamruby' in u or 'vidhide' in u or 'streamhide' in u:
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
    if ('byse' in u or 'alapuix' in u) and '/e/' in u:
        return 'byse'
    if 'filemoon' in u or 'bysetayico' in u or 'byseze' in u:
        return 'filemoon'
    if 'strmup' in u or 'streamwish' in u:
        return 'filemoon'
    if 'hanerix' in u or 'smoothpre' in u:
        return 'streamhg'
    # streamsb.net and vidstreaming.xyz sit behind the same JS proof-of-work
    # challenge (302 -> 401 for non-browser clients). Leave them unclassified
    # so they're skipped instead of returned as dead links.
    return ''


class ToonStreamProvider:
    NAME = 'toonstream'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def _fetch(self, url, referer=None):
        """GET a page, replaying the site's own ads-unlock call if it's gated."""
        headers = {'Referer': referer} if referer else {}
        r = self.session.get(url, headers=headers, timeout=TIMEOUT, verify=False)
        if r.status_code == 200 and 'accessStatus' in r.text and 'aa-options' not in r.text:
            parsed = urlparse(url)
            base = f'{parsed.scheme}://{parsed.netloc}'
            try:
                self.session.post(
                    f'{base}/api/access/ads/verify',
                    headers={'Content-Type': 'application/json',
                             'Referer': url, 'Origin': base,
                             'X-Requested-With': 'XMLHttpRequest'},
                    json={'returnTo': parsed.path}, timeout=TIMEOUT, verify=False)
                r = self.session.get(url, headers=headers, timeout=TIMEOUT, verify=False)
            except Exception:
                pass
        return r

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        data, base = [], BASES[0]
        for candidate in BASES:
            try:
                r = self.session.get(f'{candidate}/search/all', params={'q': query},
                                     headers={'X-Requested-With': 'XMLHttpRequest'},
                                     timeout=TIMEOUT, verify=False)
                if r.status_code == 200:
                    found = r.json().get('data') or []
                    if found:
                        data, base = found, candidate
                        break
            except Exception:
                continue
        results = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = item.get('title', '')
            itype = item.get('type', '')
            url = item.get('url', '')
            if not title or not url:
                continue
            kind = 'series' if itype == 'series' else 'movie'
            results.append({
                'title': title,
                'slug': f'{kind}/{url.rstrip("/").split("/")[-1]}',
                'poster': '',
                'type': 'movie' if kind == 'movie' else 'series',
                'provider': self.NAME,
                'url': urljoin(base + '/', url),
            })
        return results

    def get_home_catalog(self) -> list:
        """Home rows from the site's own category listings — the same sections
        the CloudStream Toonstream extension browses (#movies-a li)."""
        sections = ('category/anime-series', 'category/anime-movies', 'category/movies')
        results, seen = [], set()
        for base in BASES:
            for path in sections:
                try:
                    r = self.session.get(f'{base}/{path}', timeout=TIMEOUT, verify=False)
                    if r.status_code != 200:
                        continue
                    soup = BeautifulSoup(r.text, 'html.parser')
                    for li in soup.select('#movies-a li'):
                        a = li.select_one('a')
                        href = a.get('href', '') if a else ''
                        if not href:
                            continue
                        slug = href.rstrip('/').strip('/')
                        kind = 'movie' if slug.startswith('movies/') else 'series'
                        if kind == 'movie':
                            slug = 'movie/' + slug.split('/', 1)[1]
                        if not slug or slug in seen:
                            continue
                        seen.add(slug)
                        img = li.find('img')
                        t = li.select_one('h2, h3, .title, .entry-title')
                        title = t.text.strip() if t else ((img.get('alt') if img else '') or slug.split('/')[-1])
                        results.append({'title': title, 'slug': slug,
                                        'poster': (img.get('src') if img else '') or '',
                                        'type': kind, 'provider': self.NAME})
                except Exception:
                    continue
        return results

    def _candidate_urls(self, slug):
        """slug is 'series/<basename>' or 'movie/<basename>'."""
        if '/' not in slug:
            return []
        kind, basename = slug.split('/', 1)
        prefix = 'movies' if kind == 'movie' else 'series'
        return [f'{base}/{prefix}/{basename}/' for base in BASES]

    def _slug_url(self, slug):
        urls = self._candidate_urls(slug)
        return urls[0] if urls else None

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        url = r = None
        for candidate in self._candidate_urls(slug):
            try:
                rr = self._fetch(candidate)
                if rr is not None and rr.status_code == 200:
                    url, r = candidate, rr
                    break
            except Exception:
                continue
        if not url or r is None:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')

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
        base = f'{urlparse(url).scheme}://{urlparse(url).netloc}'
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
                'ep_url': urljoin(base + '/', href),
            })
        if not episodes:
            basename = slug.split('/', 1)[1]
            episodes = [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug,
                         'ep_url': f'{base}/episode/{basename}-1x{i}/'}
                        for i in range(1, 200)]
        return {
            'title': title, 'slug': slug, 'poster': poster, 'type': 'series',
            'provider': self.NAME, 'episodes': episodes,
        }

    def get_episodes(self, slug: str) -> list:
        details = self.get_anime_details(slug)
        return details.get('episodes', []) if details else []

    def _episode_url(self, slug, season, episode):
        details = self.get_anime_details(slug)
        if details:
            for ep in details.get('episodes', []):
                if ep.get('season') == season and ep.get('episode') == episode:
                    if ep.get('ep_url'):
                        return ep['ep_url']
        kind = slug.split('/', 1)[0] if '/' in slug else ''
        basename = slug.split('/', 1)[1] if '/' in slug else slug
        if kind == 'movie':
            return self._slug_url(slug)
        return f'https://tooniboy.xyz/episode/{basename}-{season}x{episode}/'

    @cached(streams_cache)
    def get_episode_streams(self, slug: str, season: int = 1, episode: int = 1) -> dict:
        streams = []
        ep_url = self._episode_url(slug, season, episode)
        candidates = [ep_url] if ep_url else []
        if ep_url and 'tooniboy.xyz' in ep_url:
            candidates.append(ep_url.replace('tooniboy.xyz', 'toonstream.us'))
        elif ep_url and 'toonstream.us' in ep_url:
            candidates.append(ep_url.replace('toonstream.us', 'tooniboy.xyz'))

        seen = set()
        for url in candidates:
            if not url or url in seen:
                continue
            seen.add(url)
            try:
                r = self._fetch(url, referer='https://tooniboy.xyz/')
                if r is None or r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                # Match the CloudStream plugin + live DOM: players live in #aa-options.
                iframes = soup.select('#aa-options iframe') or soup.select('iframe[src], iframe[data-src]')
                base = f'{urlparse(url).scheme}://{urlparse(url).netloc}'
                for ifr in iframes:
                    src = ifr.get('src') or ifr.get('data-src') or ''
                    if not src or 'youtube.com' in src or 'youtu.be' in src:
                        continue
                    if not src.startswith('http'):
                        src = urljoin(base + '/', src)
                    player = _classify_embed(src)
                    if not player:
                        continue
                    if src in seen:
                        continue
                    seen.add(src)
                    streams.append({'player': player, 'url': src, 'name': self.NAME})
                if streams:
                    break
            except Exception as e:
                print(f'[toonstream] streams error: {e}')
        return {'streams': streams}
