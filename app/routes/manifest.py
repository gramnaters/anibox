from fastapi import APIRouter, Request
from .utils import respond_with
from app.config_parser import parse_config, get_provider_from_config
from app.api import ALL_PROVIDERS

manifest_router = APIRouter()

_PROVIDER_NAMES = {
    'multimovies': 'MultiMovies',
    'watchanimeworld': 'AnimeWorld',
    'toonstream': 'ToonStream',
    'piratexplay': 'PirateXPlay',
}

BASE_MANIFEST = {
    'id': 'com.anibox.addon',
    'version': '2.4.0',
    'name': 'AniBox',
    'description': 'AniBox — stream movies and (Hindi dub) anime from multiple providers with quality and language filters.',
    'logo': '/static/anibox-icon-512.png',
    'types': ['movie', 'series'],
    'idPrefixes': ['tt', 'tmdb:', 'hd:tmdb:', 'hd:'],
    'catalogs': [],
    'behaviorHints': {'configurable': True, 'configurationRequired': False},
    'resources': [
        {'name': 'catalog', 'types': ['series', 'movie']},
        {'name': 'meta', 'types': ['series', 'movie']},
        {'name': 'stream', 'types': ['series', 'movie']},
    ],
    'config': [
        {'key': 'source_multimovies', 'type': 'checkbox', 'title': 'MultiMovies (movies + Hindi series)', 'default': 'checked'},
        {'key': 'source_watchanimeworld', 'type': 'checkbox', 'title': 'AnimeWorld (Hindi dub series)', 'default': 'checked'},
        {'key': 'source_toonstream', 'type': 'checkbox', 'title': 'ToonStream (anime + cartoon)', 'default': 'checked'},
        {'key': 'source_piratexplay', 'type': 'checkbox', 'title': 'PirateXPlay (multi-language anime)', 'default': 'checked'},
        {'key': 'catalogs', 'type': 'checkbox', 'title': 'Show catalogs (one row per provider)', 'default': 'checked'},
        {'key': 'formatter_style', 'type': 'select', 'title': 'Stream label style', 'default': 'rich',
         'options': ['rich', 'aiostreams', 'compact', 'plain']},
    ],
}

def _catalogs_for(cfg):
    cats = []
    for pname in get_provider_from_config(cfg):
        if pname not in ALL_PROVIDERS:
            continue
        name = _PROVIDER_NAMES.get(pname, pname)
        for ctype in ('series', 'movie'):
            cat_label = f"{name} Series" if ctype == 'series' else f"{name} Movies"
            cats.append({
                'type': ctype,
                'id': f'{pname}_{ctype}',
                'name': cat_label,
                'extra': [
                    {'name': 'search', 'isRequired': False},
                    {'name': 'skip', 'isRequired': False},
                ],
            })
    return cats

def _apply_catalogs(m, cfg):
    catalogs_on = cfg.get('catalogs', 'on') != 'off'
    if catalogs_on:
        m['catalogs'] = _catalogs_for(cfg)
        m['resources'] = [
            {'name': 'catalog', 'types': ['series', 'movie']},
            {'name': 'meta', 'types': ['series', 'movie']},
            {'name': 'stream', 'types': ['series', 'movie']},
        ]
    else:
        m['catalogs'] = []
        m['resources'] = [
            {'name': 'meta', 'types': ['series', 'movie']},
            {'name': 'stream', 'types': ['series', 'movie']},
        ]
    return m

def make_manifest(config_segment=''):
    m = dict(BASE_MANIFEST)
    cfg = parse_config(config_segment or '')
    _apply_catalogs(m, cfg)
    if config_segment:
        m['id'] = f'com.anibox.{hash(config_segment) % 10000}'
    return m

def _abs_logo(manifest, request: Request):
    base_url = str(request.base_url).rstrip('/')
    manifest['logo'] = f"{base_url}/static/anibox-icon-512.png"
    return manifest

MANIFEST = BASE_MANIFEST

def _strict_config(segment):
    import base64
    import json as _json
    import urllib.parse as _up
    try:
        decoded = _up.unquote(segment)
        padded = decoded + '=' * (4 - len(decoded) % 4)
        d = _json.loads(base64.urlsafe_b64decode(padded))
        return d if isinstance(d, dict) else None
    except Exception:
        return None

@manifest_router.get('/manifest.json')
@manifest_router.get('/{segment}/manifest.json')
async def addon_manifest(request: Request, segment: str = None):
    cfg = parse_config(segment or '')
    m = dict(BASE_MANIFEST)
    _apply_catalogs(m, cfg)
    if segment and _strict_config(segment) is not None:
        m['id'] = f'com.anibox.{hash(segment) % 10000}'
    return respond_with(_abs_logo(m, request), 7200, request=request)
