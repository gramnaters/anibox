"""
FirePlayer / ZephyrFlick player extractor.
Improved version with proper headers from Nuvio's AnimeSalt/AnimeWorld logic.

Extraction flow (from Nuvio):
1. Get page, find src="https://as-cdn{N}.top/video/{hash}" or play.zephyrflick.top/video/{hash}
2. POST to {base}/player/index.php?data={hash}&do=getVideo
   Body: hash={hash}&siteurl={page_url}
   Headers: Referer, Origin, X-Requested-With: XMLHttpRequest
3. Response: {"videoSource": "https://{base}/cdn/hls/{hash}/master.m3u8?md5=..."}
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['play.zephyrix.top', 'play.zephyrflick.top', 'as-cdn21.top',
           'as-cdn22.top', 'as-cdn23.top', 'as-cdn24.top', 'as-cdn25.top',
           'zephyrflick.top', 'zephyrix.top', 'embedplayzephyr.top',
           'play.zephyrix.top']
NAMES = ['fireplayer', 'zephyr', 'zephyrflick', 'zephyrix', 'mystream', 'play']

ENABLED = True


def get_video_from_fireplayer_player(url):
    """Extract video URL from FirePlayer page."""
    try:
        # Extract hash from URL
        hash_match = re.search(r'/video/([a-f0-9]+)', url)
        if not hash_match:
            return None, None, None

        video_hash = hash_match.group(1)

        # Determine base URL
        base_match = re.match(r'(https?://[^/]+)', url)
        if not base_match:
            return None, None, None
        base_url = base_match.group(1).rstrip('/')

        # Build referer (the page that embeds this player)
        referer = base_url + '/'

        # POST to getVideo API
        api_url = f"{base_url}/player/index.php?data={video_hash}&do=getVideo"
        post_data = f"hash={video_hash}&siteurl={referer}"

        headers = {
            'User-Agent': get_random_agent(),
            'Referer': referer,
            'Origin': base_url,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        resp = requests.post(api_url, data=post_data, headers=headers, timeout=30, verify=False)
        resp.raise_for_status()
        data = resp.json()

        video_url = data.get('videoSource') or data.get('source')
        if not video_url:
            return None, None, None

        # Build response headers
        response_headers = {
            'request': {
                'Referer': referer,
                'Origin': base_url,
                'User-Agent': get_random_agent(),
            }
        }

        return video_url, 'auto', response_headers

    except Exception as e:
        logging.warning(f"[FirePlayer] {type(e).__name__}: {e}")
        return None, None, None


def get_video_from_mystream_player(url):
    """
    Extract video URL from AnimeSalt MyStream (as-cdn21.top).
    Same as FirePlayer but with AnimeSalt-specific referer.
    """
    try:
        hash_match = re.search(r'/video/([a-f0-9]+)', url)
        if not hash_match:
            return None, None, None

        video_hash = hash_match.group(1)
        base_match = re.match(r'(https?://[^/]+)', url)
        if not base_match:
            return None, None, None
        base_url = base_match.group(1).rstrip('/')

        # AnimeSalt uses animesalt.link as referer
        referer = 'https://animesalt.link/'
        api_url = f"{base_url}/player/index.php?data={video_hash}&do=getVideo"
        post_data = f"hash={video_hash}&siteurl={referer}"

        headers = {
            'User-Agent': get_random_agent(),
            'Referer': referer,
            'Origin': base_url,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        resp = requests.post(api_url, data=post_data, headers=headers, timeout=30, verify=False)
        resp.raise_for_status()
        data = resp.json()

        video_url = data.get('videoSource') or data.get('source')
        if not video_url:
            return None, None, None

        return video_url, 'auto', {
            'request': {
                'Referer': referer,
                'Origin': base_url,
                'User-Agent': get_random_agent(),
            }
        }

    except Exception as e:
        logging.warning(f"[MyStream] {type(e).__name__}: {e}")
        return None, None, None
