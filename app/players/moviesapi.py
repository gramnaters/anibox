"""
MoviesAPI player extractor.
Handles moviesapi.club URLs.
Used by AniMoye.
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['moviesapi.club', 'moviesapi.com']
NAMES = ['moviesapi']

ENABLED = True


def get_video_from_moviesapi_player(url):
    """Extract video URL from MoviesAPI page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://moviesapi.club/'}
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
        logging.warning(f"[MoviesAPI] {type(e).__name__}: {e}")
        return None, None, None
