"""Gunicorn configuration — keeps app logging and emits access lines to stdout."""

import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

# Visible in `docker compose logs api` (in addition to app JSON logs).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
capture_output = True
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)s'
)


def post_fork(server, worker):
    """Re-apply logging after Gunicorn configures loggers in the worker process."""
    from run import app
    from app.common.logging import setup_logging

    setup_logging(app)
