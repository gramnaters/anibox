"""
Full reverse-engineered providers with direct API calls.
"""
import requests, re, json, time, hashlib, base64, os
from urllib.parse import quote, urlparse

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
TIMEOUT = 15


# ========== WATCHANIMEWORLD / ANIMESALT / ANIMEJOKER (Torofilm WordPress) ==========
# WordPress AJAX based

class TorofilmDirect:
    NAME = 'torofilm'
    BASE_URL = ''
    TRAWL_URL = os.getenv('TRAWL_URL', 'https://trawl.fly.dev')

    def __init__(self, base_url, name):
        self.BASE_URL = base_url
        self.NAME = name
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def _trawl_fetch(self, url):
        """Fetch URL through TRAWL CF bypass."""
        import time
        time.sleep(0.3)  # Rate limit
        try:
            r = requests.post(f'{self.TRAWL_URL}/v1',
                json={'cmd': 'request.get', 'url': url, 'maxTimeout': 60000},
                timeout=90)
            if r.status_code == 429:
                time.sleep(3)
                r = requests.post(f'{self.TRAWL_URL}/v1',
                    json={'cmd': 'request.get', 'url': url, 'maxTimeout': 60000},
                    timeout=90)
            if r.status_code == 200:
                data = r.json()
                sol = data.get('solution', {})
                if sol.get('status') == 200:
                    return sol.get('response', '')
            return ''
        except Exception as e:
            print(f'[{self.NAME}] trawl error: {e}')
            return ''

    def search_anime(self, query):
        try:
            # Use TRAWL for CF bypass
            search_url = f'{self.BASE_URL}/?s={quote(query)}'
            html = self._trawl_fetch(search_url)
            if not html:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            seen = set()
            for article in soup.find_all('article'):
                a = article.find('a', href=True)
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not title or query.lower() not in title.lower():
                    continue
                href = a['href']
                slug = href.rstrip('/').split('/')[-1]
                if slug in seen:
                    continue
                seen.add(slug)
                results.append({'title': title, 'slug': slug, 'type': 'series', 'provider': self.NAME})
            return results
        except:
            return []

    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            # Get episode page through TRAWL
            ep_url = f'{self.BASE_URL}/episode/{slug}-{season}x{episode}/'
            html = self._trawl_fetch(ep_url)
            if not html:
                # Try series page
                series_url = f'{self.BASE_URL}/series/{slug}/'
                html = self._trawl_fetch(series_url)
                if not html:
                    return {'streams': []}

            # Find data-post and data-nume
            data_post = re.search(r'data-post="([^"]+)"', html)
            data_nume = re.search(r'data-nume="([^"]+)"', html)

            if not data_post:
                eps = re.findall(r'<li[^>]*data-post="(\d+)"[^>]*data-nume="(\d+)"[^>]*>', html)
                if eps:
                    idx = min(episode - 1, len(eps) - 1)
                    data_post = eps[idx][0]
                    data_nume = eps[idx][1]
                else:
                    return {'streams': []}
            else:
                data_post = data_post.group(1)
                data_nume = data_nume.group(1)

            # AJAX call through TRAWL
            ajax_html = self._trawl_fetch(
                f'{self.BASE_URL}/wp-admin/admin-ajax.php?action=doo_player_ajax&post={data_post}&nume={data_nume}&type=tv'
            )
            if not ajax_html:
                return {'streams': []}

            try:
                # TRAWL may wrap JSON in HTML <pre> tags
                pre_match = re.search(r'<pre>(.*?)</pre>', ajax_html, re.DOTALL)
                if pre_match:
                    ajax_html = pre_match.group(1)
                data = json.loads(ajax_html)
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

                streams = []
                for tab in tabs:
                    if not tab['url']:
                        continue
                    player = self._classify(tab['url'])
                    streams.append({
                        'player': player,
                        'url': tab['url'],
                        'name': tab['name'],
                    })
                return {'streams': streams}
            except:
                return {'streams': []}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'zephyr' in u or 'as-cdn' in u: return 'zephyrflick'
        if 'gdmirrorbot' in u: return 'gdmirrorbot'
        if 'vidmoly' in u: return 'vidmoly'
        if 'abyss' in u: return 'abyss'
        if 'streamruby' in u: return 'streamruby'
        if 'dood' in u: return 'doodstream'
        if 'p2pplay' in u or 'strp' in u: return 'streamp2p'
        if 'turbovid' in u: return 'turbovid'
        if '.m3u8' in u: return 'direct_m3u8'
        return 'generic_embed'


# ========== DESIDUBANIME (desidubanime.me) ==========
# Uses GDMirrorBot + P2P family + Cloud

