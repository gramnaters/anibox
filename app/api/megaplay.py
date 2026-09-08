"""
MegaPlay Direct provider - direct m3u8 URLs from megaplay.buzz.
Search resolves titles to AniList IDs (megaplay's slug convention) via AniList GraphQL.
"""
import requests, re, os, time
from urllib.parse import quote
from cachetools import TTLCache, cached

BASE_URL = 'https://megaplay.buzz'
ANILIST_URL = 'https://graphql.anilist.co'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 15

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


def _get_retry(session, url, headers=None, max_retries=4, timeout=25):
    """GET with backoff retry on 403/5xx/timeout (megaplay CDN is flaky)."""
    last = None
    for attempt in range(max_retries):
        try:
            r = session.get(url, headers=headers, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 429, 500, 502, 503, 504, 522, 524):
                time.sleep(1.5 * (attempt + 1))
                last = r
                continue
            return r
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    if isinstance(last, Exception):
        raise last
    return last


class MegaPlayProvider:
    NAME = 'megaplay'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query):
        """Resolve a title to an AniList ID (megaplay's slug convention)."""
        anilist_id = self._anilist_id_for_title(query)
        if not anilist_id:
            return []
        return [{
            'title': query,
            'slug': str(anilist_id),
            'poster': '',
            'type': 'series',
            'provider': self.NAME,
        }]

    def _anilist_id_for_title(self, title):
        try:
            r = requests.post(ANILIST_URL, json={
                'query': 'query($s: String){ Media(search: $s, type: ANIME) { id } }',
                'variables': {'s': title},
            }, headers={'User-Agent': UA, 'Content-Type': 'application/json'},
                timeout=TIMEOUT, verify=False)
            data = (r.json() or {})
            media = (data.get('data') or {}).get('Media') or {}
            return media.get('id')
        except Exception as e:
            print(f'[megaplay] anilist search error: {e}')
            return None

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        anilist_id = self._parse_anilist_id(slug)
        if not anilist_id:
            return None
        return {
            'title': slug,
            'slug': slug,
            'poster': '',
            'type': 'series',
            'provider': self.NAME,
            'episodes': self.get_episodes(slug),
        }

    def _parse_anilist_id(self, slug):
        if slug and str(slug).isdigit():
            return int(slug)
        m = re.search(r'-(\d+)$', str(slug or ''))
        return int(m.group(1)) if m else None

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': i, 'title': f'Episode {i}', 'slug': slug} for i in range(1, 300)]

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        anilist_id = self._parse_anilist_id(slug)
        if not anilist_id:
            return {'streams': []}

        streams = []
        for lang_type in ['sub', 'dub']:
            try:
                stream_url = f"{BASE_URL}/stream/ani/{anilist_id}/{episode}/{lang_type}?autostart=true"
                r = self.session.get(stream_url, headers={'User-Agent': UA, 'Referer': 'https://aniflix.us/'},
                                     timeout=TIMEOUT, verify=False)
                if r.status_code != 200:
                    continue
                m = re.search(r'data-id=["\'](\d+)["\']', r.text)
                if not m:
                    continue
                r2 = _get_retry(self.session, f"{BASE_URL}/stream/getSources?id={m.group(1)}",
                                headers={'User-Agent': UA, 'Referer': stream_url,
                                         'X-Requested-With': 'XMLHttpRequest'})
                if r2 is None or r2.status_code != 200:
                    continue
                data = r2.json()
                sources = data.get('sources', {})
                m3u8 = sources.get('file', '') if isinstance(sources, dict) else (
                    sources[0].get('file', '') if sources else '')
                if m3u8:
                    subtitles = []
                    for track in data.get('tracks', []) or []:
                        if not isinstance(track, dict):
                            continue
                        turl = track.get('file') or ''
                        if not turl:
                            continue
                        subtitles.append({
                            'id': track.get('id', turl),
                            'url': turl,
                            'lang': track.get('label') or track.get('kind') or 'Unknown',
                        })
                    streams.append({
                        'player': 'direct_m3u8',
                        'url': m3u8,
                        'name': f'MegaPlay {lang_type.upper()}',
                        'referer': 'https://megaplay.buzz/',
                        'subtitles': subtitles,
                    })
            except Exception as e:
                print(f'[megaplay] streams error: {e}')
        return {'streams': streams}
