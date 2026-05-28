"""Gunicorn configuration — keeps app logging and emits access lines to stdout."""

import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

# Visible in `docker compose logs api` (in addition to app JSON logs).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
capture_output = True
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)s'
)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


_dev_reload = (
    os.environ.get("FLASK_ENV", "development") == "development"
    and _env_bool("FLASK_USE_RELOADER", True)
)
reload = _dev_reload
# Auto-reload only supports a single worker process.
workers = 1 if _dev_reload else int(os.environ.get("GUNICORN_WORKERS", "2"))


def post_fork(server, worker):
    """Re-apply logging after Gunicorn configures loggers in the worker process."""
    from run import app
    from app.common.logging import setup_logging

    setup_logging(app)
