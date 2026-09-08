"""
VidStreaming player extractor.
Handles vidstreaming.io, vidstreaming.pro URLs.
Used by PirateXPlay SERVER 3 (VIDSTREAMING).
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['vidstreaming.io', 'vidstreaming.pro', 'vidstreaming.net',
           'vidstreaming.me', 'vidstreaming.com', 'vidstreaming.org',
           'gogo-stream.com', 'gogoplay.io', 'gogoplay1.com',
           'goload.io', 'goload.pro', 'streamani.net', 'playtvid.com']
NAMES = ['vidstreaming', 'gogoplay', 'goload', 'playtvid']

ENABLED = True


def get_video_from_vidstreaming_player(url):
    """Extract video URL from VidStreaming page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': url}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        m = re.search(r'(?:file|source|src)\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        m = re.search(r'sources\s*:\s*\[\{[^}]*(?:file|src)\s*:\s*["\']([^"\']+)["\']', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[VidStreaming] {type(e).__name__}: {e}")
        return None, None, None
