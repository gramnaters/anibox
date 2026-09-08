"""
EmTurboVid player extractor.
Handles emturbovid.com embed pages.
Used by PirateXPlay SERVER 8 (TURBO), ToonStream SERVER 8 (TURBO).
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['emturbovid.com', 'turbovidhls.com', 'turbovidhls.net',
           'turbovid.com', 'turbovid.net']
NAMES = ['turbovid', 'emturbovid', 'turbovidhls', 'turbo']

ENABLED = True


def get_video_from_turbovid_player(url):
    """Extract video URL from EmTurboVid embed page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://emturbovid.com/'}
        resp = requests.get(url, headers=headers, timeout=20, verify=False)
        if resp.status_code != 200:
            return None, None, None

        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': {
                'Referer': 'https://emturbovid.com/',
                'User-Agent': get_random_agent()
            }}

        return None, None, None

    except Exception as e:
        logging.warning(f"[EmTurboVid] {type(e).__name__}: {e}")
        return None, None, None
