from flask import Flask, render_template, request, make_response, send_from_directory, Blueprint
from flask_compress import Compress
import logging, os, hashlib, sys, io

# Fix Unicode on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import Config

from app.routes.manifest import manifest_bp, MANIFEST
from app.routes.catalog import catalog_bp
from app.routes.meta import meta_bp
from app.routes.stream import stream_bp
from app.routes.proxy import proxy_bp

app = Flask(__name__, template_folder='./templates', static_folder='./static')
app.config.from_object('config.Config')
app.register_blueprint(manifest_bp)
app.register_blueprint(catalog_bp)
app.register_blueprint(meta_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(proxy_bp)

Compress(app)
logging.basicConfig(format='%(asctime)s %(message)s')

@app.route('/')
@app.route('/<lang>/')
def index(lang=None):
    return render_template('configure.html')

@app.route('/configure')
@app.route('/<lang>/configure')
def configure(lang=None):
    return render_template('configure.html')

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.png')

@app.route('/.well-known/ai-plugin.json')
@app.route('/health')
def health():
    return {'status': 'ok', 'version': MANIFEST['version']}

@app.route('/debug')
def debug():
    from config import Config
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
        'tmdb_configured': has_tmdb,
        'tmdb_test': tmdb_test,
        'python_version': __import__('sys').version,
    }


@app.route('/diagnose')
def diagnose():
    """Report what upstream sites actually return from this server's IP
    (CF challenge vs real content) — used to debug datacenter IP blocking."""
    import requests as _rq
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    out = {}
    probes = {
        'multimovies_search': 'https://multimovies.beer/?s=Inception',
        'multimovies_home': 'https://multimovies.beer/',
        'nxsha_home': 'https://nxsha.space/',
        'iqsmart_home': 'https://pro.iqsmartgames.com/',
    }
    # Stream-level servers (the ones actually serving m3u8/segments)
    stream_probes = {
        'streamhg_hanerix': 'https://hanerix.com/',
        'rpmshare_rpmhub': 'https://multimovies.rpmhub.site/',
        'streamhg_smoothpre': 'https://smoothpre.com/',
        'nxsha_hls_cdn': 'https://img1.klcxm.com/',
        'animeworld_zephyrix': 'https://play.zephyrix.org/',
    }
    for name, url in probes.items():
        try:
            r = _rq.get(url, headers={'User-Agent': UA}, timeout=20, verify=False)
            t = r.text or ''
            low = t.lower()
            out[name] = {
                'status': r.status_code,
                'len': len(t),
                'has_result_item': 'result-item' in t,
                'cf_challenge': ('challenge-platform' in low or 'cf-chl' in low
                                 or 'just a moment' in low or 'cf-please-wait' in low
                                 or 'captcha' in low or 'turnstile' in low),
                'server': r.headers.get('server', ''),
                'cf_ray': bool(r.headers.get('cf-ray')),
            }
        except Exception as e:
            out[name] = {'error': f'{type(e).__name__}: {str(e)[:80]}'}
    for name, url in stream_probes.items():
        try:
            r = _rq.get(url, headers={'User-Agent': UA}, timeout=20, verify=False)
            out[name] = {'status': r.status_code, 'len': len(r.text or ''), 'server': r.headers.get('server', '')}
        except Exception as e:
            out[name] = {'error': f'{type(e).__name__}: {str(e)[:80]}'}
    # POST endpoints (resolvers)
    try:
        r = _rq.post('https://pro.iqsmartgames.com/embedhelper2.php',
                     data={'sid': 'abt92w4', 'UserFavSite': '', 'currentDomain': '[]'},
                     headers={'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded'},
                     timeout=20, verify=False)
        out['iqsmart_embedhelper2_POST'] = {'status': r.status_code, 'body': (r.text or '')[:120]}
    except Exception as e:
        out['iqsmart_embedhelper2_POST'] = {'error': f'{type(e).__name__}: {str(e)[:80]}'}

    # modiplay embed chain (self-contained, non-blocked path)
    try:
        r = _rq.get('https://rozgarlelo.modiplay.xyz/embed/imdb/movie?id=tt34339725',
                    headers={'User-Agent': UA}, timeout=25, verify=False)
        t = r.text or ''
        out['modiplay_embed'] = {'status': r.status_code, 'len': len(t),
                                 'has_iframe': '<iframe' in t,
                                 'has_proxy': '/proxy.php' in t}
    except Exception as e:
        out['modiplay_embed'] = {'error': f'{type(e).__name__}: {str(e)[:80]}'}
    try:
        r = _rq.get('https://rozgarlelo.modiplay.xyz/proxy.php?p=streamhg&c=q7cx9vgs8lv8&title=x&noredirect=1',
                    headers={'User-Agent': UA}, timeout=25, verify=False)
        t = r.text or ''
        out['modiplay_proxy'] = {'status': r.status_code, 'len': len(t),
                                 'has_e_path': '/e/' in t,
                                 'has_directSrc': 'directSrc' in t,
                                 'has_hanerix': 'hanerix' in t}
    except Exception as e:
        out['modiplay_proxy'] = {'error': f'{type(e).__name__}: {str(e)[:80]}'}
    try:
        r = _rq.get('https://vibuxer.com/e/q7cx9vgs8lv8', headers={'User-Agent': UA}, timeout=25, verify=False)
        t = r.text or ''
        out['vibuxer_e_page'] = {'status': r.status_code, 'len': len(t), 'has_packer': 'eval(function' in t}
    except Exception as e:
        out['vibuxer_e_page'] = {'error': f'{type(e).__name__}: {str(e)[:80]}'}
    return out


if __name__ == '__main__':
    port = int(Config.FLASK_PORT) if Config.FLASK_PORT.isdigit() else 5000
    print(f'AniBox | http://localhost:{port}')
    print(f'Configure: http://localhost:{port}/configure')
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG == 'True')
