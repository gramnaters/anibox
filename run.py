"""AniBox Application Entrypoint (FastAPI ASGI)"""
import os
import uvicorn
from main import app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=1)
