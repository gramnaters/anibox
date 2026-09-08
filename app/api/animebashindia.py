"""
Anime Bash India provider (animebashindia.me).
Uses AniKoto API for search + details + sources.
9 servers: HD-1, Vidstream-2, VidPlay-1
"""
import requests, re, json, os
from urllib.parse import quote
from cachetools import TTLCache, cached

BASE_URL = 'https://animebashindia.me'
ANIKOTO_API = 'https://anikoto-api-f43e.vercel.app'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 15

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


class AnimeBashIndiaProvider:
    NAME = 'animebashindia'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query):
        results = []
        try:
            r = requests.get(f'{ANIKOTO_API}/api/search', params={'keyword': query},
                           headers={'User-Agent': UA}, timeout=TIMEOUT, verify=False)
            if r.status_code == 200:
                data = r.json()
                for item in data.get('data', {}).get('results', []):
                    slug = item.get('slug', '')
                    if slug:
                        results.append({
                            'title': item.get('title') or item.get('titleJp') or slug,
                            'slug': slug,
                            'poster': item.get('image', ''),
                            'type': 'series',
                            'provider': self.NAME,
                        })
        except Exception as e:
            print(f'[animebashindia] search error: {e}')
        return results

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        try:
            r = requests.get(f'{ANIKOTO_API}/api/anime/{slug}', headers={'User-Agent': UA},
                           timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return None
            data = r.json().get('data', {})
            ep_count = data.get('episodeCount') or 1
            episodes = []
            for i in range(1, min(ep_count + 1, 300)):
                episodes.append({
                    'season': 1, 'episode': i,
                    'title': f'Episode {i}',
                    'slug': slug,
                })
            return {
                'title': data.get('title') or slug,
                'slug': slug,
                'poster': data.get('image', ''),
                'type': 'series' if ep_count > 1 else 'movie',
                'provider': self.NAME,
                'episodes': episodes,
            }
        except:
            return None

    def get_episodes(self, slug):
        d = self.get_anime_details(slug)
        return d.get('episodes', []) if d else []

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            r = requests.get(f'{ANIKOTO_API}/api/watch/{slug}', params={'ep': episode},
                           headers={'User-Agent': UA}, timeout=30, verify=False)
            if r.status_code != 200:
                return {'streams': []}

            text = r.text.strip()
            sources = []
            if text.startswith('data:'):
                for line in text.split('\n'):
                    line = line.strip()
                    if not line.startswith('data:'):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                        if event.get('type') == 'source' and event.get('source'):
                            sources.append(event['source'])
                        elif event.get('type') == 'done':
                            break
                    except:
                        continue
            else:
                data = json.loads(text)
                sources = data.get('data', {}).get('sources', [])

            streams = []
            seen = set()
            for src in sources:
                server = src.get('server', 'Unknown')
                src_type = src.get('type', 'sub')
                m3u8 = src.get('m3u8', '')
                referer = src.get('referer', '')
                if not m3u8:
                    continue
                key = (server, src_type)
                if key in seen:
                    continue
                seen.add(key)

                player = self._classify_m3u8(m3u8, server)
                streams.append({
                    'player': player,
                    'url': m3u8,
                    'name': f'{server} ({src_type})',
                    'referer': referer,
                })

            return {'streams': streams}
        except Exception as e:
            print(f'[animebashindia] streams error: {e}')
            return {'streams': []}

    def _classify_m3u8(self, url, server):
        u = url.lower()
        if 'megaplay' in u or 'megap.' in u:
            return 'anistream'
        if 'vidnest' in u:
            return 'vidmaster'
        if 'vivibebe' in u:
            return 'vibeplayer'
        if 'as-cdn' in u or 'zephyr' in u:
            return 'fireplayer'
        if 'p2pplay' in u or 'upns' in u or 'rpmstream' in u:
            return 'streamp2p'
        if 'dood' in u:
            return 'dood'
        if 'vidmoly' in u:
            return 'vidmoly'
        if 'abyss' in u or 'short.icu' in u:
            return 'abyss'
        if 'streamtape' in u:
            return 'streamtape'
        if 'streamruby' in u or 'rubystm' in u:
            return 'streamruby'
        if '.m3u8' in u:
            return 'direct_m3u8'
        return 'generic_embed'
