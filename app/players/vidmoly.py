"""
VidMoly player extractor.
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['vidmoly.org', 'vidmoly.net', 'vidmoly.biz', 'vidmoly.me',
           'vidmoly.to', 'vidmoly.vip']
NAMES = ['vidmoly']

ENABLED = True


def get_video_from_vidmoly_player(url):
    """Extract video URL from VidMoly embed page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://vidmoly.net/'}
        resp = requests.get(url, headers=headers, timeout=20, verify=False)
        resp.raise_for_status()

        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if not m:
            m = re.search(r'sources\s*[:=]\s*\[\{[^}]*file\s*:\s*["\']([^"\']+)["\']', resp.text)
            if not m:
                return None, None, None
            video_url = m.group(1)
        else:
            video_url = m.group(1)

        proxy_headers = {'request': {'Referer': 'https://vidmoly.net/', 'User-Agent': get_random_agent()}}
        return video_url, 'auto', proxy_headers

    except Exception as e:
        logging.warning(f"[VidMoly] {type(e).__name__}: {e}")
        return None, None, None
