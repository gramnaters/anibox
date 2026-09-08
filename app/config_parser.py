"""
Config parsing utilities - shared between routes and run.py without circular imports.
"""
import base64
import json
import urllib.parse


def parse_config(segment: str) -> dict:
    """Parse config from URL path segment. Supports base64url + JSON."""
    if not segment:
        return _default_config()
    try:
        decoded = urllib.parse.unquote(segment)
        padded = decoded + '=' * (4 - len(decoded) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded)
            return json.loads(raw)
        except:
            pass
        return json.loads(decoded)
    except:
        return _default_config()


def _default_config():
    return {
        'source_multimovies': 'on',
        'source_nxsha': 'on',
        'source_watchanimeworld': 'on',
    }


def get_provider_from_config(config: dict) -> list:
    """Get enabled providers from config"""
    providers = []
    for k, v in config.items():
        if k.startswith('source_') and v == 'on':
            providers.append(k.replace('source_', ''))
    return providers


def encode_config(config: dict) -> str:
    """Encode config dict to base64url string for URL embedding"""
    json_str = json.dumps(config, separators=(',', ':'))
    return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip('=')