class DesiDubDirect:
    NAME = 'desidubanime'
    BASE_URL = 'https://desidubanime.me'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def search_anime(self, query):
        try:
            from urllib.parse import quote
            r = self.session.get(f'{self.BASE_URL}/search/{quote(query)}/feed/rss2/', timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'xml')
            results = []
            seen = set()
            for item in soup.find_all('item'):
                title = item.find('title')
                link = item.find('link')
                if not title or not link:
                    continue
                t = title.text.strip()
                h = link.text.strip()
                m = re.search(r'/(?:watch|anime)/([^/?#]+)', h)
                if not m:
                    continue
                slug = re.sub(r'-episode-\d+$', '', m.group(1))
                if slug in seen:
                    continue
                seen.add(slug)
                results.append({'title': t, 'slug': slug, 'type': 'series', 'provider': self.NAME})
            return results
        except:
            return []

    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            # DesiDubAnime uses /watch/{slug}-episode-{N}/ format
            ep_url = f'{self.BASE_URL}/watch/{slug}-episode-{episode}/'
            r = self.session.get(ep_url, timeout=TIMEOUT, verify=False)

            if r.status_code != 200:
                # Try to find episode from anime page
                anime_url = f'{self.BASE_URL}/anime/{slug}/'
                r2 = self.session.get(anime_url, timeout=TIMEOUT, verify=False)
                if r2.status_code == 200:
                    # Find episode link in anime page
                    ep_link = re.search(rf'href="https?://(?:www\.)?desidubanime\.me/watch/{re.escape(slug)}-episode-{episode}/"', r2.text)
                    if ep_link:
                        r = self.session.get(ep_link.group(0).split('"')[1], timeout=TIMEOUT, verify=False)
                    else:
                        return {'streams': []}
                else:
                    return {'streams': []}

            html = r.text
            streams = []

            # Find all GDMirrorBot URLs
            gdm_urls = re.findall(r'https?://(?:gdmirrorbot\.nl|pro\.iqsmartgames\.com)[^\s"\'<>]*', html)
            for gdm in set(gdm_urls):
                streams.append({
                    'player': 'gdmirrorbot',
                    'url': gdm,
                    'name': 'Mirror',
                })

            # Find data-embed-id (base64 encoded)
            data_embed_ids = re.findall(r'data-embed-id="([^"]+)"', html)
            for encoded in set(data_embed_ids):
                parts = encoded.split(':')
                if len(parts) == 2:
                    try:
                        name = base64.b64decode(parts[0]).decode()
                        url = base64.b64decode(parts[1]).decode()
                        player = self._classify(url)
                        streams.append({
                            'player': player,
                            'url': url,
                            'name': name,
                        })
                    except:
                        pass

            # Find iframes
            iframes = re.findall(r'<iframe[^>]+src="([^"]+)"', html, re.I)
            for iframe in set(iframes):
                player = self._classify(iframe)
                streams.append({
                    'player': player,
                    'url': iframe,
                    'name': player.replace('_', ' ').title(),
                })

            return {'streams': streams}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'gdmirrorbot' in u: return 'gdmirrorbot'
        if 'p2pplay' in u: return 'streamp2p'
        if 'rpmstream' in u: return 'rpmstream'
        if 'strp2p' in u: return 'streamp2p'
        if 'upns' in u: return 'upnshare'
        if 'cloud.desidubanime' in u: return 'cloud'
        if 'abyssplayer' in u: return 'abyss'
        if 'vidmoly' in u: return 'vidmoly'
        return 'generic_embed'


# ========== DORABASH (dorabash.in) ==========
# WordPress kiranime_pro theme

