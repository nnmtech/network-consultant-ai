import multiprocessing
import os

bind = "0.0.0.0:3000"
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count()))
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 120
timeout = 300
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()

preload_app = False

def on_starting(server):
    server.log.info("Gunicorn master starting")

def when_ready(server):
    server.log.info(f"Gunicorn ready with {workers} workers")

def worker_int(worker):
    worker.log.info(f"Worker {worker.pid} interrupted")

def worker_abort(worker):
    worker.log.error(f"Worker {worker.pid} aborted")