"""
FlixCloud player extractor.
Handles flixcloud.cc, fetch.flixcloud.cc URLs.
Used by BashAPI (flixcloud.cc embeds).
"""

import re
import logging
import json
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['flixcloud.cc', 'fetch.flixcloud.cc', 'flixcloud.to', 'flixcloud.io',
           'flixcloud.net', 'flixcloud.me', 'flixcloud.org']
NAMES = ['flixcloud', 'flix']

ENABLED = True


def get_video_from_flixcloud_player(url):
    """Extract video URL from FlixCloud embed page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://flixcloud.cc/'}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        m = re.search(r'(https?://[^"\'<>\s]+\.mp4[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[FlixCloud] {type(e).__name__}: {e}")
        return None, None, None
