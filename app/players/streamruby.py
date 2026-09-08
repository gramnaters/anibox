"""
StreamRuby / StreamHG (VidHidePro) player extractor.
"""

import re
import logging
import requests

try:
    from app.players.common_utils import get_random_agent
except ImportError:
    from common_utils import get_random_agent

DOMAINS = ['rubystm.com', 'streamruby.com', 'rubystm.me',
           'hanerix.com', 'hanerix.net', 'smoothpre.com',
           'vidhidepro.com', 'vidhide.net']
NAMES = ['streamruby', 'streamhg', 'vidhidepro', 'rubystm']

ENABLED = True


def _matching(s, i, open_c, close_c):
    """s[i] == open_c; return index of matching close_c (quote-aware)."""
    depth, j, quote = 0, i, None
    while j < len(s):
        ch = s[j]
        if quote:
            if ch == '\\':
                j += 2
                continue
            if ch == quote:
                quote = None
            j += 1
            continue
        if ch in '\'"':
            quote = ch
            j += 1
            continue
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _split_top_level(s):
    parts, depth, cur, quote = [], 0, '', None
    i = 0
    while i < len(s):
        ch = s[i]
        if quote:
            cur += ch
            if ch == '\\' and i + 1 < len(s):
                cur += s[i + 1]
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '\'"':
            quote = ch
            cur += ch
            i += 1
            continue
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
        i += 1
    if cur.strip():
        parts.append(cur)
    return parts


def _unpack_packed(script):
    """Decode a Dean Edwards 'packed' JS script (p.a.c.k.e.r style)."""
    m = re.search(r'eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*(?:r|d)\s*\)', script)
    if not m:
        return script
    body_close = _matching(script, m.end() - 1, '{', '}')
    if body_close == -1:
        return script
    k = body_close + 1
    while k < len(script) and script[k] in ' \t\r\n':
        k += 1
    if k >= len(script) or script[k] != '(':
        return script
    close = _matching(script, k, '(', ')')
    if close == -1:
        return script
    parts = _split_top_level(script[k + 1:close])
    if len(parts) < 4:
        return script
    try:
        payload = parts[0].strip().strip("'\"")
        radix = int(parts[1].strip())
        words = [w.replace('\\', '') for w in parts[3].strip().strip("'\"").split('|')]
        if len(parts) >= 5 and parts[4].strip() not in ('0', '', 'false'):
            return script
    except Exception:
        return script

    digs = '0123456789abcdefghijklmnopqrstuvwxyz'

    def to_base(n):
        out = []
        while True:
            out.append(digs[n % radix])
            n //= radix
            if n == 0:
                break
        return ''.join(reversed(out))

    tokens = [to_base(i) for i in range(len(words))]
    token_re = re.compile(r'\b(' + '|'.join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)) + r')\b')

    def repl(mm):
        tok = mm.group(1)
        idx = int(tok, radix)
        return words[idx] if idx < len(words) else tok

    return token_re.sub(repl, payload)


def _reconstruct(val):
    """Reconstruct URLs hidden as 'prefix'.split('rest') by the obfuscator."""
    val = val.strip()
    if "'.split('" in val:
        prefix, rest = val.split("'.split('", 1)
        return prefix.strip().strip('"\'') + rest.strip().strip('"\'').rstrip('"')
    return val.strip('"')


def _extract_links(decoded):
    """Pull {hls4, hls3, hls2} candidates from the decoded player JS."""
    m = re.search(r'links\s*=\s*\{', decoded)
    if not m:
        m = re.search(r'var\s+links\s*=\s*\{', decoded)
    if not m:
        return []
    seg = decoded[m.end():]
    depth, j = 0, 0
    while j < len(seg):
        if seg[j] == '{':
            depth += 1
        elif seg[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    body = seg[:j]
    out = []
    for key in ('hls4', 'hls3', 'hls2'):
        mm = re.search(r'"?' + key + r'"?\s*:\s*"([^"]+)"', body)
        if mm:
            out.append((key, _reconstruct(mm.group(1))))
    return out


def _verify_hls(url, referer):
    """Return True if the candidate URL serves an HLS playlist."""
    try:
        import requests as _req
        r = _req.get(url, headers={'User-Agent': get_random_agent(), 'Referer': referer},
                     timeout=10, verify=False)
        if r.status_code != 200:
            return False
        ct = (r.headers.get('Content-Type') or '').lower()
        if 'mpegurl' in ct or '#extm3u' in r.text.lower():
            return True
        return '.m3u8' in url or '.txt' in url
    except Exception:
        return False


def get_video_from_streamruby_player(url):
    """Extract video URL from StreamRuby/StreamHG page."""
    try:
        from urllib.parse import urlparse
        page_host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers = {'User-Agent': get_random_agent(), 'Referer': 'https://hanerix.com/'}

        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        html = resp.text

        # Legacy: plain m3u8 references in the raw HTML
        for pattern in [r'file\s*:\s*"(.*?m3u8.*?)"', r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)']:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                return m.group(1), 'auto', {'request': {'Referer': page_host, 'User-Agent': headers['User-Agent']}}

        # New: Dean Edwards packed script with links={hls4,hls3,hls2}
        decoded = html
        for sc in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S):
            if 'eval(function(p,a,c,k' in sc:
                decoded = _unpack_packed(sc)
                break

        candidates = _extract_links(decoded)
        if not candidates:
            # fallback: any m3u8 in the decoded source
            flat = decoded.replace("'", '').replace('"', '')
            m = re.search(r'(https?://[^\s]+?\.m3u8[^\s]*)', flat)
            if m:
                return m.group(1), 'auto', {'request': {'Referer': page_host, 'User-Agent': headers['User-Agent']}}
            return None, None, None

        # The page player uses hls4 || hls3 || hls2; verify each until one serves HLS.
        for key, cand in candidates:
            if cand.startswith('/'):
                cand = page_host.rstrip('/') + cand
            if _verify_hls(cand, page_host):
                return cand, 'auto', {'request': {'Referer': page_host, 'User-Agent': headers['User-Agent']}}

        return None, None, None

    except Exception as e:
        logging.warning(f"[StreamRuby] {type(e).__name__}: {e}")
        return None, None, None


def get_video_from_streamhg_player(url):
    """Alias for StreamRuby."""
    return get_video_from_streamruby_player(url)
