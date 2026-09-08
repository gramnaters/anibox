"""
AniStream / MegaPlay player extractor.
Handles megaplay.buzz stream URLs used by AniFlix, AnimeLok, AnimeBashIndia.

Provider mapping:
- AniFlix SUB/DUB: Mega (megaplay.buzz direct)
- AnimeLok JAP/ENG: AniStream (megaplay.buzz/stream/ani/)
- AnimeBashIndia: HD-1, Vidstream-2 (megaplay.buzz CDN)
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['megaplay.buzz', 'megap.akirax.buzz', 'megap.mikora.top',
           'megap.shiora.site', 'megap.shiora.buzz', 'megap.mikora.net',
           'megap.akirax.net', 'megap.shiora.top']
NAMES = ['anistream', 'mega', 'megaplay', 'megacloud', 'megacdn']

ENABLED = True


def get_video_from_anistream_player(url):
    """Extract video URL from AniStream/MegaPlay stream page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://animelok.live/'}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        m = re.search(r'data-id=["\'](\d+)["\']', resp.text)
        if not m:
            m2 = re.search(r'/stream/ani/(\d+)', url)
            if not m2:
                return None, None, None
            data_id = m2.group(1)
        else:
            data_id = m.group(1)

        r2 = requests.get(
            f"https://megaplay.buzz/stream/getSources?id={data_id}",
            headers={'User-Agent': headers['User-Agent'], 'Referer': url, 'X-Requested-With': 'XMLHttpRequest'},
            timeout=15, verify=False
        )
        if r2.status_code != 200:
            return None, None, None

        data = r2.json()
        sources = data.get('sources', {})
        m3u8 = sources.get('file', '') if isinstance(sources, dict) else (sources[0].get('file', '') if sources else '')
        if not m3u8:
            return None, None, None

        tracks = data.get('tracks', [])
        subs = [{'id': f"anistream_{t.get('label', 'en')[:3]}", 'url': t.get('file', ''), 'lang': t.get('label', 'en').lower()[:3]}
                for t in tracks if t.get('kind') in ('captions', 'subtitles')]

        return m3u8, 'auto', {'request': {'Referer': 'https://megaplay.buzz/', 'User-Agent': headers['User-Agent']}}, subs

    except Exception as e:
        logging.warning(f"[AniStream] {type(e).__name__}: {e}")
        return None, None, None


def get_video_from_mega_player(url):
    """Alias for AniStream handler."""
    return get_video_from_anistream_player(url)
