"""
DoodStream player extractor.
Ported from docchi-stremio-addon.
"""

import re
import logging
import random
import string
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['dood.li', 'dood.to', 'dood.ws', 'dood.so', 'dood.la',
           'd000d.com', 'd0000d.com', 'doodstream.com', 'dood.watch',
           'dood.cx', 'dood.yt', 'dood.sh', 'dood.pm', 'dood.wf',
           'dood.re', 'dood.fo', 'dood.stream']
NAMES = ['doodstream', 'dood']

ENABLED = True


def get_video_from_dood_player(url):
    """Extract video URL from DoodStream page."""
    try:
        dood_hosts = ['dood.li', 'dood.to', 'dood.ws', 'dood.so', 'dood.la',
                      'dood.pm', 'dood.sh', 'dood.wf', 'dood.re', 'dood.fo']
        host = url.split('/')[2]
        if host not in dood_hosts:
            for h in dood_hosts:
                if h in host:
                    host = h
                    break

        url = url.replace('/d/', '/e/')

        headers = {
            'User-Agent': get_random_agent(),
            'Referer': f'https://{host}/'
        }

        resp = requests.get(url, headers=headers, timeout=15, verify=False, allow_redirects=True)
        resp.raise_for_status()

        m = re.search(r'/pass_md5/([^"\'<>\s]+)', resp.text)
        if not m:
            return None, None, None

        token = m.group(1)
        r2 = requests.get(f"https://{host}/pass_md5/{token}",
                         headers={'User-Agent': headers['User-Agent'], 'Referer': resp.url},
                         timeout=15, verify=False)

        if r2.status_code != 200 or not r2.text:
            return None, None, None

        random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        final_url = f"{r2.text}{random_chars}?token={token.split('/')[-1]}"

        quality = 'unknown'
        qm = re.search(r'(\d{3,4}[pP])', resp.text)
        if qm:
            quality = qm.group(1)

        return final_url, quality, {'request': {'Referer': f'https://{host}/', 'User-Agent': headers['User-Agent']}}

    except Exception as e:
        logging.warning(f"[DoodStream] {type(e).__name__}: {e}")
        return None, None, None
