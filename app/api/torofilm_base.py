# Generic WordPress torofilm theme API (used by watchanimeworld, animesalt, animejoker)
import requests, re, random, os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from cachetools import TTLCache, cached

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

TIMEOUT = 15
search_cache = TTLCache(maxsize=512, ttl=3600)
details_cache = TTLCache(maxsize=1024, ttl=3600)
streams_cache = TTLCache(maxsize=512, ttl=600)

class TorofilmAPI:
    BASE_URL = ''
    NAME = ''
    SCRAPER_PROXY = os.getenv('SCRAPER_PROXY_URL', '')

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
        })

    def _get(self, url, **kwargs):
        self.session.headers['User-Agent'] = random.choice(_USER_AGENTS)
        kwargs.setdefault('timeout', TIMEOUT)
        if self.SCRAPER_PROXY:
            return self.session.get(self._proxy_url(url), **kwargs)
        return self.session.get(url, **kwargs)

    def _post(self, url, **kwargs):
        self.session.headers['User-Agent'] = random.choice(_USER_AGENTS)
        kwargs.setdefault('timeout', TIMEOUT)
        if self.SCRAPER_PROXY:
            return self.session.post(self._proxy_url(url), **kwargs)
        return self.session.post(url, **kwargs)

    def _proxy_url(self, target_url):
        pw = os.getenv('SCRAPER_PROXY_PASSWORD', '')
        ua = self.session.headers.get('User-Agent', '')
        return f"{self.SCRAPER_PROXY}/proxy/stream?d={quote(target_url,safe='')}&api_password={pw}&h_user-agent={quote(ua,safe='')}"

    @cached(search_cache)
    def search_anime(self, query: str) -> list:
        try:
            resp = self._get(f'{self.BASE_URL}/', params={'s': query})
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for article in soup.select('article, .item, .post'):
                link = article.select_one('a[href*="/series/"], a[href*="/movies/"], a[href*="/episode/"]')
                img = article.find('img')
                title = article.select_one('h2, h3, .entry-title')
                if link:
                    href = link.get('href', '')
                    slug = href.rstrip('/').split('/')[-1]
                    content_type = 'movie' if '/movies/' in href else 'series'
                    results.append({
                        'title': title.text.strip() if title else (img.get('alt', '') if img else slug),
                        'slug': slug,
                        'poster': img.get('src', '').replace('//', 'https://') if img else None,
                        'type': content_type,
                        'provider': self.NAME,
                    })
            return results
        except Exception as e:
            print(f'[{self.NAME}] search error: {e}')
            return []

    def get_home_catalog(self) -> list:
        try:
            resp = self._get(self.BASE_URL)
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for article in soup.select('article'):
                link = article.select_one('a[href]')
                img = article.find('img')
                title = article.select_one('h2, h3, .entry-title')
                if link:
                    href = link.get('href', '')
                    parts = href.rstrip('/').split('/')
                    slug = parts[-1] if parts else ''
                    results.append({
                        'title': title.text.strip() if title else (img.get('alt', '') if img else slug),
                        'slug': slug,
                        'poster': img.get('src', '').replace('//', 'https://') if img else None,
                        'type': 'movie' if '/movies/' in href else 'series',
                        'provider': self.NAME,
                    })
            return results
        except Exception as e:
            print(f'[{self.NAME}] home error: {e}')
            return []

    @cached(details_cache)
    def get_anime_details(self, slug: str) -> dict:
        for content_type in ['series', 'movies']:
            try:
                url = f'{self.BASE_URL}/{content_type}/{slug}'
                resp = self._get(url)
                if resp.status_code == 404: continue
                soup = BeautifulSoup(resp.text, 'html.parser')
                title = soup.select_one('h1, .entry-title')
                description = soup.select_one('.description p, .entry-content p')
                poster = soup.select_one('article.post img, .poster img')
                genres = [g.text.strip() for g in soup.select('.genres a, .categories a')]

                episodes = []
                if content_type == 'series':
                    for i, li in enumerate(soup.select('#episode_by_temp li, li[data-post], .episodes-list li')):
                        data_post = li.get('data-post', '')
                        data_nume = li.get('data-nume', str(i + 1))
                        data_type = li.get('data-type', 'tv')
                        ep_link = li.find('a')
                        ep_href = ep_link.get('href', '') if ep_link else ''
                        ep_title = ep_link.text.strip() if ep_link else f'Episode {i+1}'

                        match = re.match(r'(\d+)x(\d+)', ep_title)
                        if match:
                            season = int(match.group(1))
                            ep_num = int(match.group(2))
                        else:
                            season = 1
                            ep_num = i + 1

                        ep_page_url = ep_href if ep_href.startswith('http') else urljoin(url, ep_href) if ep_href else ''

                        episodes.append({
                            'season': season, 'episode': ep_num,
                            'title': ep_title,
                            'data_post': data_post, 'data_nume': data_nume,
                            'data_type': data_type, 'url': url, 'slug': slug,
                            'ep_page_url': ep_page_url,
                        })

                    if not episodes:
                        for i in range(1, 13):
                            ep_slug = f'{slug}-{i}'
                            ep_page_url = f'{self.BASE_URL}/episode/{ep_slug}/'
                            episodes.append({
                                'season': 1, 'episode': i,
                                'title': f'Episode {i}',
                                'data_post': slug, 'data_nume': str(i),
                                'data_type': 'tv', 'url': url, 'slug': slug,
                                'ep_page_url': ep_page_url,
                            })
                else:
                    episodes.append({
                        'season': 1, 'episode': 1, 'title': 'Movie',
                        'url': url, 'slug': slug,
                    })

                return {
                    'title': title.text.strip() if title else '',
                    'slug': slug, 'description': description.text.strip() if description else '',
                    'poster': poster.get('src', '').replace('//', 'https://') if poster else '',
                    'genres': genres, 'episodes': episodes,
                    'type': 'movie' if content_type == 'movies' else 'series',
                    'provider': self.NAME,
                }
            except: continue
        return None

    def get_episodes(self, slug: str) -> list:
        details = self.get_anime_details(slug)
        return details.get('episodes', []) if details else []

    def get_episode_streams(self, slug: str, season: int, episode: int) -> dict:
        details = self.get_anime_details(slug)
        if not details: return {'streams': []}

        eps = details.get('episodes', [])
        ep_data = None
        for ep in eps:
            if ep.get('episode') == episode and ep.get('season', 1) == season:
                ep_data = ep
                break
        if not ep_data and eps:
            ep_data = eps[episode - 1] if episode <= len(eps) else None
        if not ep_data: return {'streams': []}

        streams = []
        data_post = ep_data.get('data_post', '')
        data_nume = ep_data.get('data_nume', str(episode))

        if data_post:
            try:
                resp = self._post(
                    f'{self.BASE_URL}/wp-admin/admin-ajax.php',
                    data={
                        'action': 'doo_player_ajax',
                        'post': data_post,
                        'nume': data_nume,
                        'type': ep_data.get('data_type', 'tv'),
                    },
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': f'{self.BASE_URL}/',
                    }
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        tabs = []
                        if data.get('embed_url'):
                            tabs.append({'name': 'Default', 'url': data['embed_url']})
                        if data.get('embed'):
                            tabs.append({'name': 'Default', 'url': data['embed']})
                        if data.get('tabs'):
                            for key, val in data['tabs'].items():
                                tabs.append({
                                    'name': val.get('title', key),
                                    'url': val.get('embed_url') or val.get('embed', ''),
                                })

                        for tab in tabs:
                            if not tab['url']: continue
                            streams.append(self._classify_stream(tab['url'], tab['name']))
                    except: pass
            except Exception as e:
                print(f'[{self.NAME}] AJAX error: {e}')

        # Also try to find iframes directly from episode page
        if not streams:
            try:
                ep_page_url = ep_data.get('ep_page_url', '')
                if not ep_page_url:
                    ep_page_url = ep_data.get('url', f'{self.BASE_URL}/series/{slug}')
                resp = self._get(ep_page_url)
                soup = BeautifulSoup(resp.text, 'html.parser')
                for iframe in soup.find_all('iframe'):
                    src = iframe.get('src') or iframe.get('data-src', '')
                    if src:
                        streams.append(self._classify_stream(src, 'Direct'))
            except: pass

        return {'streams': streams}

    def _classify_stream(self, url: str, name: str) -> dict:
        url_lower = url.lower()
        if 'zephyr' in url_lower:
            return {'player': 'zephyrflick', 'url': url, 'name': f'{name} (Zephyr)', 'languages': []}
        elif 'gdmirrorbot' in url_lower:
            return {'player': 'gdmirrorbot', 'url': url, 'name': f'{name} (GDMirror)', 'languages': []}
        elif 'vidmoly' in url_lower:
            return {'player': 'vidmoly', 'url': url, 'name': f'{name} (VMoly)', 'languages': []}
        elif 'abyss' in url_lower:
            return {'player': 'abyss', 'url': url, 'name': f'{name} (Abyss)', 'languages': []}
        elif 'streamruby' in url_lower:
            return {'player': 'streamruby', 'url': url, 'name': f'{name} (StreamRuby)', 'languages': []}
        elif 'dood' in url_lower:
            return {'player': 'doodstream', 'url': url, 'name': f'{name} (Dood)', 'languages': []}
        elif 'p2pplay' in url_lower or 'strp' in url_lower:
            return {'player': 'streamp2p', 'url': url, 'name': f'{name} (P2P)', 'languages': []}
        elif 'turbovid' in url_lower:
            return {'player': 'turbovid', 'url': url, 'name': f'{name} (Turbo)', 'languages': []}
        elif '.m3u8' in url_lower:
            return {'player': 'direct_m3u8', 'url': url, 'name': f'{name} (Direct)', 'languages': []}
        else:
            return {'player': 'generic_embed', 'url': url, 'name': name, 'languages': []}
