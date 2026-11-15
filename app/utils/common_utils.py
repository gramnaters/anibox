import random, re, aiohttp

def get_random_agent():
    agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    ]
    return random.choice(agents)

async def fetch_resolution_from_m3u8(session: aiohttp.ClientSession, m3u8_url: str, headers: dict = None, timeout: int = 4):
    try:
        async with session.get(m3u8_url, headers=headers or {}, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                text = await resp.text()
                match = re.search(r'RESOLUTION=\d+x(\d+)', text)
                if match:
                    return f"{match.group(1)}p"
    except Exception:
        pass
    return None

def get_packed_data(html: str):
    """Unpack Dean Edwards p,a,c,k,e,d JavaScript"""
    try:
        from app.players.all_players import _unpack_js
        return _unpack_js(html)
    except Exception:
        return ''
