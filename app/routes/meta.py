import re
from urllib.parse import unquote
import requests
from flask import Blueprint
from cachetools import TTLCache
from app.routes.utils import respond_with, log_error
from app.api import ALL_PROVIDERS

meta_bp = Blueprint('meta', __name__)
TMDB = 'https://api.themoviedb.org/3'
meta_cache = TTLCache(maxsize=1000, ttl=86400)


def _tmdb_key():
    from config import Config
    return Config.TMDB_API_KEY or ''


def _clean_title_for_tmdb(title: str) -> str:
    """Strip season numbers, release years, and file tags so TMDB search succeeds."""
    if not title:
        return ''
    t = re.sub(r'\s*\((?:19|20)\d{2}\)', '', title)
    t = re.sub(r'\s*-\s*Season\s*\d+.*$', '', t, flags=re.I)
    t = re.sub(r'\s*Season\s*\d+.*$', '', t, flags=re.I)
    t = re.sub(r'\s*S\d+.*$', '', t, flags=re.I)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'\s*-\s*\d+$', '', t)  # strip trailing id numbers like "-171982"
    return t.strip()


def _search_tmdb_info(title: str, content_type: str = 'tv') -> dict:
    """Find the best TMDB match for a show or movie by title."""
    clean = _clean_title_for_tmdb(title)
    if not clean:
        return None
    cache_key = f'tmdb_search:{content_type}:{clean.lower()}'
    if cache_key in meta_cache:
        return meta_cache[cache_key]
    try:
        endpoint = 'movie' if content_type == 'movie' else 'tv'
        r = requests.get(f'{TMDB}/search/{endpoint}', params={
            'api_key': _tmdb_key(),
            'query': clean,
        }, timeout=8)
        r.raise_for_status()
        results = r.json().get('results') or []
        if results:
            best = results[0]
            meta_cache[cache_key] = best
            return best
    except Exception as e:
        print(f'[tmdb] search error for "{clean}": {e}')
    meta_cache[cache_key] = None
    return None


def _get_tmdb_details(tmdb_id, content_type='tv'):
    cache_key = f'detail:{content_type}:{tmdb_id}'
    if cache_key in meta_cache:
        return meta_cache[cache_key]
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
            'background': f"https://image.tmdb.org/t/p/original{data['backdrop_path']}" if data.get('backdrop_path') else '',
            'description': (data.get('overview', '') or '')[:500],
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
    if cache_key in meta_cache:
        return meta_cache[cache_key]
    try:
        r = requests.get(f'{TMDB}/tv/{tmdb_id}/season/{season_num}', params={'api_key': _tmdb_key()}, timeout=10)
        r.raise_for_status()
        data = r.json()
        eps = []
        for ep in data.get('episodes', []):
            still = ep.get('still_path')
            eps.append({
                'season': season_num,
                'episode': ep['episode_number'],
                'title': ep.get('name', f'Episode {ep["episode_number"]}'),
                'thumbnail': f'https://image.tmdb.org/t/p/w500{still}' if still else '',
                'overview': (ep.get('overview', '') or '')[:300],
                'released': ep.get('air_date', '') or '',
            })
        meta_cache[cache_key] = eps
        return eps
    except Exception as e:
        print(f'[tmdb] season {season_num} error for {tmdb_id}: {e}')
        return []


def _is_ugly_title(title: str, ep_num: int = 1) -> bool:
    """Detect broken/scraped titles like 'NextS1 · E2', 'E125m', 'E1', etc."""
    if not title:
        return True
    t = title.strip()
    if re.match(r'^(?:Next)?S\d+\s*·\s*E\d+$', t, re.I):
        return True
    if re.match(r'^E\d+\s*\d+m$', t, re.I):
        return True
    if re.match(r'^(?:S\d+)?E\d+$', t, re.I):
        return True
    if t.lower() in (f'episode {ep_num}', f'e{ep_num}', f'ep {ep_num}'):
        return True
    return False


