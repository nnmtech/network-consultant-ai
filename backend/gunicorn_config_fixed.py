import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count()))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
keepalive = 5

timeout = 120
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()

preload_app = False

def on_starting(server):
    server.log.info("Starting Gunicorn server")

def on_reload(server):
    server.log.info("Reloading Gunicorn server")

def worker_int(worker):
    worker.log.info(f"Worker {worker.pid} received SIGINT")

def worker_abort(worker):
    worker.log.info(f"Worker {worker.pid} received SIGABRT")

def pre_fork(server, worker):
    pass

def post_fork(server, worker):
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    server.log.info("Forked child, re-executing")

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")

def worker_exit(server, worker):
    server.log.info(f"Worker {worker.pid} exited")