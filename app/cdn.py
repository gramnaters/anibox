"""Stable identity for the media file behind a stream URL.

Providers and players frequently expose the *same* file through different
front domains, embed IDs or freshly-minted tokens — and sometimes expose
*different* files under labels that look identical. Comparing display labels
therefore both merges distinct files and keeps duplicates.

``cdn_file_key`` reduces a resolved media URL to a key that is stable for one
file and different for distinct files, so the stream route can dedupe on
reality instead of on presentation.

Only the shape of the URL is used; no network access and no guessing.
"""
from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, unquote, urlparse

_MEDIA_EXT = re.compile(r'\.(mkv|mp4|m3u8|ts|webm|m4v|mov)$', re.I)

# Abyss file tokens are base64 blobs whose first ~36 characters identify the
# file; the tail is a per-request signature. Measured on live data: streams of
# the same file share 36-37 leading chars, distinct files share at most 1.
_ABYSS_ID_LEN = 36


def _abyss_token_id(token: str) -> str:
    """Stable file identity inside an Abyss ``/sora/<size>/<token>`` token."""
    try:
        raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
        text = raw.decode('latin-1')
        return text[:_ABYSS_ID_LEN]
    except Exception:
        return token


def _base_domain(host: str) -> str:
    """Collapse rotating edge subdomains to the registrable-ish domain.

    ``gi7owxbf32.sssrr.org`` -> ``sssrr.org``
    ``edge1-moscow-sprintcdn.owphbf24.com`` -> ``owphbf24.com``
    """
    host = (host or '').lower().split(':')[0]
    if not host or host.replace('.', '').isdigit():
        return host
    parts = [p for p in host.split('.') if p]
    if len(parts) <= 2:
        return host
    return '.'.join(parts[-2:])


def cdn_file_key(url: str):
    """Return a hashable key identifying the media file at ``url``.

    Returns ``None`` for an empty URL. The key is a tuple so callers can
    inspect its kind while debugging.
    """
    if not url:
        return None

    text = unquote(url)
    parsed = urlparse(text)
    host = (parsed.hostname or '').lower()
    path = parsed.path or ''

    # Abyss / Byse (sssrr.org): /sora/<bytes>/<token>. The token's stable
    # prefix identifies the file; its tail is a signature and rotates.
    m = re.search(r'/sora/(\d+)/([^/?#]+)', path)
    if m:
        return ('abyss', m.group(1), _abyss_token_id(m.group(2)))

    # Hanerix / StreamHG: /stream/<a>/<b>/<expiry>/<file_id>/master.m3u8
    m = re.search(r'/stream/[^/]+/[^/]+/\d+/(\d+)/', path)
    if m:
        return ('hanerix', m.group(1))

    # StreamRuby / VidMoly media playlists:
    # /hls2/.../<video_id>_,l,n,h,x,.urlset/master.m3u8
    m = re.search(r'/([a-z0-9]{6,})_[,a-z0-9]*\.urlset', path, re.I)
    if m:
        return ('streamruby', m.group(1).lower())

    # VidMoly embed page: /embed-<id>.html
    m = re.search(r'/embed-([a-z0-9]+)\.html', path, re.I)
    if m:
        return ('vidmoly', m.group(1).lower())

    # HSCow: /hls_mps/<hash>/<quality>/index_<n>.m3u8
    m = re.search(r'/hls_mps/([0-9a-f]+)/(\d+)/', path, re.I)
    if m:
        return ('hscow', m.group(1).lower(), m.group(2))

    # UPNShare style: https://cloudy.upns.one/#r513gu
    if parsed.fragment:
        return ('fragment', parsed.fragment.lower())

    # Cloudflare worker wrappers carry the real URL in ?url=<encoded>.
    query = parse_qs(parsed.query)
    if 'url' in query and query['url']:
        inner = cdn_file_key(query['url'][0])
        if inner:
            return ('wrapped',) + inner

    # Direct media file: host family + path, ignoring rotating query tokens.
    if _MEDIA_EXT.search(path):
        return ('path', _base_domain(host), path.lower())

    # Last resort: host family + path (still better than a display label).
    return ('url', _base_domain(host), path.lower())
