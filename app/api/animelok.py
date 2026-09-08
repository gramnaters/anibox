import requests, re, json, os
from bs4 import BeautifulSoup
from urllib.parse import quote
from cachetools import TTLCache, cached

BASE_URL = 'https://animelok.live'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 15

SCRAPER_PROXY = os.getenv('SCRAPER_PROXY_URL', '')
SCRAPER_PROXY_PW = os.getenv('SCRAPER_PROXY_PASSWORD', '')

def _proxy_url(target):
    return f"{SCRAPER_PROXY}/proxy/stream?d={quote(target,safe='')}&api_password={SCRAPER_PROXY_PW}&h_user-agent={quote(UA,safe='')}"

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)

class AnimeLokAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': UA,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def _get(self, url, **kwargs):
        target = _proxy_url(url) if SCRAPER_PROXY else url
        kwargs.setdefault('timeout', TIMEOUT)
        return self.session.get(target, **kwargs)

    def _proxy_url(self, target):
        return f"{SCRAPER_PROXY}/proxy/stream?d={quote(target,safe='')}&api_password={SCRAPER_PROXY_PW}&h_user-agent={quote(UA,safe='')}"

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        results = []
        try:
            resp = self._get(f'{BASE_URL}/home', timeout=TIMEOUT)
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.select('a[href*="/anime/"]'):
                href = a.get('href', '')
                if '/cover/' in href: continue
                path = href.split('/anime/')[-1]
                if not path: continue
                slug_match = re.match(r'^(.+)-(\d+)$', path)
                slug = slug_match.group(1) if slug_match else path
                anilist_id = slug_match.group(2) if slug_match else None
                title = (a.find('img') or {}).get('alt', '') or a.get_text(strip=True)
                poster = (a.find('img') or {}).get('src', '')
                if not title or len(title) < 2: continue
                if query.lower() not in title.lower(): continue
                results.append({
                    'title': title, 'slug': path,
                    'anilist_id': anilist_id, 'poster': poster, 'type': 'series',
                    'provider': 'animelok',
                })
        except Exception as e:
            print(f'[animelok] search error: {e}')
        return results

    def get_home_catalog(self) -> list:
        return self.search_anime('')  # all anime

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        try:
            resp = self._get(f'{BASE_URL}/api/anime/{slug}/episodes/1', timeout=TIMEOUT)
            if resp.status_code != 200: return None
            data = resp.json()
            anime = data.get('anime', data)
            title = anime.get('title', '')
            anilist_id = anime.get('anilistId', anime.get('id'))

            # Get actual episode count from episodes-range API
            episodes = []
            try:
                range_resp = self._get(f'{BASE_URL}/api/anime/{slug}/episodes-range?page=0&lang=HINDI&pageSize=200', timeout=TIMEOUT)
                if range_resp.status_code == 200:
                    range_data = range_resp.json()
                    episodes_data = range_data.get('episodes', range_data.get('data', []))
                    if isinstance(episodes_data, list) and episodes_data:
                        for ep in episodes_data:
                            ep_num = ep.get('number', ep.get('episodeNumber', ep.get('episode', 0)))
                            season_num = ep.get('season', 1)
                            ep_title = ep.get('title', f'Episode {ep_num}')
                            episodes.append({
                                'season': season_num, 'episode': ep_num,
                                'title': ep_title, 'slug': slug, 'ep_num': ep_num,
                            })
            except: pass

            if not episodes:
                for i in range(1, 13):
                    episodes.append({'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug})

            return {
                'title': title,
                'slug': slug,
                'anilist_id': anilist_id,
                'poster': anime.get('poster', ''),
                'type': 'series',
                'provider': 'animelok',
                'episodes': episodes,
            }
        except Exception as e:
            print(f'[animelok] details error: {e}')
            return None

    def get_episodes(self, slug: str) -> list:
        """Returns all episodes using the episodes-range API"""
        try:
            # Try episodes-range API first (returns all episodes at once)
            resp = self._get(f'{BASE_URL}/api/anime/{slug}/episodes-range?page=0&lang=HINDI&pageSize=200', timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                episodes_data = data.get('episodes', data.get('data', []))
                if isinstance(episodes_data, list) and episodes_data:
                    episodes = []
                    for ep in episodes_data:
                        ep_num = ep.get('number', ep.get('episodeNumber', ep.get('episode', 0)))
                        season_num = ep.get('season', 1)
                        ep_title = ep.get('title', f'Episode {ep_num}')
                        episodes.append({
                            'season': season_num,
                            'episode': ep_num,
                            'title': ep_title,
                            'slug': slug,
                            'ep_num': ep_num,
                        })
                    if episodes:
                        return episodes

            # Fallback: try to get from episode 1 and generate
            resp = self._get(f'{BASE_URL}/api/anime/{slug}/episodes/1', timeout=TIMEOUT)
            if resp.status_code != 200: return []
            data = resp.json()
            anime = data.get('anime', data)
            total = anime.get('totalEpisodes', anime.get('episodesCount', 12))

            episodes = []
            for i in range(1, total + 1):
                episodes.append({
                    'season': 1, 'episode': i,
                    'title': f'Episode {i}',
                    'slug': slug, 'ep_num': i,
                })
            return episodes
        except Exception as e:
            print(f'[animelok] episodes error: {e}')
            return []

    def get_episode_streams(self, slug: str, season: int, episode: int) -> dict:
        try:
            resp = self._get(f'{BASE_URL}/api/anime/{slug}/episodes/{episode}', timeout=TIMEOUT)
            if resp.status_code != 200: return {'streams': []}
            data = resp.json()
            ep_data = data.get('episode', data)
            servers = ep_data.get('servers', [])

            streams = []
            for srv in servers:
                url = srv.get('url', '')
                name = srv.get('name', 'Server')
                tip = srv.get('tip', '')
                langs = srv.get('languages', [])

                if not url: continue

                # Pahe JSON array/dict OR malformed (MUST be checked FIRST before m3u8)
                if isinstance(url, str) and (url.startswith('[') or url.startswith('{') or '"url"' in url):
                    try:
                        if url.startswith('[') or url.startswith('{'):
                            parsed = json.loads(url)
                            items = parsed if isinstance(parsed, list) else [parsed]
                        else:
                            # Malformed: try regex extract
                            match = re.search(r'"url"\s*:\s*"([^"]*\.m3u8[^"]*)"', url)
                            items = [{'url': match.group(1)}] if match else []
                        for pu in items:
                            pu_url = pu.get('url', '')
                            if '.m3u8' in pu_url:
                                streams.append({
                                    'player': 'direct_m3u8',
                                    'url': pu_url,
                                    'name': f'Pahe ({name})',
                                    'languages': langs,
                                })
                        continue
                    except: pass

                # Direct m3u8 (Bato)
                if isinstance(url, str) and '.m3u8' in url:
                    streams.append({
                        'player': 'direct_m3u8',
                        'url': url,
                        'name': f'{name} ({tip})',
                        'languages': langs,
                    })
                # Abyss (short.icu redirect)
                elif isinstance(url, str) and 'short.icu' in url:
                    streams.append({
                        'player': 'abyss',
                        'url': url,
                        'name': f'{name} (Abyss)',
                        'languages': langs,
                    })
                # ZephyrFlick multi
                elif isinstance(url, str) and 'zephyr' in url.lower():
                    streams.append({
                        'player': 'zephyrflick',
                        'url': url,
                        'name': f'{name} (Multi)',
                        'languages': langs,
                    })
                # Other embed
                elif isinstance(url, str):
                    streams.append({
                        'player': 'generic_embed',
                        'url': url,
                        'name': f'{name} ({tip})',
                        'languages': langs,
                    })

            # Also get Flixcloud servers
            anime_data = data.get('anime', data)
            anilist_id = anime_data.get('anilistId', anime_data.get('id'))
            if anilist_id:
                try:
                    flix_resp = self._get(f'{BASE_URL}/api/flix/{anilist_id}/{episode}', timeout=TIMEOUT)
                    if flix_resp.status_code == 200:
                        flix_data = flix_resp.json()
                        for sv in flix_data.get('servers', []):
                            streams.append({
                                'player': 'flixcloud',
                                'url': sv.get('dataLink', ''),
                                'name': f"{sv.get('serverName', 'HD')} ({sv.get('dataType', '')})",
                                'languages': [],
                            })
                except: pass

            return {'streams': streams}
        except Exception as e:
            print(f'[animelok] streams error: {e}')
            return {'streams': []}
