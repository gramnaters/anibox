"""
AniMoye provider (animoye.com).
Streams via iqsmartgames: watch page -> embed key -> myseriesapi (fileslugs)
-> embedhelper2 (sources + mresult) -> sub-host URLs -> player modules.
Search uses TMDB (site search is JS/anti-bot protected) + watch-page probe.
"""
import requests, re
from cachetools import TTLCache, cached

from app.api.iqsmart_common import resolve_tv

BASE_URL = 'https://animoye.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')
TIMEOUT = 15

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _tmdb_key():
    try:
        from config import Config
        return Config.TMDB_API_KEY or ''
    except Exception:
        return ''


class AniMoyeProvider:
    NAME = 'animoye'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query):
        """Site search is bot-protected; use TMDB search + watch-page probe."""
        results = []
        try:
            r = requests.get('https://api.themoviedb.org/3/search/tv',
                             params={'api_key': _tmdb_key(), 'query': query},
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            for item in (r.json().get('results') or [])[:4]:
                tmdb_id = str(item.get('id') or '')
                name = item.get('name') or ''
                if not tmdb_id or not name:
                    continue
                if query.lower() not in name.lower():
                    continue
                if self._exists_on_site(tmdb_id):
                    results.append({
                        'title': name,
                        'slug': tmdb_id,
                        'poster': '',
                        'type': 'series',
                        'provider': self.NAME,
                    })
                    break
        except Exception as e:
            print(f'[animoye] search error: {e}')
        return results

    def _exists_on_site(self, tmdb_id):
        try:
            r = self.session.get(f'{BASE_URL}/watch/tv/{tmdb_id}/1/1', timeout=TIMEOUT, verify=False)
            return r.status_code == 200
        except Exception:
            return False

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return {
            'title': f'AniMoye {slug}',
            'slug': slug,
            'type': 'series',
            'provider': self.NAME,
            'episodes': self.get_episodes(slug),
        }

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug} for i in range(1, 300)]

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        tmdb_id = self._tmdb_from_slug(slug)
        if not tmdb_id:
            return {'streams': []}
        try:
            my_key = self._get_embed_key(tmdb_id, season, episode)
            if not my_key:
                return {'streams': []}
            return {'streams': resolve_tv(tmdb_id, season, episode, my_key)}
        except Exception as e:
            print(f'[animoye] episode streams error: {e}')
            return {'streams': []}

    def _tmdb_from_slug(self, slug):
        if slug and str(slug).isdigit():
            return str(slug)
        # legacy slug like "naruto.html" -> scrape tmdb id from series page
        try:
            r = self.session.get(f'{BASE_URL}/series/{slug}', timeout=TIMEOUT, verify=False)
            if r.status_code == 200:
                m = re.search(r'/watch/tv/(\d+)', r.text)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return None

    def _get_embed_key(self, tmdb_id, season, episode):
        wurl = f'{BASE_URL}/watch/tv/{tmdb_id}/{season}/{episode}'
        r = self.session.get(wurl, timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return None
        m = re.search(r'streams\.iqsmartgames\.com/embed/tv/\d+/\d+/\d+\?key=([A-Za-z0-9_-]+)', r.text)
        return m.group(1) if m else None
