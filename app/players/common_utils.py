"""
Common utilities shared across the application.
Ported from docchi-stremio-addon for Multianima.
"""

import re
import random


def get_random_agent(browser=None):
    """Get random user agent string."""
    USER_AGENTS_BY_BROWSER = {
        "chrome": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ],
        "firefox": [
            "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/119.0",
        ],
        "safari": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
        ],
        "opera": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 OPR/104.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 OPR/104.0.0.0",
        ]
    }

    if browser and browser.lower() in USER_AGENTS_BY_BROWSER:
        return random.choice(USER_AGENTS_BY_BROWSER[browser.lower()])
    all_agents = [agent for sublist in USER_AGENTS_BY_BROWSER.values() for agent in sublist]
    return random.choice(all_agents)


def get_packed_data(html):
    """Extract and unpack eval(function(p,a,c,k,e,...)) packed JS."""
    packed_data = ''
    for m in re.finditer(r'''(eval\s*\(function\(p,a,c,k,e,.*?)</script>''', html, re.DOTALL | re.I):
        pass
    return packed_data


def fetch_resolution_from_m3u8(m3u8_url, headers=None, timeout=2):
    """Extract maximum resolution from m3u8 playlist. Returns e.g. '1080p' or None."""
    import requests
    try:
        h = {'User-Agent': get_random_agent()}
        if headers:
            h.update(headers)
        r = requests.get(m3u8_url, headers=h, timeout=timeout, verify=False)
        if r.status_code != 200:
            return None
        resolutions = re.findall(r'RESOLUTION=\s*(\d+)x(\d+)', r.text)
        if resolutions:
            return f"{max(int(h) for w, h in resolutions)}p"
        return None
    except Exception:
        return None
