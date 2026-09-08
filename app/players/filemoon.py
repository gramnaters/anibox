"""
Filemoon/Byse player extractor.
Improved version with API-based extraction from MediaVanced.

Flow:
1. Extract video ID from URL
2. GET /api/videos/{code}/embed/details → get embed_frame_url
3. GET /api/videos/{code}/embed/playback → get encrypted data
4. Decrypt with AES-GCM
5. Extract sources URL
"""
import re
import json
import base64
import logging
import requests
from urllib.parse import urlparse

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['filemoon.sx', 'filemoon.to', 'filemoon.in', 'filemoon.link', 'filemoon.nl',
           'filemoon.wf', 'filemoon.eu', 'filemoon.art', 'moonmov.pro', '96ar.com',
           'kerapoxy.cc', 'furher.in', 'smdfs40r.skin', 'c1z39.com', 'bf0skv.org',
           'z1ekv717.fun', 'l1afav.net', '222i8x.lol', '8mhlloqo.fun', 'f51rm.com',
           'xcoic.com', 'boosteradx.online', 'streamlyplayer.online', 'streamlyplayero.online',
           'bysewihe.com', 'byselapuix.com', 'byseqekaho.com', 'rupertisdivingintoocean.com',
           'bysesayeveum.com', 'bysetayico.com', 'bysevepoin.com', 'bysezejataos.com',
           'bysekoze.com', 'bysesukior.com', 'bysejikuar.com', 'bysefujedu.com',
           'bysedikamoum.com', 'bysebuho.com', 'byse.sx', 'embedplaybyse.top',
           'sb1254w9megshle.org', '1azayf9w.xyz']
NAMES = ['filemoon', 'byse']

ENABLED = True


def _b64_url_decode(v):
    """Decode URL-safe Base64."""
    v = v.replace('-', '+').replace('_', '/')
    return base64.b64decode(v + '=' * (-len(v) % 4))


def get_video_from_filemoon_player(url):
    """Extract video URL from Filemoon/Byse page."""
    try:
        # Extract video code from URL
        code_match = re.search(r'/e/([^/]+)', url)
        if not code_match:
            code_match = re.search(r'/embed/([^/]+)', url)
        if not code_match:
            return None, None, None

        code = code_match.group(1)
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        headers = {
            "Accept": "*/*",
            "Referer": domain,
            "X-Embed-Parent": url,
            "User-Agent": get_random_agent(),
        }

        # Step 1: Get embed details
        details_url = f'{domain}/api/videos/{code}/embed/details'
        resp = requests.get(details_url, headers=headers, timeout=15, verify=False).json()

        # Get embed frame URL
        embed_url = resp.get('embed_frame_url')
        if embed_url:
            embed_parsed = urlparse(embed_url)
            domain = f"https://{embed_parsed.netloc}"

        # Step 2: Get playback data
        playback_url = f'{domain}/api/videos/{code}/embed/playback'
        resp = requests.get(playback_url, headers=headers, timeout=15, verify=False).json()

        # Step 3: Decrypt
        encryption_info = resp.get('playback')
        if not encryption_info:
            # Try packed JS extraction as fallback
            return _extract_from_page(url, domain)

        ciphertext_b64 = encryption_info.get('payload')
        key_parts = encryption_info.get('key_parts')
        iv_b64 = encryption_info.get('iv')

        if not all([ciphertext_b64, key_parts, iv_b64]):
            return _extract_from_page(url, domain)

        ciphertext = _b64_url_decode(ciphertext_b64)
        key = b''.join(_b64_url_decode(p) for p in key_parts)
        iv = _b64_url_decode(iv_b64)

        # Parse auth tag and ciphertext
        ciphertext_data = ciphertext[:-16]
        tag = ciphertext[-16:]

        # Decrypt with AES-GCM
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        plaintext = cipher.decrypt_and_verify(ciphertext_data, tag)

        streaming_info = json.loads(plaintext)
        sources = streaming_info.get('sources')

        if sources and len(sources) > 0:
            video_url = sources[0].get('url')
            if video_url:
                return video_url, 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[Filemoon] {type(e).__name__}: {e}")
        return None, None, None


def _extract_from_page(url, domain):
    """Fallback: extract packed JS from page."""
    try:
        headers = {
            "Referer": domain,
            "User-Agent": get_random_agent(),
        }
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        html = resp.text

        # Look for m3u8 URL
        m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', html)
        if m:
            return m.group(1), 'auto', {'request': headers}

        # Look for sources array
        m = re.search(r'sources\s*:\s*\[\s*\{\s*file\s*:\s*["\']([^"\']+)["\']', html)
        if m:
            return m.group(1), 'auto', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[Filemoon fallback] {type(e).__name__}: {e}")
        return None, None, None
