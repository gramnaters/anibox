import sys, io, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse

# Fix Unicode on Windows with immediate line buffering
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from app.routes.manifest import manifest_router, MANIFEST
from app.routes.catalog import catalog_router
from app.routes.meta import meta_router
from app.routes.stream import stream_router
from app.routes.proxy import proxy_router, addon_base_url
from app.routes.status import status_router
from app.status_monitor import start as start_status_monitor
from config import Config

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO,
    stream=sys.stdout,
    force=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: trigger status monitor
    start_status_monitor()
    yield

app = FastAPI(
    title="AniBox",
    description="High-speed Stremio multi-provider streaming addon for Anime & Cinema",
    version=MANIFEST.get('version', '2.4.0'),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Static and Templates
app.mount("/static", StaticFiles(directory="static"), name="static")

# Pre-cache static HTML in memory with dynamic read support
_CACHED_CONFIGURE_HTML = ""
def get_cached_configure_html():
    global _CACHED_CONFIGURE_HTML
    if not _CACHED_CONFIGURE_HTML:
        try:
            with open("templates/configure.html", "r", encoding="utf-8") as _f:
                _CACHED_CONFIGURE_HTML = _f.read()
        except Exception:
            pass
    return _CACHED_CONFIGURE_HTML

# Register API Routers
app.include_router(manifest_router)
app.include_router(catalog_router)
app.include_router(meta_router)
app.include_router(stream_router)
app.include_router(proxy_router)
app.include_router(status_router)

@app.middleware("http")
async def capture_base_url_middleware(request: Request, call_next):
    # Track the real base URL seen by client (honours reverse proxies and Render TLS)
    addon_base_url(request)
    return await call_next(request)

@app.get('/ping')
@app.head('/ping')
@app.get('/cron')
@app.head('/cron')
@app.get('/keepalive')
@app.head('/keepalive')
async def ping():
    return PlainTextResponse("OK", status_code=200)

@app.get('/', response_class=HTMLResponse)
@app.get('/{lang}/', response_class=HTMLResponse)
@app.get('/configure', response_class=HTMLResponse)
@app.get('/{lang}/configure', response_class=HTMLResponse)
async def configure_page(request: Request, lang: str = None):
    # Prevent cron-job.org & uptime monitors from failing with 'output too large'
    ua = request.headers.get('User-Agent', '').lower()
    if any(b in ua for b in ('cron-job', 'cronjob', 'uptimerobot', 'betteruptime', 'pingdom', 'statuscake', 'freshping', 'render')):
        return PlainTextResponse("OK", status_code=200)
    if any(k in request.query_params for k in ('ping', 'cron', 'health', 'keepalive')):
        return PlainTextResponse("OK", status_code=200)
    return HTMLResponse(content=get_cached_configure_html(), status_code=200)

@app.get('/favicon.ico')
async def favicon():
    return FileResponse("static/favicon.png")

@app.get('/health')
async def health():
    return {'status': 'ok', 'version': MANIFEST['version']}

@app.get('/debug')
async def debug():
    import requests
    has_tmdb = bool(Config.TMDB_API_KEY and Config.TMDB_API_KEY != 'your_tmdb_api_key_here')
    tmdb_test = 'N/A'
    if has_tmdb:
        try:
            r = requests.get('https://api.themoviedb.org/3/search/tv',
                           params={'api_key': Config.TMDB_API_KEY, 'query': 'naruto'}, timeout=10)
            tmdb_test = f"OK ({r.json().get('total_results', 0)} results)" if r.ok else f"FAIL {r.status_code}"
        except Exception as e:
            tmdb_test = f"ERROR: {str(e)[:80]}"
    return {
        'framework': 'FastAPI',
        'tmdb_configured': has_tmdb,
        'tmdb_test': tmdb_test,
        'python_version': sys.version,
    }

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 5056))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=1)
