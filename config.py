import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    FLASK_HOST = os.getenv('FLASK_RUN_HOST', 'localhost')
    FLASK_PORT = os.getenv('FLASK_RUN_PORT', '5000')
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 600
    DEBUG = os.getenv('FLASK_DEBUG', 'False')
    TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')
    STREAM_MODE = os.getenv('STREAM_MODE', 'direct').lower()
    ENABLE_PROXY_ROUTES = os.getenv('ENABLE_PROXY_ROUTES', '1') in ('1', 'true', 'True', 'yes')
    DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
    # Use a writable, ephemeral path by default so deployments on platforms
    # with a read-only filesystem (Render free tier) don't crash on import.
    DB_PATH = os.getenv('DB_PATH', '/tmp/mappings.db')
    DATABASE_URL = os.getenv('DATABASE_URL', '')
