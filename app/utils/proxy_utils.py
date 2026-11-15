import aiohttp
from config import Config

async def generate_proxy_url(session: aiohttp.ClientSession, destination_url: str, endpoint: str = '/proxy/stream', request_headers: dict = None, response_headers: dict = None, proxy_index: int = 0) -> str:
    """Return direct or proxied destination URL"""
    return destination_url

async def proxy_get(session: aiohttp.ClientSession, url: str, headers: dict = None, timeout: int = 10, **kwargs) -> tuple[str | None, int]:
    """Fetch URL and return (html_text, proxy_index)"""
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout), **kwargs) as resp:
            if resp.status == 200:
                return await resp.text(), -1
            return None, -1
    except Exception:
        return None, -1