class DoraBashDirect:
    NAME = 'dorabash'
    BASE_URL = 'https://dorabash.in'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def search_anime(self, query):
        try:
            r = self.session.get(f'{self.BASE_URL}/', params={'s': query}, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            seen = set()
            for article in soup.find_all('article'):
                a = article.find('a', href=True)
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not title or query.lower() not in title.lower():
                    continue
                href = a['href']
                slug = href.rstrip('/').split('/')[-1]
                if slug in seen:
                    continue
                seen.add(slug)
                results.append({'title': title, 'slug': slug, 'type': 'series', 'provider': self.NAME})
            return results
        except:
            return []

    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            # Get anime page to find anime_id
            r = self.session.get(f'{self.BASE_URL}/anime/{slug}/', timeout=TIMEOUT)
            if r.status_code != 200:
                return {'streams': []}

            html = r.text
            # Find anime_id
            anime_id = re.search(r'anime_id["\']?\s*[:=]\s*["\']?(\d+)', html)
            if not anime_id:
                anime_id = re.search(r'data-anime-id="(\d+)"', html)
            if not anime_id:
                return {'streams': []}

            anime_id = anime_id.group(1)

            # Get episodes
            r = self.session.get(
                f'{self.BASE_URL}/wp-admin/admin-ajax.php?action=get_episodes&anime_id={anime_id}&page=1&order=desc',
                timeout=TIMEOUT
            )
            if r.status_code != 200:
                return {'streams': []}

            data = r.json()
            if not data.get('success'):
                return {'streams': []}

            episodes = data.get('data', {}).get('episodes', [])
            if not episodes or episode > len(episodes):
                return {'streams': []}

            ep = episodes[episode - 1]
            embed_url = ep.get('embed_url', ep.get('url', ''))
            if not embed_url:
                return {'streams': []}

            player = self._classify(embed_url)
            return {'streams': [{
                'player': player,
                'url': embed_url,
                'name': ep.get('title', f'Episode {episode}'),
            }]}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'zephyr' in u or 'as-cdn' in u: return 'zephyrflick'
        if 'gdmirrorbot' in u: return 'gdmirrorbot'
        if 'abyss' in u: return 'abyss'
        if 'vidmoly' in u: return 'vidmoly'
        if '.m3u8' in u: return 'direct_m3u8'
        return 'generic_embed'


# ========== ANIMOYE (animoye.com) ==========
# Uses proxykey.php + load_more.php

class AnimoyeDirect:
    NAME = 'animoye'
    BASE_URL = 'https://animoye.com'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def search_anime(self, query):
        try:
            r = self.session.get(f'{self.BASE_URL}/', params={'s': query}, timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            seen = set()
            for article in soup.find_all('article'):
                a = article.find('a', href=True)
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not title or query.lower() not in title.lower():
                    continue
                href = a['href']
                slug = href.rstrip('/').split('/')[-1]
                if slug in seen:
                    continue
                seen.add(slug)
                results.append({'title': title, 'slug': slug, 'type': 'series', 'provider': self.NAME})
            return results
        except:
            return []

    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            # Get episode page
            r = self.session.get(f'{self.BASE_URL}/series/{slug}.html', timeout=TIMEOUT)
            if r.status_code != 200:
                return {'streams': []}

            html = r.text
            # Find episode links
            ep_links = re.findall(r'href="([^"]*episode[^"]*)"', html, re.I)
            if not ep_links:
                return {'streams': []}

            ep_url = ep_links[0] if episode == 1 else ep_links[min(episode - 1, len(ep_links) - 1)]
            if not ep_url.startswith('http'):
                ep_url = f'{self.BASE_URL}/{ep_url.lstrip("/")}'

            # Get episode page
            r = self.session.get(ep_url, timeout=TIMEOUT)
            if r.status_code != 200:
                return {'streams': []}

            html = r.text
            # Find iframes
            iframes = re.findall(r'<iframe[^>]+src="([^"]+)"', html, re.I)
            streams = []
            for iframe in set(iframes):
                player = self._classify(iframe)
                streams.append({
                    'player': player,
                    'url': iframe,
                    'name': player.replace('_', ' ').title(),
                })

            return {'streams': streams}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'vidsrc' in u: return 'vidsrc'
        if 'moviesapi' in u: return 'moviesapi'
        if 'videasy' in u: return 'videasy'
        if 'technocosmos' in u: return 'autoembed'
        if 'as-cdn' in u or 'zephyr' in u: return 'zephyrflick'
        return 'generic_embed'


# ========== PIRATEXPLAY (piratexplay.cc) ==========
# Uses proxy/play.php

class PirateXPlayDirect:
    NAME = 'piratexplay'
    BASE_URL = 'https://piratexplay.cc'

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': UA})

    def search_anime(self, query):
        try:
            r = requests.get('https://ind.bashapi.tech/home', headers={'User-Agent': UA}, timeout=15, verify=False)
            data = r.json()
            if not data.get('success'):
                return []
            results = []
            seen = set()
            q = query.lower()
            for section in data.get('data', {}).get('main', []):
                for item in section.get('data', []):
                    slug = item.get('slug', '')
                    base_slug = re.sub(r'-\d+x\d+$', '', slug)
                    if base_slug in seen:
                        continue
                    title = item.get('title', '')
                    if q in title.lower() or q in base_slug.lower():
                        seen.add(base_slug)
                        results.append({'title': title, 'slug': base_slug, 'poster': item.get('poster', ''), 'type': 'series', 'provider': self.NAME})
            return results
        except:
            return []

    def get_episode_streams(self, slug, season=1, episode=1):
        try:
            # Get episode page
            r = self.session.get(f'{self.BASE_URL}/series/{slug}/', timeout=TIMEOUT)
            if r.status_code != 200:
                return {'streams': []}

            html = r.text
            # Find server URLs
            servers = re.findall(r'(?:src|url)\s*[:=]\s*["\']([^"\']+)["\']', html, re.I)
            streams = []
            for srv in set(servers):
                if 'as-cdn' in srv or 'gdmirrorbot' in srv or 'abyss' in srv:
                    player = self._classify(srv)
                    streams.append({
                        'player': player,
                        'url': srv,
                        'name': player.replace('_', ' ').title(),
                    })

            return {'streams': streams}
        except:
            return {'streams': []}

    def _classify(self, url):
        u = url.lower()
        if 'as-cdn' in u or 'zephyr' in u: return 'zephyrflick'
        if 'gdmirrorbot' in u: return 'gdmirrorbot'
        if 'abyss' in u: return 'abyss'
        return 'generic_embed'


# ========== EXPORT ==========
ALL_NEW_PROVIDERS = {
    'watchanimeworld': TorofilmDirect('https://watchanimeworld.top', 'watchanimeworld'),
    'animesalt': TorofilmDirect('https://animesalt.link', 'animesalt'),
    'animejoker': TorofilmDirect('https://animejoker.com', 'animejoker'),
    'desidubanime': DesiDubDirect(),
    'dorabash': DoraBashDirect(),
    'animoye': AnimoyeDirect(),
    'piratexplay': PirateXPlayDirect(),
}
