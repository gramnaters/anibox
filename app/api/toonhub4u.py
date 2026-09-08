"""
ToonHub4u provider (toonhub4u.co).
Download-only site - returns empty streams (gdmirrorbot links require browser).
"""
import requests, re, os
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached

BASE_URL = 'https://toonhub4u.co'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 15

search_cache = TTLCache(maxsize=512, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)


class ToonHub4uProvider:
    NAME = 'toonhub4u'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    @cached(search_cache)
    def search_anime(self, query):
        results = []
        try:
            r = self.session.get(f'{BASE_URL}/', params={'s': query}, timeout=TIMEOUT, verify=False)
            soup = BeautifulSoup(r.text, 'html.parser')
            seen = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                if BASE_URL in href and href.count('/') > 3:
                    slug = href.rstrip('/').split('/')[-1]
                    if slug in seen or len(slug) < 5:
                        continue
                    title = a.text.strip()
                    if not title or query.lower() not in title.lower():
                        continue
                    seen.add(slug)
                    results.append({
                        'title': title,
                        'slug': slug,
                        'type': 'series',
                        'provider': self.NAME,
                    })
        except:
            pass
        return results

    def get_home_catalog(self):
        return []

    def get_anime_details(self, slug):
        return {
            'title': slug.replace('-', ' ').title(),
            'slug': slug,
            'type': 'series',
            'provider': self.NAME,
            'episodes': [{'season': 1, 'episode': 1, 'title': slug, 'slug': slug}],
        }

    def get_episodes(self, slug):
        return [{'season': 1, 'episode': 1, 'title': slug, 'slug': slug}]

    @cached(streams_cache)
    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            r = self.session.get(f'{BASE_URL}/{slug}/', timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return {'streams': []}

            soup = BeautifulSoup(r.text, 'html.parser')
            streams = []
            seen_ids = set()

            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'gdmirrorbot.nl/file/' in href or 'gdmirrorbot.nl/embed/' in href:
                    embed_url = href.replace('/file/', '/embed/') if '/file/' in href else href
                    m = re.search(r'/embed/([^/?#]+)', embed_url)
                    if m:
                        file_id = m.group(1)
                        if file_id in seen_ids:
                            continue
                        seen_ids.add(file_id)
                        streams.append({
                            'player': 'gdmirrorbot',
                            'url': embed_url,
                            'name': 'GDMirror',
                        })
                        if len(streams) >= 10:
                            break

            return {'streams': streams}
        except:
            return {'streams': []}
