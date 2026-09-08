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


if __name__ == '__main__':
    port = int(Config.FLASK_PORT) if Config.FLASK_PORT.isdigit() else 5000
    print(f'AniBox | http://localhost:{port}')
    print(f'Configure: http://localhost:{port}/configure')
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG == 'True')
