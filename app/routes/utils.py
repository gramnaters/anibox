import logging, random, hashlib
from flask import make_response, request

try:
    import orjson
    def _dumps(data):
        return orjson.dumps(data).decode('utf-8')
except ImportError:
    import json
    def _dumps(data):
        return json.dumps(data)

def respond_with(data, cache_seconds=600):
    """Respond with CORS and multi-tier edge CDN caching headers (Cloudflare, Vercel, Render)."""
    payload_str = _dumps(data)
    etag = hashlib.md5(payload_str.encode('utf-8')).hexdigest()

    # Fast 304 Not Modified for repeat client queries
    try:
        inm = request.headers.get('If-None-Match', '')
        if inm and (inm == f'"{etag}"' or inm == etag):
            res = make_response('', 304)
            res.headers['ETag'] = f'"{etag}"'
            res.headers['Access-Control-Allow-Origin'] = '*'
            if cache_seconds:
                res.headers['Cache-Control'] = f'public, s-maxage={cache_seconds}, max-age={cache_seconds}, stale-while-revalidate=60'
            return res
    except Exception:
        pass

    response = make_response(payload_str, 200)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['ETag'] = f'"{etag}"'

    if cache_seconds:
        response.headers['Cache-Control'] = f'public, s-maxage={cache_seconds}, max-age={cache_seconds}, stale-while-revalidate=60'
        response.headers['CDN-Cache-Control'] = f'public, s-maxage={cache_seconds}, stale-while-revalidate=60'
        response.headers['Cloudflare-CDN-Cache-Control'] = f'public, max-age={cache_seconds}, stale-while-revalidate=60'
    else:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['CDN-Cache-Control'] = 'no-store'
        response.headers['Cloudflare-CDN-Cache-Control'] = 'no-store'

    return response

def get_random_agent():
    agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    ]
    return random.choice(agents)

def log_error(e):
    logging.error(f'Error: {e}', exc_info=True)
