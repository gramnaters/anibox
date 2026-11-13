from urllib.parse import unquote
import requests
from flask import Blueprint
from cachetools import TTLCache
from app.routes.utils import respond_with, log_error
from app.api import ALL_PROVIDERS

meta_bp = Blueprint('meta', __name__)
TMDB = 'https://api.themoviedb.org/3'
meta_cache = TTLCache(maxsize=500, ttl=86400)


def _tmdb_key():
    from config import Config
    return Config.TMDB_API_KEY or ''


def _get_tmdb_details(tmdb_id, content_type='tv'):
    cache_key = f'detail:{content_type}:{tmdb_id}'
    if cache_key in meta_cache: return meta_cache[cache_key]
    try:
        r = requests.get(f'{TMDB}/{content_type}/{tmdb_id}', params={
            'api_key': _tmdb_key(),
            'append_to_response': 'external_ids,seasons',
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        imdb_id = (data.get('external_ids') or {}).get('imdb_id', '')
        result = {
            'id': imdb_id or f"hd:tmdb:{tmdb_id}",
            'tmdb_id': str(tmdb_id),
            'type': 'movie' if content_type == 'movie' else 'series',
            'name': data.get('name', '') or data.get('title', ''),
            'poster': f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get('poster_path') else '',
            'description': (data.get('overview', '') or '')[:300],
            'genres': [g['name'] for g in data.get('genres', [])],
            'year': (data.get('first_air_date', '') or data.get('release_date', '') or '')[:4],
            'rating': str(data.get('vote_average', '')),
            'seasons': [],
        }
        for s in data.get('seasons', []):
            if s.get('season_number', 0) > 0:
                result['seasons'].append({
                    'season': s['season_number'],
                    'episode_count': s.get('episode_count', 0),
                    'name': s.get('name', ''),
                })
        meta_cache[cache_key] = result
        return result
    except Exception as e:
        print(f'[tmdb] detail error: {e}')
        return None


def _get_season_episodes(tmdb_id, season_num):
    cache_key = f'season:{tmdb_id}:{season_num}'
    if cache_key in meta_cache: return meta_cache[cache_key]
    try:
        r = requests.get(f'{TMDB}/tv/{tmdb_id}/season/{season_num}', params={'api_key': _tmdb_key()}, timeout=10)
        r.raise_for_status()
        data = r.json()
        eps = [{'season': season_num, 'episode': ep['episode_number'],
                 'title': ep.get('name', f'E{ep["episode_number"]}'),
                 'overview': (ep.get('overview', '') or '')[:100]}
                for ep in data.get('episodes', [])]
        meta_cache[cache_key] = eps
        return eps
    except: return []


def _provider_meta(pname, slug, meta_id, meta_type=None):
    """Meta for a provider-scoped id (hd:<provider>:<slug>) from a per-provider catalog."""
    provider = ALL_PROVIDERS.get(pname)
    if not provider:
        return respond_with({'meta': {}})
    try:
        detail = provider.get_anime_details(slug) or {}
    except Exception as e:
        print(f'[meta] {pname} detail error: {e}')
        detail = {}
    name = detail.get('title') or str(slug).replace('-', ' ').title()

    is_movie = False
    if meta_type == 'movie':
        is_movie = True
    elif (detail.get('type') or '') == 'movie':
        is_movie = True
    elif str(slug).startswith('movie/'):
        is_movie = True

    c_type = 'movie' if is_movie else 'series'
    meta = {
        'id': meta_id,
        'type': c_type,
        'name': name,
        'poster': detail.get('poster') or '',
        'description': detail.get('description') or '',
        'genres': detail.get('genres') or [],
        'releaseInfo': '',
    }

    if is_movie:
        meta['behaviorHints'] = {'defaultVideoId': meta_id, 'hasScheduledVideos': False}
        meta['videos'] = []
        return respond_with({'meta': meta}, 86400)

    eps = detail.get('episodes') or []
    videos = []
    if eps:
        for e in eps:
            s = e.get('season', 1) or 1
            ep = e.get('episode', 1) or 1
            videos.append({'id': f'{meta_id}:{s}:{ep}', 'title': e.get('title') or f'Episode {ep}',
                           'season': s, 'episode': ep})
    if not videos:
        for i in range(1, 13):
            videos.append({'id': f'{meta_id}:1:{i}', 'title': f'Episode {i}', 'season': 1, 'episode': i})
    meta['videos'] = videos
    return respond_with({'meta': meta}, 86400)


@meta_bp.route('/meta/<meta_type>/<meta_id>.json')
@meta_bp.route('/<lang>/meta/<meta_type>/<meta_id>.json')
@meta_bp.route('/<config_data>/meta/<meta_type>/<meta_id>.json')
@meta_bp.route('/<config_data>/<lang>/meta/<meta_type>/<meta_id>.json')
def addon_meta(meta_type, meta_id, lang=None, config_data=None):
    meta_id = unquote(meta_id)

    # Provider-scoped meta from a per-provider catalog: hd:<provider>:<slug>
    if meta_id.startswith('hd:') and not meta_id.startswith('hd:tmdb:'):
        _p = meta_id.split(':', 2)
        if len(_p) == 3 and _p[1] in ALL_PROVIDERS:
            return _provider_meta(_p[1], _p[2].replace('~', '/'), meta_id, meta_type=meta_type)

    tmdb_id = None
    if meta_id.startswith('tmdb:'):
        tmdb_id = meta_id.replace('tmdb:', '')
    elif meta_id.startswith('hd:tmdb:'):
        tmdb_id = meta_id.replace('hd:tmdb:', '')
    elif meta_id.startswith('tt'):
        # Look up TMDB ID from IMDB
        try:
            r = requests.get(f'{TMDB}/find/{meta_id}', params={
                'api_key': _tmdb_key(), 'external_source': 'imdb_id'
            }, timeout=10)
            data = r.json()
            results = (data.get('movie_results', []) if meta_type == 'movie' else data.get('tv_results', [])) or data.get('tv_results', []) or data.get('movie_results', [])
            if results:
                tmdb_id = str(results[0]['id'])
        except: pass

    if not tmdb_id:
        return respond_with({'meta': {}})

    details = _get_tmdb_details(tmdb_id, content_type='movie' if meta_type == 'movie' else 'tv')
    if not details:
        return respond_with({'meta': {}})

    is_movie = (meta_type == 'movie' or details.get('type') == 'movie')
    meta = {
        'id': meta_id,
        'type': 'movie' if is_movie else 'series',
        'name': details['name'],
        'poster': details.get('poster', ''),
        'description': details.get('description', ''),
        'genres': details.get('genres', []),
        'releaseInfo': details.get('year', ''),
    }

    if is_movie:
        meta['behaviorHints'] = {'defaultVideoId': meta_id, 'hasScheduledVideos': False}
        meta['videos'] = []
        return respond_with({'meta': meta}, 86400)

    # Build video list from seasons (for series)
    videos = []
    for s in details.get('seasons', [])[:5]:
        episodes = _get_season_episodes(tmdb_id, s['season'])
        for ep in episodes:
            videos.append({
                'id': f"{meta_id}:{ep['season']}:{ep['episode']}",
                'title': ep['title'],
                'season': ep['season'], 'episode': ep['episode'],
            })

    if not videos:
        for i in range(1, 13):
            videos.append({
                'id': f"{meta_id}:1:{i}",
                'title': f'Episode {i}',
                'season': 1, 'episode': i,
            })

    meta['videos'] = videos
    return respond_with({'meta': meta}, 86400)
