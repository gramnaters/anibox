from flask import Blueprint, render_template, request

from app.routes.utils import respond_with
from app.status_monitor import (
    is_checking, request_refresh, snapshot, start,
)

status_bp = Blueprint('status', __name__)


@status_bp.route('/status')
def status_page():
    start()
    return render_template('status.html')


@status_bp.route('/api/status')
def api_status():
    start()
    if request.args.get('refresh') == '1':
        request_refresh()
    data = snapshot()
    data['checking'] = is_checking()
    return respond_with(data, cache_seconds=0)
