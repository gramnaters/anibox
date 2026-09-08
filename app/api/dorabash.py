import requests, re, json, os
from urllib.parse import quote
from cachetools import TTLCache, cached
from app.players.trawl import trawl_fetch, trawl_fetch_json

BASE_URL = 'https://dorabash.in'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 25

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


class DoraBashProvider:
    NAME = 'dorabash'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query):
        results = []
        try:
            # dorabash.in is behind Cloudflare; direct requests get 403.
            # Use the kiranime title API routed through TRAWL solver.
            data = trawl_fetch_json(
                f'{BASE_URL}/wp-json/kiranime/v1/anime/title?query={quote(query)}',
                max_timeout=45000)
            if isinstance(data, list):
                for item in data:
                    title = item.get('title') or ''
                    slug = item.get('slug') or ''
                    if not title or not slug or query.lower() not in title.lower():
                        continue
                    meta = item.get('meta') or {}
                    episodes = item.get('episodes') or meta.get('episodes') or '0'
                    types = item.get('type') or []
                    type_name = 'series'
                    for t in types:
                        tname = (t.get('name') or '').upper()
                        if 'MOVIE' in tname or 'SPECIAL' in tname:
                            type_name = 'movie'
                    results.append({
                        'title': title,
                        'slug': slug,
                        'type': type_name,
                        'episodes': int(episodes) if str(episodes).isdigit() else 0,
                        'provider': self.NAME,
                    })
        except Exception as e:
            print(f'[dorabash] search error: {e}')
        return results

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        eps = self.get_episodes(slug)
        return {
            'title': slug.replace('-', ' ').title(),
            'slug': slug,
            'type': 'series',
            'provider': self.NAME,
            'episodes': eps,
        }

    def get_episodes(self, slug):
        """Parse the series page for real episode links /watch/{slug}-episode-{n}/."""
        try:
            status, html = trawl_fetch(f'{BASE_URL}/series/{slug}/', max_timeout=45000)
            if status not in (200, 301) or not html:
                return []
            pattern = re.compile(r'/watch/{slug}-episode-(\d+)/'.format(slug=re.escape(slug)))
            seen = set()
            episodes = []
            for m in pattern.finditer(html):
                ep = int(m.group(1))
                if ep in seen:
                    continue
                seen.add(ep)
                episodes.append({
                    'season': 1,
                    'episode': ep,
                    'title': f'Episode {ep}',
                    'slug': slug,
                })
            episodes.sort(key=lambda x: x['episode'])
            return episodes
        except Exception as e:
            print(f'[dorabash] episodes error: {e}')
            return []

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            ep_url = f'{BASE_URL}/watch/{slug}-episode-{episode}/'
            status, html = trawl_fetch(ep_url, max_timeout=45000)
            if status != 200 or not html:
                return {'streams': []}

            streams = []

            # DoraBash uses filemoon mirrors (bysevepoin.com) and short.icu for multilang
            iframes = re.findall(r'<iframe[^>]+src="([^"]+)"', html, re.I)
            for i, src in enumerate(iframes):
                if src.startswith('//'):
                    src = 'https:' + src
                player = self._classify(src)
                streams.append({
                    'player': player,
                    'url': src,
                    'name': f'Server {i+1}',
                })

            # Look for Abyss/Hindi links (match inside href/src/quotes only)
            abyss = re.findall(r'(?:href|src)=["\']([^"\']*(?:abyss|short\.icu)[^"\']*)["\']', html, re.I)
            for a in abyss:
                if not a.startswith('http'):
                    a = 'https://' + a
                streams.append({'player': 'abyss', 'url': a, 'name': 'Abyss (Hindi)'})

            return {'streams': streams}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'filemoon' in u or 'byse' in u: return 'filemoon'
        if 'short.icu' in u: return 'shorticu'
        if 'abyss' in u: return 'abyss'
        if 'gdmirrorbot' in u: return 'gdmirrorbot'
        if 'p2pplay' in u or 'upns' in u: return 'streamp2p'
        if 'dood' in u: return 'dood'
        if 'vidmoly' in u: return 'vidmoly'
        return 'generic_embed'