def _provider_meta(pname, slug, meta_id, meta_type=None):
    """Meta for a provider-scoped id (hd:<provider>:<slug>) enriched with TMDB images/details."""
    provider = ALL_PROVIDERS.get(pname)
    if not provider:
        return respond_with({'meta': {}})
    try:
        detail = provider.get_anime_details(slug) or {}
    except Exception as e:
        print(f'[meta] {pname} detail error: {e}')
        detail = {}

    name = detail.get('title') or str(slug).split('/')[-1].replace('-', ' ').title()
    # Strip slug numeric IDs for clean title search
    name = re.sub(r'-\d+$', '', name).strip()

    is_movie = False
    if meta_type == 'movie':
        is_movie = True
    elif (detail.get('type') or '') == 'movie':
        is_movie = True
    elif str(slug).startswith('movie/'):
        is_movie = True

    c_type = 'movie' if is_movie else 'series'

    # Enrich from TMDB
    tmdb_info = _search_tmdb_info(name, c_type)
    tmdb_id = tmdb_info.get('id') if tmdb_info else None

    poster = detail.get('poster') or ''
    if (not poster or 'logo' in poster.lower() or not poster.startswith('http') or 'placeholder' in poster or 'no-poster' in poster) and tmdb_info and tmdb_info.get('poster_path'):
        poster = f"https://image.tmdb.org/t/p/w500{tmdb_info['poster_path']}"

    background = ''
    if tmdb_info and tmdb_info.get('backdrop_path'):
        background = f"https://image.tmdb.org/t/p/original{tmdb_info['backdrop_path']}"

    description = detail.get('description') or (tmdb_info.get('overview') if tmdb_info else '') or ''
    genres = detail.get('genres') or []
    release_info = ''
    if tmdb_info:
        release_info = (tmdb_info.get('first_air_date') or tmdb_info.get('release_date') or '')[:4]

    meta = {
        'id': meta_id,
        'type': c_type,
        'name': name,
        'poster': poster,
        'background': background,
        'description': description[:500],
        'genres': genres,
        'releaseInfo': release_info,
    }

    if is_movie:
        meta['behaviorHints'] = {'defaultVideoId': meta_id, 'hasScheduledVideos': False}
        meta['videos'] = []
        return respond_with({'meta': meta}, 86400)

    # For series, gather episode still/thumbnails and titles from TMDB
    tmdb_ep_map = {}
    if tmdb_id:
        # Check season numbers from provider or fetch season 1
        seasons_to_fetch = set()
        for e in (detail.get('episodes') or []):
            seasons_to_fetch.add(e.get('season', 1) or 1)
        if not seasons_to_fetch:
            seasons_to_fetch = {1}
        for s_num in sorted(seasons_to_fetch)[:8]:
            for ep in _get_season_episodes(tmdb_id, s_num):
                tmdb_ep_map[(ep['season'], ep['episode'])] = ep

    eps = detail.get('episodes') or []
    videos = []
    if eps:
        for e in eps:
            s = e.get('season', 1) or 1
            ep = e.get('episode', 1) or 1
            tmdb_ep = tmdb_ep_map.get((s, ep))

            raw_title = e.get('title') or ''
            if _is_ugly_title(raw_title, ep):
                title = (tmdb_ep.get('title') if tmdb_ep else None) or f'Episode {ep}'
            else:
                title = raw_title or (tmdb_ep.get('title') if tmdb_ep else None) or f'Episode {ep}'

            thumbnail = (tmdb_ep.get('thumbnail') if tmdb_ep else None) or e.get('thumbnail') or poster
            overview = (tmdb_ep.get('overview') if tmdb_ep else None) or e.get('overview') or ''
            released = (tmdb_ep.get('released') if tmdb_ep else None) or e.get('released') or ''

            v = {
                'id': f'{meta_id}:{s}:{ep}',
                'title': title,
                'season': s,
                'episode': ep,
            }
            if thumbnail:
                v['thumbnail'] = thumbnail
            if overview:
                v['overview'] = overview
            if released:
                v['released'] = released
            videos.append(v)

    # Fallback to TMDB episodes if provider scraped 0 episodes
    if not videos and tmdb_id and tmdb_ep_map:
        for (s, ep), ep_data in sorted(tmdb_ep_map.items()):
            v = {
                'id': f'{meta_id}:{s}:{ep}',
                'title': ep_data.get('title') or f'Episode {ep}',
                'season': s,
                'episode': ep,
            }
            if ep_data.get('thumbnail'):
                v['thumbnail'] = ep_data['thumbnail']
            if ep_data.get('overview'):
                v['overview'] = ep_data['overview']
            if ep_data.get('released'):
                v['released'] = ep_data['released']
            videos.append(v)

    if not videos:
        for i in range(1, 13):
            videos.append({
                'id': f'{meta_id}:1:{i}',
                'title': f'Episode {i}',
                'season': 1,
                'episode': i,
                'thumbnail': poster,
            })

    videos.sort(key=lambda x: (x.get('season', 1), x.get('episode', 1)))
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
        except Exception:
            pass

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
        'background': details.get('background', ''),
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
    for s in details.get('seasons', [])[:6]:
        episodes = _get_season_episodes(tmdb_id, s['season'])
        for ep in episodes:
            v = {
                'id': f"{meta_id}:{ep['season']}:{ep['episode']}",
                'title': ep.get('title') or f"Episode {ep['episode']}",
                'season': ep['season'],
                'episode': ep['episode'],
            }
            if ep.get('thumbnail'):
                v['thumbnail'] = ep['thumbnail']
            if ep.get('overview'):
                v['overview'] = ep['overview']
            if ep.get('released'):
                v['released'] = ep['released']
            videos.append(v)

    if not videos:
        for i in range(1, 13):
            videos.append({
                'id': f"{meta_id}:1:{i}",
                'title': f'Episode {i}',
                'season': 1,
                'episode': i,
                'thumbnail': details.get('poster', ''),
            })

    videos.sort(key=lambda x: (x.get('season', 1), x.get('episode', 1)))
    meta['videos'] = videos
    return respond_with({'meta': meta}, 86400)
