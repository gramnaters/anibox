"""
VibePlayer extractor.
Handles vibeplayer:// custom scheme URLs from AnimeLok API.

Provider mapping:
- AnimeLok JAP/ENG: HD-1 (VibePlayer)
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['vivibebe.site']
NAMES = ['vibeplayer']

ENABLED = True


def get_video_from_vibeplayer_player(url):
    """Extract video URL from VibePlayer (via AnimeLok API)."""
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        anilist_id = parsed.netloc or parsed.path.strip('/')
        qs = parse_qs(parsed.query)
        ep = qs.get('ep', ['1'])[0]
        src_type = qs.get('type', ['sub'])[0]

        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://animelok.live/'}
        r = requests.get(
            f"https://animelok.live/api/get-vibeplayer-data",
            params={'anilistId': anilist_id, 'epNum': ep, 'type': src_type},
            headers=headers, timeout=15, verify=False
        )
        if r.status_code != 200:
            return None, None, None

        data = r.json()
        sources = data.get('sources', [])
        if isinstance(sources, list) and sources:
            m3u8 = sources[0].get('url', '') or sources[0].get('file', '')
        elif isinstance(sources, dict):
            m3u8 = sources.get('url', '') or sources.get('file', '')
        else:
            m3u8 = ''

        if not m3u8:
            return None, None, None

        referer = data.get('headers', {}).get('Referer', 'https://vivibebe.site')
        return m3u8, 'auto', {'request': {'Referer': referer, 'User-Agent': headers['User-Agent']}}

    except Exception as e:
        logging.warning(f"[VibePlayer] {type(e).__name__}: {e}")
        return None, None, None
