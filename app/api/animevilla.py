import requests, re, os, base64, json
from cachetools import TTLCache, cached
from urllib.parse import quote
from app.players.all_players import extract_hsastream

BASE_URL = 'https://animevilla.org'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
TIMEOUT = 15

SCRAPER_PROXY = os.getenv('SCRAPER_PROXY_URL', '')
SCRAPER_PROXY_PW = os.getenv('SCRAPER_PROXY_PASSWORD', '')

search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
episode_streams_cache = TTLCache(maxsize=2048, ttl=3600)


def _proxy_url(target):
    return f"{SCRAPER_PROXY}/proxy/stream?d={quote(target, safe='')}&api_password={SCRAPER_PROXY_PW}&h_user-agent={quote(UA, safe='')}"


class AnimeVillaProvider:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA, 'Accept': 'application/json'})

    def _get(self, url, **kwargs):
        target = _proxy_url(url) if SCRAPER_PROXY else url
        kwargs.setdefault('timeout', TIMEOUT)
        return self.session.get(target, **kwargs)

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        results = []
        try:
            resp = self._get(f'{BASE_URL}/wp-json/kiranime/v1/anime/title', params={'query': query})
            if resp.status_code != 200:
                return []
            for item in resp.json():
                title = item.get('title', '').strip()
                slug = item.get('slug', '')
                anime_id = item.get('id') or item.get('anime_id')
                if not title or not slug:
                    continue
                results.append({
                    'title': title, 'slug': slug, 'poster': '',
                    'type': 'series', 'provider': 'animevilla',
                    'anime_id': anime_id,
                })
        except Exception as e:
            print(f'[animevilla] search error: {e}')
        return results

    def get_home_catalog(self) -> list:
        return self.search_anime('')

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        try:
            resp = self._get(f'{BASE_URL}/wp-json/kiranime/v1/anime/title', params={'query': slug})
            if resp.status_code != 200:
                return None
            anime_list = resp.json()
            anime_data = next((a for a in anime_list if a.get('slug') == slug), anime_list[0] if anime_list else None)
            if not anime_data:
                return None

            anime_id = anime_data.get('id') or anime_data.get('anime_id')
            title = anime_data.get('title', slug)

            episodes = self._discover_episodes_from_watch_page(slug, title)

            return {
                'title': title, 'slug': slug, 'poster': '',
                'type': 'series', 'provider': 'animevilla',
                'anime_id': anime_id, 'episodes': episodes,
                'total_seasons': max((ep.get('season', 1) for ep in episodes), default=1),
            }
        except Exception as e:
            print(f'[animevilla] details error: {e}')
            return None

    def _discover_episodes_from_watch_page(self, anime_slug, anime_title):
        """Try to discover episodes by trying common watch page URL patterns"""
        episodes = []
        tried = set()

        patterns_to_try = [
            f'{anime_slug}-episode-1',
            f'{anime_slug}-ep-1',
            f'{anime_slug}-1',
            f'{anime_slug}-hindi-dubbed-episode-1',
        ]

        for pattern in patterns_to_try:
            if pattern in tried:
                continue
            tried.add(pattern)
            watch_url = f'{BASE_URL}/watch/{pattern}/'
            try:
                r = self._get(watch_url, headers={'Accept': 'text/html'})
                if r.status_code == 200 and 'episode-list' in r.text:
                    episodes = self._parse_episode_list(r.text)
                    if episodes:
                        break
            except:
                continue

        return episodes

    def _parse_episode_list(self, html):
        """Parse server-rendered episode list from watch page HTML"""
        episodes = []
        ep_links = re.findall(
            r'<a\s+href="([^"]*?/watch/[^"]*?)"[^>]*class="[^"]*episode-list-item[^"]*"[^>]*data-episode-search-query="([^"]*)"',
            html
        )
        for ep_url, ep_num_str in ep_links:
            try:
                ep_num = int(ep_num_str)
            except ValueError:
                ep_num = len(episodes) + 1

            ep_slug = ep_url.rstrip('/').split('/watch/')[-1]
            episodes.append({
                'season': 1,
                'episode': ep_num,
                'title': f'Episode {ep_num}',
                'slug': ep_slug,
                'ep_page_url': ep_url if ep_url.startswith('http') else BASE_URL + ep_url,
            })

        if not episodes:
            ep_links_simple = re.findall(r'href="([^"]*?/watch/[^"]*?)"[^>]*episode-list', html)
            for i, ep_url in enumerate(ep_links_simple):
                ep_slug = ep_url.rstrip('/').split('/watch/')[-1]
                episodes.append({
                    'season': 1,
                    'episode': i + 1,
                    'title': f'Episode {i+1}',
                    'slug': ep_slug,
                    'ep_page_url': ep_url if ep_url.startswith('http') else BASE_URL + ep_url,
                })

        return episodes

    def get_episodes(self, slug: str) -> list:
        details = self.get_anime_details(slug)
        return details.get('episodes', []) if details else []

    @cached(episode_streams_cache)
    def _get_episode_streams(self, ep_page_url: str) -> list:
        streams = []
        try:
            resp = self._get(ep_page_url, headers={'Accept': 'text/html'})
            if resp.status_code != 200:
                return []
            html = resp.text

            hsastream_ids = re.findall(r'https?://hsastream\.com/#([A-Za-z0-9]+)', html)
            for video_id in hsastream_ids:
                embed_url = f'https://hsastream.com/#{video_id}'
                result = extract_hsastream(embed_url)
                for s in result.get('streams', []):
                    s['name'] = f'AV/{s.get("name", "Stream")}'
                    streams.append(s)

            if not streams:
                iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
                for iframe_url in iframes:
                    if 'hsastream' in iframe_url:
                        result = extract_hsastream(iframe_url)
                        for s in result.get('streams', []):
                            s['name'] = f'AV/{s.get("name", "Stream")}'
                            streams.append(s)

            if not streams:
                embed_ids = re.findall(r'data-embed-id=["\']([^"\']+)["\']', html)
                for eid in embed_ids:
                    try:
                        decoded = base64.b64decode(eid).decode('utf-8')
                        if 'hsastream' in decoded:
                            url_match = re.search(r'https?://hsastream\.com[#/]*([A-Za-z0-9]+)', decoded)
                            if url_match:
                                result = extract_hsastream(f'https://hsastream.com/#{url_match.group(1)}')
                                for s in result.get('streams', []):
                                    s['name'] = f'AV/{s.get("name", "Stream")}'
                                    streams.append(s)
                    except:
                        pass

        except Exception as e:
            print(f'[animevilla] episode scrape error: {e}')
        return streams

    def get_episode_streams(self, slug: str, season: int, episode: int) -> dict:
        details = self.get_anime_details(slug)
        if not details:
            return {'streams': []}

        eps = details.get('episodes', [])
        ep_data = None
        for ep in eps:
            if ep.get('episode') == episode and ep.get('season', 1) == season:
                ep_data = ep
                break
        if not ep_data and eps:
            ep_data = eps[episode - 1] if episode <= len(eps) else None
        if not ep_data:
            return {'streams': []}

        ep_page_url = ep_data.get('ep_page_url', '')
        if not ep_page_url:
            return {'streams': []}

        streams = self._get_episode_streams(ep_page_url)
        return {'streams': streams}
