"""
Abyss/HydraX player extractor.
Improved version with AES-256-CTR decryption from MediaVanced.
"""
import re
import json
import base64
import hashlib
import logging
import requests
from urllib.parse import urlparse

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['abysscdn.com', 'hydraxcdn.biz', 'short.icu', 'embedplayabyss.top',
           'abyssplayer.com', 'play.abyssplayer.com', 'abysssplayer.com']
NAMES = ['abyss', 'abyssplayer', 'abysssplayer']

ENABLED = True


def get_video_from_abyss_player(url):
    """Extract video URL from Abyss/HydraX page."""
    try:
        # Normalize URL
        if 'short.icu' in url or 'embedplayabyss.top' in url:
            vid_match = re.search(r'[?/]v=([0-9a-zA-Z_-]+)', url)
            if vid_match:
                url = f'https://abysscdn.com/?v={vid_match.group(1)}'

        headers = {
            "Referer": "https://abysscdn.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        }

        resp = requests.get(url, headers=headers, verify=False, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Extract encoded data from const datas = "..."
        match = re.search(r'(?:const|var)\s+datas\s*=\s*"([^"]+)"', html)
        if not match:
            return None, None, None

        encoded_data = match.group(1)
        decoded_text = base64.b64decode(encoded_data).decode('latin-1')
        data = json.loads(decoded_text)

        user_id = str(data['user_id'])
        slug = data['slug']
        md5_id = str(data['md5_id'])

        # Create key from seed
        seed = f"{user_id}:{slug}:{md5_id}"
        md5_hex = hashlib.md5(seed.encode('utf-8')).hexdigest()
        key_bytes = md5_hex.encode('utf-8')

        # AES-256-CTR decryption
        from Crypto.Cipher import AES
        iv_bytes = key_bytes[:16]

        encrypted_media_bytes = data['media'].encode('latin-1')
        cipher = AES.new(key_bytes, AES.MODE_CTR, nonce=b'', initial_value=iv_bytes)
        decrypted_bytes = cipher.decrypt(encrypted_media_bytes)

        metadata_config = json.loads(decrypted_bytes.decode('utf-8'))

        # Extract video URL
        video_url = _extract_url_from_metadata(metadata_config)

        if video_url:
            return video_url, 'auto', {'request': headers}

        logging.warning("[Abyss] No video source found")
        return None, None, None

    except Exception as e:
        logging.warning(f"[Abyss] {type(e).__name__}: {e}")
        return None, None, None


def _extract_url_from_metadata(config):
    """Extract video URL from decrypted metadata config."""
    if not isinstance(config, dict):
        return None

    # Try mp4 sources
    mp4 = config.get('mp4') if isinstance(config.get('mp4'), dict) else {}
    sources = mp4.get('sources') if isinstance(mp4.get('sources'), list) else []

    for src in sorted(sources, key=lambda s: int(s.get('size', 0) or 0), reverse=True):
        direct = src.get('file')
        if direct:
            return direct.replace('\\/', '/')
        url = src.get('url')
        path = src.get('path')
        if url and path:
            return f"{url.rstrip('/')}/{path.lstrip('/')}".replace('\\/', '/')

    # Try HLS
    hls = config.get('hls') if isinstance(config.get('hls'), dict) else {}
    for key in ('file', 'url', 'master', 'src', 'source'):
        val = hls.get(key)
        if isinstance(val, str) and val:
            return val.replace('\\/', '/')

    # Try direct sources
    for src in sources:
        size = src.get('size')
        label = src.get('label')
        if size and label:
            return src.get('file', '').replace('\\/', '/')

    return None
