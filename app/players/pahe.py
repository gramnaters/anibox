"""
Pahe / Kwik / UwuCDN player extractor.
Full extraction logic ported from Nuvio's All-in-One addon.

AnimePahe flow:
1. Search anime → get session + episode pages
2. Each episode links to kwik.cx embed
3. Fetch kwik page → extract packed JS with .split('|') pattern
4. Unpack JS → extract source='...m3u8...'
5. Return URL with Referer: https://kwik.cx, Origin: https://kwik.cx
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['pahe.host', 'pahe.win', 'pahe.bz', 'pahe.in', 'pahe.pm',
           'vault-01.uwucdn.top', 'vault-02.uwucdn.top',
           'vault-01.uwucdn.net', 'vault-02.uwucdn.net',
           'uwucdn.top', 'uwucdn.net', 'animepahe.ru', 'animepahe.org',
           'animepahe.com', 'pahe.live', 'kwik.cx', 'kwik.si',
           'animepahe.win']
NAMES = ['pahe', 'uwucdn', 'animepahe', 'kwik']

ENABLED = True

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}

KWIK_REFERER = 'https://kwik.cx'
KWIK_ORIGIN = 'https://kwik.cx'


def _unpack_js(packed_code):
    """Unpack eval(function(p,a,c,k,e,d){...}) packed JS."""
    try:
        import jsbeautifier.unpackers.packer as packer
        if packer.detect(packed_code):
            return packer.unpack(packed_code)
    except Exception:
        pass

    # Manual unpack using regex for .split('|') pattern
    try:
        match = re.search(
            r"}\((['\"])([\s\S]*?)\1,\s*(\d+),\s*(\d+),\s*(['\"])([\s\S]*?)\5\.split\((['"])\|\7\)",
            packed_code
        )
        if match:
            _, code, count, _, _, dictionary, _ = match.groups()
            dictionary = dictionary.split('|')
            count = int(count)
            # Simple substitution
            for i in range(count - 1, -1, -1):
                if i < len(dictionary):
                    code = code.replace(_base_n_str(i, count), dictionary[i])
            return code
    except Exception:
        pass

    return ''


def _base_n_str(num, base):
    """Convert number to base-n string for unpacking."""
    if num == 0:
        return '0'
    chars = '0123456789abcdefghijklmnopqrstuvwxyz'
    result = ''
    while num > 0:
        result = chars[num % base] + result
        num //= base
    return result


def extract_kwik(url):
    """
    Extract m3u8 URL from kwik.cx embed page.
    Ported from Nuvio's extractKwik function.
    """
    try:
        headers = dict(HEADERS)
        headers['Referer'] = KWIK_REFERER + '/'
        headers['Origin'] = KWIK_ORIGIN

        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        html = resp.text

        # Extract all script tags
        scripts = re.findall(r'<script.*?>([\s\S]*?)</script>', html)

        packed_blocks = []
        for script in scripts:
            # Find packed JS with .split('|') pattern
            idx = 0
            while True:
                find_idx = script.indexOf('eval(function(p,a,c,k,e', idx) if hasattr(script, 'indexOf') else script.find('eval(function(p,a,c,k,e', idx)
                if find_idx == -1:
                    break
                split_idx = script.find('.split(\'|\')', find_idx)
                if split_idx == -1:
                    break
                end_idx = script.find('))', split_idx)
                if end_idx == -1:
                    break
                packed_blocks.append(script[find_idx:end_idx + 2])
                idx = end_idx + 2

        # Also try the direct pattern
        for script in scripts:
            if 'split(\'|\')' in script or 'split("|")' in script:
                # Find all eval blocks
                for m in re.finditer(r'(eval\(function\(p,a,c,k,e[^{]*\{[\s\S]*?\)\))', script):
                    packed_blocks.append(m.group(1))

        for packed in packed_blocks:
            unpacked = _unpack_js(packed)
            if not unpacked:
                continue

            # Extract source URL
            m = re.search(r"source\s*=\s*'([^']+m3u8[^']*)'", unpacked) or \
                re.search(r'source\s*=\s*"([^"]+m3u8[^"]*)"', unpacked) or \
                re.search(r"source\s*=\s*'([^']+\.m3u8[^']*)'", unpacked) or \
                re.search(r'src\s*=\s*"([^"]+m3u8[^"]*)"', unpacked) or \
                re.search(r"file\s*:\s*'([^']+m3u8[^']*)'", unpacked) or \
                re.search(r'(https?://[^"\']+\.m3u8[^"\']*)', unpacked)

            if m:
                video_url = m.group(1).replace('\\/', '/')
                return {
                    'url': video_url,
                    'headers': {
                        'Referer': KWIK_REFERER + '/',
                        'Origin': KWIK_ORIGIN,
                        'User-Agent': HEADERS['User-Agent']
                    }
                }

        return None

    except Exception as e:
        logging.warning(f"[Kwik] Extract error: {e}")
        return None


def get_video_from_pahe_player(url):
    """Extract video URL from Pahe/UwuCDN/Kwik page."""
    try:
        # Direct kwik.cx URL
        if 'kwik' in url:
            result = extract_kwik(url)
            if result:
                return result['url'], 'auto', {'request': result['headers']}
            return None, None, None

        # Vault/uwucdn direct URL
        if 'vault-0' in url or 'uwucdn' in url:
            headers = {'request': {'Referer': 'https://pahe.host/', 'User-Agent': get_random_agent()}}
            return url, 'auto', headers

        # AnimePahe page - extract kwik link
        if 'animepahe' in url or 'pahe' in url:
            headers = dict(HEADERS)
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            if resp.status_code != 200:
                return None, None, None

            # Find kwik embed link
            m = re.search(r'(https?://kwik\.[a-z]+/[^\s"\'<>]+)', resp.text)
            if m:
                kwik_url = m.group(1)
                result = extract_kwik(kwik_url)
                if result:
                    return result['url'], 'auto', {'request': result['headers']}

        # Generic m3u8 extraction
        headers = {'User-Agent: get_random_agent(), 'Referer': 'https://pahe.host/'}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code == 200:
            m = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', resp.text)
            if m:
                return m.group(1), 'auto', {'request': {'Referer': 'https://pahe.host/', 'User-Agent': get_random_agent()}}

        return None, None, None

    except Exception as e:
        logging.warning(f"[Pahe] {type(e).__name__}: {e}")
        return None, None, None
