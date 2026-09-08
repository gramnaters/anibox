"""
VidRock DL player extractor.
Handles vidrock.com URLs.
Used by AniMoye.
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['vidrock.com', 'vidrock.net', 'vidrock.me', 'vidrock.org',
           'vidrock.cc', 'vidrock.io']
NAMES = ['vidrock']

ENABLED = True


def get_video_from_vidrock_player(url):
    """Extract video URL from VidRock page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': url}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        m = re.search(r'sources\s*:\s*\[\{[^}]*(?:file|src)\s*:\s*["\']([^"\']+)["\']', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[VidRock] {type(e).__name__}: {e}")
        return None, None, None
