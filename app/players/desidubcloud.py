"""
DesiDub Cloud player extractor.
Handles cloud.desidubanime.me self-hosted video player.
Used by DesiDubAnime CLOUD [No Ads].
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['cloud.desidubanime.me', 'cloud.desidubanime.com']
NAMES = ['desidub_cloud', 'desidubcloud']

ENABLED = True


def get_video_from_desidubcloud_player(url):
    """Extract video URL from DesiDub Cloud page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://www.desidubanime.me/'}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        # Look for play hash
        play_hashes = re.findall(r'/play/([a-f0-9]{40,})', resp.text)
        if not play_hashes:
            m = re.search(r'/external/([a-f0-9]{40,})', url)
            if m:
                play_hashes = [m.group(1)]

        if play_hashes:
            m3u8_url = f"https://cloud.desidubanime.me/media/{play_hashes[0]}"
            r2 = requests.get(m3u8_url, headers={'User-Agent': headers['User-Agent'],
                                                  'Referer': 'https://cloud.desidubanime.me/'},
                            timeout=15, verify=False)
            if r2.status_code == 200 and '#EXTM3U' in r2.text[:50]:
                return m3u8_url, 'auto', {'request': {'Referer': 'https://cloud.desidubanime.me/',
                                                       'User-Agent': headers['User-Agent']}}

        # Try direct m3u8 in page
        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[DesiDubCloud] {type(e).__name__}: {e}")
        return None, None, None
