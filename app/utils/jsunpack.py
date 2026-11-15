import re

def _matching(s, open_idx, open_c, close_c):
    depth = 0
    j = open_idx
    quote = None
    while j < len(s):
        ch = s[j]
        if quote:
            if ch == '\\' and j + 1 < len(s):
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

def unpack(script: str) -> str:
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
        return words[idx] if idx < len(words) and words[idx] else tok

    return token_re.sub(repl, payload)
