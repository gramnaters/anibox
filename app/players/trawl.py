"""
TRAWL Cloudflare bypass helper.
Uses https://trawl.fly.dev/ to bypass CF-protected sites.
"""
import os
import re
import json
import logging
import requests

def get_trawl_url():
    """Get TRAWL URL from config."""
    from config import Config
    return Config.TRAWL_URL or os.getenv('TRAWL_URL', '')


def trawl_fetch(url, max_timeout=60000):
    """
    Fetch a URL through TRAWL CF bypass.
    Returns (status_code, content) or (None, None) on failure.
    """
    trawl_url = get_trawl_url()
    if not trawl_url:
        logging.warning("[TRAWL] No TRAWL_URL configured")
        return None, None

    try:
        r = requests.post(f'{trawl_url}/v1',
            json={'cmd': 'request.get', 'url': url, 'maxTimeout': max_timeout},
            timeout=min(max_timeout / 1000 + 30, 120))

        if r.status_code != 200:
            logging.warning(f"[TRAWL] HTTP {r.status_code} for {url}")
            return None, None

        data = r.json()
        sol = data.get('solution', {})
        status = sol.get('status')
        response = sol.get('response', '')

        if status == 200:
            return 200, response
        else:
            logging.warning(f"[TRAWL] Solution status {status} for {url}")
            return status, response

    except Exception as e:
        logging.warning(f"[TRAWL] Error fetching {url}: {e}")
        return None, None


def trawl_fetch_json(url, max_timeout=60000):
    """
    Fetch JSON from a URL through TRAWL.
    Returns parsed dict or None on failure.
    """
    status, content = trawl_fetch(url, max_timeout)
    if status == 200 and content:
        try:
            # TRAWL may wrap JSON in HTML <pre> tags
            pre_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
            if pre_match:
                return json.loads(pre_match.group(1))
            return json.loads(content)
        except Exception as e:
            logging.warning(f"[TRAWL] JSON parse error: {e}")
            return None
    return None
