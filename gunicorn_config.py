import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
# The HLS proxy keeps URL->headers mappings in-process, so all requests must
# be served by the same worker. Threads provide concurrency for segment
# fetches without splitting that state across processes.
workers = int(os.getenv('GUNICORN_WORKERS', '1'))
worker_class = 'gthread'
threads = int(os.getenv('GUNICORN_THREADS', '8'))
worker_connections = 1000
timeout = 120
keepalive = 2
accesslog = '-'
errorlog = '-'
loglevel = 'info'
