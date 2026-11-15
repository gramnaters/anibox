from fastapi import APIRouter, Request
from app.routes.utils import respond_with
from app.status_monitor import is_checking, request_refresh, snapshot, start

status_router = APIRouter()

@status_router.get('/api/status')
async def api_status(request: Request, refresh: str = None):
    start()
    if refresh == '1' or request.query_params.get('refresh') == '1':
        request_refresh()
    data = snapshot()
    data['checking'] = is_checking()
    return respond_with(data, cache_seconds=0, request=request)
