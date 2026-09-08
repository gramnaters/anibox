from flask import Blueprint, request
from .utils import respond_with
from app.config_parser import parse_config, encode_config

manifest_bp = Blueprint('manifest', __name__)

BASE_MANIFEST = {
    'id': 'com.multianima.addon',
    'version': '2.0.0',
    'name': 'AniBox',
    'description': 'AniBox — stream movies and (Hindi dub) anime from multiple providers with quality and language filters.',
    'logo': '/static/anibox-icon-512.png',
    'types': ['movie', 'series'],
    'idPrefixes': ['tt', 'tmdb:', 'hd:tmdb:'],
    'catalogs': [
        {'type': 'series', 'id': 'hd_all', 'name': 'Hindi Dub Anime', 'extra': [
            {'name': 'search', 'isRequired': True}, {'name': 'skip', 'isRequired': False},
        ]},
        {'type': 'series', 'id': 'hd_latest', 'name': 'Latest Releases'},
    ],
    'behaviorHints': {'configurable': True, 'configurationRequired': False},
    'resources': [
        {'name': 'catalog', 'types': ['series', 'movie']},
        {'name': 'meta', 'types': ['series', 'movie']},
        {'name': 'stream', 'types': ['series', 'movie']},
    ],
    'config': [
        # Provider sources
        {'key': 'source_multimovies', 'type': 'checkbox', 'title': 'MultiMovies (movies + Hindi series)', 'default': 'checked'},
        {'key': 'source_nxsha', 'type': 'checkbox', 'title': 'NxSha (movies + series)', 'default': 'checked'},
        {'key': 'source_watchanimeworld', 'type': 'checkbox', 'title': 'AnimeWorld (Hindi dub series)', 'default': 'checked'},
    ],
    'behaviorHints': {'configurable': True, 'configurationRequired': False},
}


def make_manifest(config_segment=''):
    """Build manifest with config baked in"""
    m = dict(BASE_MANIFEST)
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
    m = dict(BASE_MANIFEST)
    if segment and _strict_config(segment) is not None:
        m['id'] = f'com.multianima.{hash(segment) % 10000}'
    return respond_with(_abs_logo(m), 7200)
