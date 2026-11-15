import hashlib, orjson, random, logging
from fastapi.responses import Response

def respond_with(data, cache_seconds=600, request=None):
    payload_bytes = orjson.dumps(data)
    etag = hashlib.md5(payload_bytes).hexdigest()

    if request:
        inm = request.headers.get('if-none-match', '')
        if inm and (inm == f'"{etag}"' or inm == etag):
            headers = {
                'ETag': f'"{etag}"',
                'Access-Control-Allow-Origin': '*',
            }
            if cache_seconds:
                headers['Cache-Control'] = f'public, s-maxage={cache_seconds}, max-age={cache_seconds}, stale-while-revalidate=60'
            return Response(status_code=304, headers=headers)

    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': '*',
        'ETag': f'"{etag}"',
    }

    if cache_seconds:
        headers['Cache-Control'] = f'public, s-maxage={cache_seconds}, max-age={cache_seconds}, stale-while-revalidate=60'
        headers['CDN-Cache-Control'] = f'public, s-maxage={cache_seconds}, stale-while-revalidate=60'
        headers['Cloudflare-CDN-Cache-Control'] = f'public, max-age={cache_seconds}, stale-while-revalidate=60'
    else:
        headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        headers['CDN-Cache-Control'] = 'no-store'
        headers['Cloudflare-CDN-Cache-Control'] = 'no-store'

    return Response(content=payload_bytes, status_code=200, media_type='application/json', headers=headers)

def get_random_agent():
    agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    ]
    return random.choice(agents)

def log_error(e):
    logging.error(f'Error: {e}', exc_info=True)
