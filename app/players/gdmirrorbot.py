"""
GDMirrorBot player extractor.
Handles gdmirrorbot.nl embed pages with multiple sub-players.
Used by PirateXPlay, DesiDubAnime, ToonStream, ToonHub4u, AniMoye.

Provider mapping:
- PirateXPlay SERVER 4: GDMIRRORBOT - MULTI AUDIO
- DesiDub DUB: Mirror (gdmirrorbot.nl)
- ToonStream SERVER 4: GDMIRRORBOT
- ToonHub4u: GDMirror (gdmirrorbot.nl)
- AniMoye: GDMirrorBot (streams.iqsmartgames.com)
"""

import re
import logging
import base64
import json
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['gdmirrorbot.nl', 'gdmirrorbot.com', 'iqsmartgames.com',
           'embedbox.io', 'gembed.to', 'gdmirror.to']
NAMES = ['gdmirrorbot', 'gdmirror', 'iqsmartgames', 'mirror']

ENABLED = True

# Map of sub-host friendly names to player types
SUB_HOST_PLAYERS = {
    'streamhg': 'streamhg',
    'hanerix': 'streamhg',
    'smoothpre': 'streamhg',
    'vidhide': 'streamhg',
    'upnshare': 'upnshare',
    'rpmshare': 'upnshare',
    'streamp2p': 'upnshare',
    'p2pplay': 'upnshare',
    'strp2p': 'upnshare',
    'doodstream': 'dood',
    'dood': 'dood',
    'd000d': 'dood',
    'streamtape': 'streamtape',
    'abyss': 'abyss',
    'filemoon': 'filemoon',
    'byse': 'filemoon',
    'bysetayico': 'filemoon',
    'krakenfiles': 'krakenfiles',
    'earnvids': 'earnvids',
    'vidmoly': 'vidmoly',
    'turbovid': 'turbovid',
    'emturbovid': 'turbovid',
    'cloudy': 'upnshare',
    'multi': 'multiembed',
}


def get_video_from_gdmirrorbot_player(url):
    """
    Extract sub-player URLs from GDMirrorBot embed page.
    Returns a list of (player_name, sub_url) tuples.
    """
    try:
        headers = {'User-Agent': get_random_agent()}
        embed_id = url.split('/embed/')[-1].split('?')[0].split('#')[0]

        resp = requests.get(url, headers=headers, timeout=15, verify=False, allow_redirects=True)
        if resp.status_code != 200:
            return []

        from urllib.parse import urlparse
        parsed = urlparse(resp.url)
        host = f"{parsed.scheme}://{parsed.netloc}"

        r2 = requests.post(
            f"{host}/embedhelper.php",
            data={'sid': embed_id},
            headers={'User-Agent': headers['User-Agent'], 'Referer': host, 'X-Requested-With': 'XMLHttpRequest'},
            timeout=15, verify=False
        )
        if r2.status_code != 200:
            return []

        data = r2.json()
        site_urls = data.get('siteUrls', {})
        site_friendly_names = data.get('siteFriendlyNames', {})
        mresult = data.get('mresult', '')

        if isinstance(mresult, str) and len(mresult) > 20:
            try:
                decoded = base64.b64decode(mresult).decode('utf-8')
                mresult = json.loads(decoded)
            except Exception:
                return []

        if not isinstance(mresult, dict):
            return []

        results = []
        for key in set(site_urls.keys()) & set(mresult.keys()):
            site_url = site_urls.get(key, '').rstrip('/')
            path = mresult.get(key, '').lstrip('/')
            friendly_name = site_friendly_names.get(key, key)
            if not site_url or not path:
                continue

            full_url = f"{site_url}/{path}"

            # Detect sub-player type
            player = 'default'
            fn_lower = friendly_name.lower()
            for name_key, ptype in SUB_HOST_PLAYERS.items():
                if name_key in fn_lower or name_key in site_url.lower():
                    player = ptype
                    break

            results.append({
                'player': player,
                'url': full_url,
                'player_hosting': friendly_name,
                'player_name': f'GDMirror/{friendly_name}',
            })

        return results

    except Exception as e:
        logging.warning(f"[GDMirrorBot] {type(e).__name__}: {e}")
        return []


def get_video_from_mirror_player(url):
    """Alias for GDMirrorBot."""
    return get_video_from_gdmirrorbot_player(url)
