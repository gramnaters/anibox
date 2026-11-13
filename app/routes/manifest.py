from flask import Blueprint, request
from .utils import respond_with
from app.config_parser import parse_config, get_provider_from_config
from app.api import ALL_PROVIDERS

manifest_bp = Blueprint('manifest', __name__)

# provider key -> display name (kept local to avoid importing the stream module here)
_PROVIDER_NAMES = {
    'multimovies': 'MultiMovies',
    'watchanimeworld': 'AnimeWorld',
    'toonstream': 'ToonStream',
    'piratexplay': 'PirateXPlay',
}

BASE_MANIFEST = {
    'id': 'com.multianima.addon',
    'version': '2.0.0',
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
        # Provider sources
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
    """Series + movie catalogs per enabled provider, so each site lists
    separately and both content types are browsable."""
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
    """Build manifest with config baked in"""
    m = dict(BASE_MANIFEST)
    cfg = parse_config(config_segment or '')
    _apply_catalogs(m, cfg)
    if config_segment:
        m['id'] = f'com.multianima.{hash(config_segment) % 10000}'
    return m


def _abs_logo(manifest):
    """Make the logo URL absolute against the request host so Stremio and
    Nuvio fetch the icon from whichever domain serves the addon."""
    manifest['logo'] = request.url_root.rstrip('/') + '/static/anibox-icon-512.png'
    return manifest


MANIFEST = BASE_MANIFEST


def _strict_config(segment):
    """Decode a base64url config segment; None if the segment is not a
    valid encoded config (e.g. a language prefix like /en/)."""
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


@manifest_bp.route('/manifest.json')
@manifest_bp.route('/<segment>/manifest.json')
def addon_manifest(segment=None):
    """Single manifest route. The segment may be an encoded config (from the
    configure page) or a language tag — auto-detected by strict decode."""
    cfg = parse_config(segment or '')
    m = dict(BASE_MANIFEST)
    _apply_catalogs(m, cfg)
    if segment and _strict_config(segment) is not None:
        m['id'] = f'com.multianima.{hash(segment) % 10000}'
    return respond_with(_abs_logo(m), 7200)
