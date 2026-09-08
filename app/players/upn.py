"""
UPN/RPM player extractor.
Ported from docchi-stremio-addon (upns.pro, rpmhub.site, rpmvip.com).
"""

import re
import logging
from urllib.parse import urlparse
from Crypto.Cipher import AES

try:
    from app.players.common_utils import get_random_agent, fetch_resolution_from_m3u8
except ImportError:
    from common_utils import get_random_agent, fetch_resolution_from_m3u8

DOMAINS = ['upns.pro', 'rpmhub.site', 'rpmvip.com',
           'upns.live', 'rpmstream.live', 'strp2p.site', 'p2pplay.pro',
           'cloudy.upns.one', 'cloudy.p2pplay.pro', 'desidubanime.p2pplay.pro',
           'desidubanime.upns.live', 'desidubanime.rpmstream.live',
           'desidubanime.strp2p.site']
NAMES = ['upnshare', 'rpmshare', 'upn', 'rpm', 'vidstack', 'streamp2p']

ENABLED = True

DECRYPTION_KEY_HEX = "6b69656d7469656e6d75613931316361"


def _unpad_pkcs7(padded_data):
    if not padded_data:
        return b''
    pad_value = padded_data[-1]
    if 1 <= pad_value <= AES.block_size and padded_data[-pad_value:] == bytes([pad_value]) * pad_value:
        return padded_data[:-pad_value]
    return padded_data


def _decrypt_to_raw_text(encrypted_hex_str, key_hex):
    key_bytes = bytes.fromhex(key_hex)
    full_payload_bytes = bytes.fromhex(encrypted_hex_str.strip())
    iv = full_payload_bytes[:16]
    ciphertext = full_payload_bytes[16:]
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    decrypted_padded_bytes = cipher.decrypt(ciphertext)
    decrypted_bytes = _unpad_pkcs7(decrypted_padded_bytes)
    return decrypted_bytes.decode('utf-8', errors='ignore')


def get_video_from_upn_player(url):
    """Extract video URL from UPN/RPM/VidStack player."""
    import requests

    try:
        parsed_url = urlparse(url)
        base_url_with_scheme = f"{parsed_url.scheme}://{parsed_url.netloc}"

        headers = {
            "User-Agent": get_random_agent(),
            "Referer": f"{base_url_with_scheme}/"
        }

        # Extract video ID from fragment
        video_id_match = re.search(r'#([a-zA-Z0-9]+)', url)
        if not video_id_match:
            logging.warning("[UPN] wrong ID")
            return None, None, None

        video_id = video_id_match.group(1)
        api_url = f"{base_url_with_scheme}/api/v1/video?id={video_id}&w=1920&h=1200&r="

        response = requests.get(api_url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        encrypted_response_hex = response.text

        decrypted_text = _decrypt_to_raw_text(encrypted_response_hex, DECRYPTION_KEY_HEX)

        stream_url = None
        source_match = re.search(r'"source"\s*:\s*"([^"]+)"', decrypted_text)
        if source_match:
            stream_url = source_match.group(1).replace('\\/', '/')

        if not stream_url:
            logging.warning("[UPN] no 'source' found")
            return None, None, None

        quality = fetch_resolution_from_m3u8(stream_url, headers)
        if not quality:
            quality = "unknown"

        stream_headers = {'request': headers}
        return stream_url, quality, stream_headers

    except Exception as e:
        logging.warning(f"[UPN] Unexpected error: {e}")
        return None, None, None


# Alias for compatibility
def get_video_from_vidstack_player(url):
    return get_video_from_upn_player(url)
