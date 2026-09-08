"""
VidMaster (VidNest) player extractor.
Handles new.vidnest.fun URLs used by AnimeLok.

Provider mapping:
- AnimeLok JAP/ENG: VidMaster (new.vidnest.fun)
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

DOMAINS = ['vidnest.fun', 'new.vidnest.fun']
NAMES = ['vidmaster', 'vidnest']

ENABLED = True

STD_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
CUSTOM_B64 = "RB0fpH8ZEyVLkv7c2i6MAJ5u3IKFDxlS1NTsnGaqmXYdUrtzjwObCgQP94hoeW+/="


def _custom_b64_decode(encoded):
    """Decode VidMaster's custom base64."""
    try:
        trans = str.maketrans(CUSTOM_B64, STD_B64)
        return base64.b64decode(encoded.translate(trans)).decode('utf-8')
    except Exception:
        return ''


def get_video_from_vidmaster_player(url):
    """Extract video URL from VidMaster (VidNest) page."""
    try:
        headers = {'User-Agent': get_random_agent()}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        try:
            resp_json = json.loads(resp.text)
        except Exception:
            return None, None, None

        encrypted_data = resp_json.get('data', '')
        if not encrypted_data:
            data = resp_json
        else:
            decoded = _custom_b64_decode(encrypted_data)
            if not decoded:
                return None, None, None
            try:
                data = json.loads(decoded)
            except Exception:
                return None, None, None

        sources = data.get('sources', [])
        if isinstance(sources, list) and sources:
            m3u8 = sources[0].get('file', '') or sources[0].get('url', '')
        elif isinstance(sources, dict):
            m3u8 = sources.get('file', '') or sources.get('url', '')
        else:
            m3u8 = ''

        if not m3u8:
            return None, None, None

        return m3u8, 'auto', {'request': {'Referer': 'https://megaplay.buzz/', 'User-Agent': headers['User-Agent']}}

    except Exception as e:
        logging.warning(f"[VidMaster] {type(e).__name__}: {e}")
        return None, None, None
