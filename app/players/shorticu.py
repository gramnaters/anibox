"""
Short.icu redirect resolver.
Follows short.icu redirects to get the final player URL.
Used by PirateXPlay SERVER 2 (SHORT), DoraBash, ToonStream SERVER 2 (SHORT).
"""

import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['short.icu', 'short.icu']
NAMES = ['short_icu', 'shorticu']

ENABLED = True


def resolve_short_icu(url):
    """Follow short.icu redirect and return final URL."""
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': get_random_agent()},
            timeout=15, verify=False, allow_redirects=True
        )
        if resp.status_code == 200:
            return resp.url
        return None
    except Exception:
        return None


def get_video_from_shorticu_player(url):
    """
    Resolve short.icu redirect and try to extract from final URL.
    Returns resolved URL for further processing.
    """
    try:
        final_url = resolve_short_icu(url)
        if not final_url or final_url == url:
            return None, None, None

        # Try to extract m3u8 from the final page
        from urllib.parse import urlparse
        headers = {'User-Agent': get_random_agent(), 'Referer': final_url}
        resp = requests.get(final_url, headers=headers, timeout=15, verify=False)
        if resp.status_code == 200:
            import re
            m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
            if m:
                return m.group(1), 'auto', {'request': headers}

        # Return the final URL for further processing by other players
        return final_url, 'redirect', {'request': headers}

    except Exception as e:
        logging.warning(f"[Short.icu] {type(e).__name__}: {e}")
        return None, None, None
