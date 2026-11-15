"""
AniBox Application Entrypoint (Universal ASGI + WSGI)
Supports:
  1. ASGI: uvicorn main:app / uvicorn run:app
  2. Gunicorn with UvicornWorker: gunicorn -k uvicorn.workers.UvicornWorker run:app
  3. Gunicorn legacy WSGI (gthread/sync): bridged transparently via a2wsgi.
"""
import sys
import os

from main import app as fastapi_app

class UniversalApp:
    def __init__(self, asgi):
        self._asgi = asgi
        self._wsgi = None

    def __call__(self, *args, **kwargs):
        # WSGI pass (environ dict with REQUEST_METHOD + start_response callable)
        if args and isinstance(args[0], dict) and 'REQUEST_METHOD' in args[0]:
            if self._wsgi is None:
                from a2wsgi import ASGIMiddleware
                self._wsgi = ASGIMiddleware(self._asgi)
            return self._wsgi(*args, **kwargs)
        # ASGI pass (scope dict with 'type', receive, send)
        return self._asgi(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._asgi, name)

app = UniversalApp(fastapi_app)

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=1)
