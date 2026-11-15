import aiohttp
from config import Config

async def generate_proxy_url(session: aiohttp.ClientSession, destination_url: str, endpoint: str = '/proxy/stream', request_headers: dict = None, response_headers: dict = None, proxy_index: int = 0) -> str:
    """Return direct or proxied destination URL"""
    return destination_url
