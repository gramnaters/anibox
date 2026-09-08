import urllib.parse, requests
from flask import Blueprint, abort
from cachetools import TTLCache
from app.routes.utils import respond_with, log_error
from app.config_parser import parse_config, get_provider_from_config
from app.mapper import make_custom_id

catalog_bp = Blueprint('catalog', __name__)
TMDB = 'https://api.themoviedb.org/3'

tmdb_cache = TTLCache(maxsize=200, ttl=3600)


def _tmdb_key():
    from config import Config
    return Config.TMDB_API_KEY or ''


def _search_tmdb(query, page=1):
    cache_key = f'search:{query}:{page}'
    if cache_key in tmdb_cache: return tmdb_cache[cache_key]
    try:
        r = requests.get(f'{TMDB}/search/tv', params={'api_key': _tmdb_key(), 'query': query, 'page': page}, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get('results', []):
            tmdb_id = str(item.get('id', ''))
            results.append({
                'id': f'hd:tmdb:{tmdb_id}',
                'tmdb_id': tmdb_id,
                'type': 'series',
                'name': (item.get('name', '') or item.get('original_name', '')),
                'poster': f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get('poster_path') else '',
                'description': (item.get('overview', '') or '')[:200],
                'year': (item.get('first_air_date', '') or '')[:4],
            })
        tmdb_cache[cache_key] = results
        return results
    except Exception as e:
        print(f'[tmdb] search error: {e}')
        return []


def _trending(page=1):
    cache_key = f'trending:{page}'
    if cache_key in tmdb_cache: return tmdb_cache[cache_key]
    try:
        r = requests.get(f'{TMDB}/trending/tv/week', params={'api_key': _tmdb_key(), 'page': page}, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get('results', []):
            tmdb_id = str(item.get('id', ''))
            results.append({
                'id': f'hd:tmdb:{tmdb_id}',
                'tmdb_id': tmdb_id,
                'type': 'series',
                'name': (item.get('name', '') or item.get('original_name', '')),
                'poster': f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get('poster_path') else '',
                'description': (item.get('overview', '') or '')[:200],
                'year': (item.get('first_air_date', '') or '')[:4],
            })
        tmdb_cache[cache_key] = results
        return results
    except Exception as e:
        print(f'[tmdb] trending error: {e}')
        return []


def _discover_anime(page=1):
    """Discover anime shows using TMDB anime keywords"""
    cache_key = f'anime:{page}'
    if cache_key in tmdb_cache: return tmdb_cache[cache_key]
    try:
        r = requests.get(f'{TMDB}/discover/tv', params={
            'api_key': _tmdb_key(), 'with_keywords': '210024',
            'sort_by': 'popularity.desc', 'page': page,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get('results', []):
            tmdb_id = str(item.get('id', ''))
            results.append({
                'id': f'hd:tmdb:{tmdb_id}',
                'tmdb_id': tmdb_id,
                'type': 'series',
                'name': item.get('name', '') or item.get('original_name', ''),
                'poster': f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get('poster_path') else '',
                'description': (item.get('overview', '') or '')[:200],
                'year': (item.get('first_air_date', '') or '')[:4],
                'rating': str(item.get('vote_average', '')),
            })
        tmdb_cache[cache_key] = results
        return results
    except Exception as e:
        print(f'[tmdb] anime discover error: {e}')
        return []


@catalog_bp.route('/catalog/<catalog_type>/<catalog_id>.json')
@catalog_bp.route('/catalog/<catalog_type>/<catalog_id>/search=<search>.json')
@catalog_bp.route('/catalog/<catalog_type>/<catalog_id>/search=<search>/skip=<skip>.json')
@catalog_bp.route('/catalog/<catalog_type>/<catalog_id>/skip=<skip>/search=<search>.json')
@catalog_bp.route('/<lang>/catalog/<catalog_type>/<catalog_id>.json')
@catalog_bp.route('/<lang>/catalog/<catalog_type>/<catalog_id>/search=<search>.json')
@catalog_bp.route('/<lang>/catalog/<catalog_type>/<catalog_id>/search=<search>/skip=<skip>.json')
@catalog_bp.route('/<lang>/catalog/<catalog_type>/<catalog_id>/skip=<skip>/search=<search>.json')
@catalog_bp.route('/<config_data>/catalog/<catalog_type>/<catalog_id>.json')
@catalog_bp.route('/<config_data>/catalog/<catalog_type>/<catalog_id>/search=<search>.json')
@catalog_bp.route('/<config_data>/catalog/<catalog_type>/<catalog_id>/search=<search>/skip=<skip>.json')
@catalog_bp.route('/<config_data>/catalog/<catalog_type>/<catalog_id>/skip=<skip>/search=<search>.json')
@catalog_bp.route('/<config_data>/<lang>/catalog/<catalog_type>/<catalog_id>.json')
@catalog_bp.route('/<config_data>/<lang>/catalog/<catalog_type>/<catalog_id>/search=<search>.json')
@catalog_bp.route('/<config_data>/<lang>/catalog/<catalog_type>/<catalog_id>/search=<search>/skip=<skip>.json')
@catalog_bp.route('/<config_data>/<lang>/catalog/<catalog_type>/<catalog_id>/skip=<skip>/search=<search>.json')
def addon_catalog(catalog_type, catalog_id, search=None, skip=None, lang=None, config_data=None):
    if catalog_id not in ['hd_all', 'hd_latest']:
        abort(404)

    try:
        if search:
            search = urllib.parse.unquote(search)
            page = 1
            try:
                if skip:
                    page = (int(skip) // 20) + 1
            except Exception:
                page = 1
            results = _search_tmdb(search, page)
        elif catalog_id == 'hd_latest':
            results = _discover_anime(1)
        else:
            results = _discover_anime(2)

        metas = []
        for item in results:
            meta_id = item.get('id', '')
            if not meta_id: continue

            metas.append({
                'id': meta_id,
                'type': 'series',
                'name': item['name'],
                'poster': item.get('poster', ''),
                'genres': item.get('genres', []),
                'description': item.get('description', ''),
                'releaseInfo': item.get('year', ''),
            })

        print(f'[catalog] TMDB: {len(metas)} results (search={search})')
        return respond_with({'metas': metas}, 7200)

    except Exception as e:
        log_error(e)
        return respond_with({'metas': []}, 3600)
