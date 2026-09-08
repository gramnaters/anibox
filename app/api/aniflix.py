import requests, re, os, json
from cachetools import TTLCache, cached
from urllib.parse import quote

TRAWL_URL = os.getenv('TRAWL_URL', 'https://trawl.fly.dev')
BASE_URL = 'https://aniflix.us'
TIMEOUT = 90

_cf_cache = TTLCache(maxsize=512, ttl=300)

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=2048, ttl=600)


def _trawl(url):
    """Fetch URL through TRAWL CF bypass"""
    import time
    time.sleep(0.5)  # Rate limit
    try:
        r = requests.post(f'{TRAWL_URL}/v1',
            json={'cmd': 'request.get', 'url': url, 'maxTimeout': 60000},
            timeout=TIMEOUT)
        if r.status_code == 429:
            time.sleep(2)
            r = requests.post(f'{TRAWL_URL}/v1',
                json={'cmd': 'request.get', 'url': url, 'maxTimeout': 60000},
                timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            sol = data.get('solution', {})
            if sol.get('status') == 200:
                raw = sol.get('response', '')
                pre_match = re.search(r'<pre>(.*?)</pre>', raw, re.DOTALL)
                if pre_match:
                    return pre_match.group(1)
                return raw
        return ''
    except Exception as e:
        print(f'[aniflix] trawl error: {e}')
        return ''


def _classify_embed(url, name=''):
    u = url.lower()
    if 'gdmirrorbot' in u:
        return {'player': 'gdmirrorbot', 'url': url, 'name': f'{name} (GDMirror)'}
    elif 'abyss' in u:
        return {'player': 'abyss', 'url': url, 'name': f'{name} (Abyss)'}
    elif 'cloud.desidubanime' in u:
        return {'player': 'cloud', 'url': url, 'name': f'{name} (Cloud)'}
    elif 'vidmoly' in u:
        return {'player': 'vidmoly', 'url': url, 'name': f'{name} (VMoly)'}
    elif 'p2pplay' in u:
        return {'player': 'streamp2p', 'url': url, 'name': f'{name} (P2P)'}
    elif 'boosterx' in u:
        return {'player': 'generic_embed', 'url': url, 'name': f'{name} (PlayerX)'}
    elif '.m3u8' in u:
        return {'player': 'direct_m3u8', 'url': url, 'name': f'{name} (Direct)'}
    else:
        return {'player': 'generic_embed', 'url': url, 'name': name}


class AniflixProvider:
    NAME = 'aniflix'

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        url = f'{BASE_URL}/api/desidub?eng={quote(query)}&romaji={quote(query)}&ep=1'
        html = _trawl(url)
        if not html:
            return []

        try:
            data = json.loads(html) if isinstance(html, str) else html
            if data.get('success'):
                results = [{
                    'title': query,
                    'slug': quote(query),
                    'poster': '',
                    'type': 'series',
                    'provider': self.NAME,
                }]
                return results
        except:
            pass
        return []

    def get_home_catalog(self) -> list:
        return []

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        from urllib.parse import unquote
        title = unquote(slug)

        episodes = []
        for ep in range(1, 300):
            episodes.append({
                'season': 1, 'episode': ep,
                'title': f'Episode {ep}',
                'slug': slug,
                'data_title': title,
                'data_ep': str(ep),
            })

        return {
            'title': title, 'slug': slug, 'poster': '',
            'type': 'series', 'provider': self.NAME,
            'episodes': episodes,
        }

    def get_episodes(self, slug: str) -> list:
        details = self.get_anime_details(slug)
        return details.get('episodes', []) if details else []

    @cached(streams_cache)
    def get_episode_streams(self, slug: str, season: int, episode: int) -> dict:
        from urllib.parse import unquote
        title = unquote(slug)
        url = f'{BASE_URL}/api/desidub?eng={quote(title)}&romaji={quote(title)}&ep={episode}'
        html = _trawl(url)
        if not html:
            return {'streams': []}

        try:
            data = json.loads(html) if isinstance(html, str) else html
            if not data.get('success'):
                return {'streams': []}

            streams = []
            for srv in data.get('servers', []):
                embed_url = srv.get('embed', '')
                name = srv.get('name', 'Server')
                if embed_url:
                    streams.append(_classify_embed(embed_url, name))

            return {'streams': streams}
        except Exception as e:
            print(f'[aniflix] streams error: {e}')
            return {'streams': []}
