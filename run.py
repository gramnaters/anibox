"""
AniBox Application Entrypoint (FastAPI ASGI)
Re-exports the FastAPI app instance from main.py for backward compatibility
with runners looking for run:app or main:app.
"""
import sys, os
from main import app

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=1)
