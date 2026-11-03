"""
ScreenScape provider (screenscape.me).

ScreenScape is a TMDB-id resolver: give it a tmdb id + type + season/episode and
it returns direct HLS streams. The public, unencrypted API is the "qsply" server:

    GET /api/servers/qsply?id={tmdb}&type={tv|movie}&s={season}&e={episode}
    -> {"success": true, "streams": [ { "url": "/api/servers/qsply/proxy?url=<m3u8>",
                                        "quality", "language", "provider", ... } ]}

Stream URLs are served through the site's own proxy (the underlying CDN needs a
referer), so we return the proxy URL directly and set a Referer header.

Search is TMDB-backed (the site indexes by tmdb id), same pattern as nxsha.py.
"""
import re

import requests
from cachetools import TTLCache, cached

BASE_URL = 'https://screenscape.me'
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


class ScreenScapeProvider:
    NAME = 'screenscape'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def _qsply(self, tmdb_id, media_type, season=None, episode=None):
        params = {'id': str(tmdb_id), 'type': media_type}
        if media_type == 'tv':
            params['s'] = season or 1
            params['e'] = episode or 1
        r = self.session.get(f'{BASE_URL}/api/servers/qsply', params=params,
                             headers={'Referer': f'{BASE_URL}/'},
                             timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get('streams') or []

    def _has_title(self, tmdb_id, media_type, season=None, episode=None):
        try:
            return bool(self._qsply(tmdb_id, media_type, season, episode))
        except Exception:
            return False

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        key = _tmdb_key()
        if not key:
            return []
        results = []
        try:
            r = requests.get('https://api.themoviedb.org/3/search/multi',
                             params={'api_key': key, 'query': query},
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            for item in (r.json().get('results') or []):
                mtype = item.get('media_type')
                if mtype not in ('movie', 'tv'):
                    continue
                tmdb_id = str(item.get('id') or '')
                name = item.get('title') or item.get('name') or ''
                if not tmdb_id or not name:
                    continue
                if query.lower() not in name.lower():
                    continue
                results.append({
                    'title': name,
                    'slug': tmdb_id,
                    'poster': f'https://image.tmdb.org/t/p/w300{item.get("poster_path") or ""}',
                    'type': 'movie' if mtype == 'movie' else 'series',
                    'provider': self.NAME,
                })
        except Exception as e:
            print(f'[screenscape] search error: {e}')
        return results[:10]

    def get_home_catalog(self) -> list:
        return []

    def get_anime_details(self, slug: str) -> dict:
        # slug is a bare tmdb id; we can't tell movie vs series without probing.
        # Probe qsply for tv first, then movie.
        if not str(slug or '').isdigit():
            return None
        if self._has_title(slug, 'tv', 1, 1):
            kind = 'series'
        else:
            kind = 'movie'
        return {
            'title': f'ScreenScape {slug}',
            'slug': slug,
            'poster': '',
            'type': kind,
            'provider': self.NAME,
            'episodes': self.get_episodes(slug) if kind == 'series'
                        else [{'season': 1, 'episode': 1, 'title': slug, 'slug': slug}],
        }

    def get_episodes(self, slug: str) -> list:
        return [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug}
                for i in range(1, 300)]

    @cached(streams_cache)
    def get_episode_streams(self, slug: str, season: int = 1, episode: int = 1) -> dict:
        if not str(slug or '').isdigit():
            return {'streams': []}
        streams = []
        try:
            # Probe tv first (this is an anime addon); fall back to movie.
            sources = self._qsply(slug, 'tv', season, episode)
            if not sources:
                sources = self._qsply(slug, 'movie', None, None)
            for src in sources:
                url = src.get('url') or ''
                if not url:
                    continue
                # Only keep clean, playable URLs: the site's own proxy URL, or a
                # direct .m3u8. Skip hex/"Auto" alternates that need JS decoding.
                if '/api/servers/qsply/proxy' not in url and '.m3u8' not in url:
                    continue
                label = src.get('quality') or src.get('language') or ''
                streams.append({
                    'player': 'direct_m3u8',
                    'url': url,
                    'name': f'{src.get("provider") or "ScreenScape"} {label}'.strip(),
                    'referer': f'{BASE_URL}/',
                    'headers': {'Referer': f'{BASE_URL}/', 'Origin': BASE_URL},
                })
        except Exception as e:
            print(f'[screenscape] streams error: {e}')
        # dedupe
        seen = set()
        unique = []
        for s in streams:
            if s['url'] in seen:
                continue
            seen.add(s['url'])
            unique.append(s)
        return {'streams': unique}
