"""Provider health monitor for the /status page.

A daemon thread periodically probes every provider with a few known titles
and records whether it is up, how long it took, how many streams it returned
and which titles actually produced streams. Results stay in memory and are
served by /api/status; the page polls that endpoint, so refreshing the page
never blocks on a scrape.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.api import ALL_PROVIDERS
from app.routes.stream import PROVIDER_DISPLAY, _search_providers_for_title

# A small, stable set of titles used to exercise every provider.
PROBE_TITLES = (
    ('46260', 'Naruto', 'series', 1, 1),
    ('37854', 'One Piece', 'series', 1, 1),
    ('47480', 'The Tom and Jerry Show', 'series', 1, 1),
)

CHECK_INTERVAL = 1800   # re-check every 30 minutes
WORKERS = 3             # providers probed in parallel

_state = {'updatedAt': None, 'providers': {}}
_lock = threading.Lock()
_started = False
_checking = False
_wake = threading.Event()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_provider(pname, provider):
    started = time.time()
    entry = {
        'id': pname,
        'name': PROVIDER_DISPLAY.get(pname, pname),
        'status': 'unknown',
        'lastChecked': None,
        'responseMs': None,
        'streamCount': 0,
        'workingTitles': [],
        'error': None,
    }
    titles = []
    errors = []
    for _tid, title, ctype, season, episode in PROBE_TITLES:
        try:
            slugs = _search_providers_for_title(title, [pname], ctype, season)
            slug = next((s for p, s in slugs if p == pname), None)
            if not slug:
                continue
            data = provider.get_episode_streams(slug, season, episode)
            streams = (data or {}).get('streams') or []
            if streams:
                titles.append(title)
                entry['streamCount'] += len(streams)
        except Exception as e:
            errors.append(f'{title}: {e}')

    entry['workingTitles'] = titles
    entry['status'] = 'up' if titles else 'down'
    entry['lastChecked'] = _now()
    entry['responseMs'] = round((time.time() - started) * 1000)
    if errors:
        entry['error'] = errors[-1][:240]
    return entry


def _run():
    global _checking
    while True:
        _checking = True
        try:
            items = list(ALL_PROVIDERS.items())
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                results = list(ex.map(lambda it: _check_provider(*it), items))
            providers = {r['id']: r for r in results}
            with _lock:
                _state['providers'] = providers
                _state['updatedAt'] = _now()
        except Exception as e:
            print(f'[status] check failed: {e}', flush=True)
        finally:
            _checking = False
        _wake.wait(CHECK_INTERVAL)
        _wake.clear()


def start():
    """Start the monitor once (cheap to call on every request)."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_run, daemon=True, name='anibox-status').start()


def request_refresh():
    """Ask the monitor to re-check as soon as it can."""
    _wake.set()


def snapshot() -> dict:
    with _lock:
        return {'updatedAt': _state['updatedAt'],
                'providers': dict(_state['providers'])}


def is_checking() -> bool:
    return _checking
