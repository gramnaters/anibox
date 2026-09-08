"""
MegaCloud / MewStream player extractor.
Handles megacloud.animanga.fun, cdn.mewstream.buzz URLs.
Used by AnimeLok Multi.
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['megacloud.animanga.fun', 'cdn.mewstream.buzz', 'mewstream.buzz',
           'megacloud.to', 'megacloud.net', 'megacloud.io']
NAMES = ['megacloud', 'mewstream']

ENABLED = True


def get_video_from_megacloud_player(url):
    """Extract video URL from MegaCloud/MewStream page."""
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

        return None, None, None

    except Exception as e:
        logging.warning(f"[MegaCloud] {type(e).__name__}: {e}")
        return None, None, None
