"""
KrakenFiles player extractor.
Handles krakenfiles.com embed pages.
Used by GDMirrorBot sub-player.
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['krakenfiles.com', 'krakenfiles.net', 'krakenfiles.org']
NAMES = ['krakenfiles']

ENABLED = True


def get_video_from_krakenfiles_player(url):
    """Extract video URL from KrakenFiles embed page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://krakenfiles.com/'}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        m = re.search(r'(?:file|source|src)\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        m = re.search(r'(https?://[^"\'<>\s]+\.mp4[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[KrakenFiles] {type(e).__name__}: {e}")
        return None, None, None
