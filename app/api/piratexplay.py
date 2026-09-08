"""
PirateXPlay provider (piratexplay.cc).
Servers: HD (Multi), SHORT (Multi), VIDSTREAMING (Multi), GDMIRRORBOT (Multi).
Uses bashapi.tech API for search + details.
"""
import requests, re, json, os
from urllib.parse import quote
from cachetools import TTLCache, cached

BASE_URL = 'https://piratexplay.cc'
BASHAPI_BASE = 'https://ind.bashapi.tech'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 15

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


class PirateXPlayProvider:
    NAME = 'piratexplay'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query):
        results = []
        try:
            if query.strip():
                r = requests.get(f'{BASHAPI_BASE}/search/{quote(query, safe="")}',
                               headers={'User-Agent': UA}, timeout=TIMEOUT, verify=False)
            else:
                r = requests.get(f'{BASHAPI_BASE}/home', headers={'User-Agent': UA},
                               timeout=TIMEOUT, verify=False)
            data = r.json()
            if not data.get('success'):
                return []

            seen = set()
            search_data = data.get('data', {})
            items = search_data.get('data', []) if isinstance(search_data, dict) else []
            if not items:
                for section in search_data.get('main', []) if isinstance(search_data, dict) else []:
                    items.extend(section.get('data', []))

            for item in items:
                slug = item.get('slug', '')
                base_slug = re.sub(r'-\d+x\d+$', '', slug)
                if base_slug in seen:
                    continue
                title = item.get('title', '')
                if not title:
                    continue
                if query.strip() and query.lower() not in title.lower():
                    continue
                url = item.get('url', '')
                seen.add(base_slug)
                content_type = 'movie' if '/movies/' in url else item.get('type', 'series')
                results.append({
                    'title': title,
                    'slug': base_slug,
                    'poster': item.get('poster', ''),
                    'type': content_type,
                    'provider': self.NAME,
                })
        except:
            pass
        return results

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        try:
            r = requests.get(f'{BASHAPI_BASE}/series/info/{slug}', headers={'User-Agent': UA},
                           timeout=TIMEOUT, verify=False)
            data = r.json()
            if not data.get('success'):
                return None
            d = data.get('data', {})
            episodes = []
            for season in d.get('seasons', []):
                sn = season.get('season_no', 1)
                for ep in season.get('episodes', []):
                    episodes.append({
                        'season': sn,
                        'episode': ep.get('episode_no', 1),
                        'title': ep.get('title', ''),
                        'slug': ep.get('slug', ''),
                    })
            if not episodes:
                episodes = [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug} for i in range(1, 300)]
            return {
                'title': d.get('title', slug),
                'slug': slug,
                'poster': d.get('poster', ''),
                'type': 'series',
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
            # PirateXPlay uses bashapi.tech for streams.
            # Series slug may need episode suffix: {slug}-{season}x{episode}
            target = slug
            try:
                info = requests.get(f'{BASHAPI_BASE}/series/info/{slug}',
                                    headers={'User-Agent': UA}, timeout=max(TIMEOUT, 45), verify=False).json()
                if info.get('success'):
                    for s in info.get('data', {}).get('seasons', []):
                        if s.get('season_no') != season:
                            continue
                        for ep in s.get('episodes', []):
                            if ep.get('episode_no') == episode:
                                target = ep.get('slug', slug)
                                break
                        break
            except:
                pass

            r = requests.get(f'{BASHAPI_BASE}/episode/sources/{target}',
                             timeout=max(TIMEOUT, 45), verify=False)
            if r.status_code != 200:
                return {'streams': []}
            data = r.json()
            if not data.get('success'):
                return {'streams': []}

            streams = []
            # Direct m3u8 sources
            for src in data.get('data', {}).get('sources', []):
                url = src.get('url', '')
                if url:
                    streams.append({
                        'player': 'direct_m3u8',
                        'url': url,
                        'name': src.get('label', 'Direct'),
                    })

            # Embed sources
            for embed in data.get('data', {}).get('embeds', []):
                if embed.startswith('//'):
                    embed = 'https:' + embed
                player = self._classify(embed)
                streams.append({
                    'player': player,
                    'url': embed,
                    'name': player.replace('_', ' ').title(),
                })

            return {'streams': streams}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'gdmirrorbot' in u: return 'gdmirrorbot'
        if 'as-cdn' in u or 'zephyr' in u: return 'fireplayer'
        if 'cloudy.upns' in u or 'p2pplay' in u: return 'streamp2p'
        if 'vidmoly' in u: return 'vidmoly'
        if 'abyssplayer' in u or 'player.abyss' in u: return 'abyss'
        if 'emturbovid' in u or 'turbovid' in u: return 'turbovid'
        if 'short.icu' in u: return 'shorticu'
        if 'streamruby' in u or 'rubystm' in u: return 'streamruby'
        if 'dood' in u: return 'dood'
        return 'generic_embed'
