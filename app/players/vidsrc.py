"""
Vidsrc player extractor.
Handles vidsrc.xyz, vidsrc.wtf, vidsrc.stream, vidsrc.to URLs.
Used by AniMoye, AnimeLok.

Provider mapping:
- AniMoye: Vidsrc.xyz, Vidsrc.wtf (Multi Audio)
- AnimeLok: Multi
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['vidsrc.xyz', 'vidsrc.wtf', 'vidsrc.stream', 'vidsrc.to',
           'vidsrc.me', 'vidsrc.in', 'vidsrc.net', 'vidsrc.pro',
           'vidsrc.cc', 'vidsrc.dev', 'vidsrc.run']
NAMES = ['vidsrc']

ENABLED = True


def get_video_from_vidsrc_player(url):
    """Extract video URL from Vidsrc embed page."""
    try:
        headers = {'User-Agent': get_random_agent(), 'Referer': url}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        # Look for m3u8 URL
        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        # Look for sources
        m = re.search(r'sources\s*:\s*\[\{[^}]*(?:file|src)\s*:\s*["\']([^"\']+)["\']', resp.text)
        if m:
            return m.group(1), 'auto', {'request': headers}

        # Look for API endpoint
        m = re.search(r'(?:fetch|axios|XMLHttpRequest)\s*\(\s*["\']([^"\']+)["\']', resp.text)
        if m:
            api_url = m.group(1)
            if api_url.startswith('/'):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                api_url = f"{parsed.scheme}://{parsed.netloc}{api_url}"
            r2 = requests.get(api_url, headers=headers, timeout=15, verify=False)
            if r2.status_code == 200:
                data = r2.json()
                sources = data.get('sources', data.get('result', {}).get('sources', []))
                if sources and isinstance(sources, list):
                    for s in sources:
                        file_url = s.get('file', s.get('src', ''))
                        if file_url:
                            return file_url, s.get('label', 'auto'), {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[Vidsrc] {type(e).__name__}: {e}")
        return None, None, None
