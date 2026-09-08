"""
Streamtape player extractor.
Improved version with regex pattern from MediaVanced.
"""
import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['streamtape.com', 'streamtape.to', 'streamtape.site',
           'streamtape.xyz', 'streamtape.cloud', 'shavetape.cash']
NAMES = ['streamtape']

ENABLED = True


def get_video_from_streamtape_player(url):
    """Extract video URL from Streamtape page."""
    try:
        # Normalize URL
        if not url.startswith('https://streamtape.com/v/'):
            parts = url.split('/')
            video_id = parts[4] if len(parts) > 4 else None
            if not video_id:
                return None, None, None
            url = f'https://streamtape.com/v/{video_id}/'

        headers = {
            'Referer': 'https://streamtape.com/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }

        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            return None, None, None

        html = resp.text

        # Extract video URL using regex pattern from MediaVanced
        regex_pattern = r"document\.getElementById\(['\"]captchalink['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"].*?\+\s*\(['\"]([^'\"]+)['\"]\)\.substring\(\d+\);"

        video_match = re.search(regex_pattern, html)
        if video_match:
            video_url = "https:" + video_match.group(1) + video_match.group(2)[4:]
            return video_url, 'unknown', {'request': headers}

        # Fallback: try robotlink pattern
        soup_match = re.search(r"document\.getElementById\('robotlink'\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"]", html)
        if soup_match:
            first_part = soup_match.group(1)
            second_parts = re.findall(r"\(\'xcd(.*?)\'\)", html)
            if len(second_parts) >= 2:
                stream_data = first_part[:-1] + second_parts[1]
                video_url = f'https:/{stream_data}&stream=1'
                return video_url, 'unknown', {'request': headers}

        return None, None, None

    except Exception as e:
        logging.warning(f"[Streamtape] {type(e).__name__}: {e}")
        return None, None, None
