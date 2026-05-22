import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

_REPO_ROOT = Path(__file__).resolve().parents[3]
INFO_LOG_NAME = "info.log"
ERROR_LOG_NAME = "error.log"
_REQUEST_LOGGING_KEY = "request_logging_registered"

_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

http_logger = structlog.get_logger("app.http")


class _InfoLogFilter(logging.Filter):
    """info.log: successful HTTP responses (status < 400) and non-error app logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        status_code = getattr(record, "status_code", None)
        if status_code is not None:
            return status_code < 400
        return record.levelno < logging.ERROR


class _ErrorLogFilter(logging.Filter):
    """error.log: HTTP error responses (status >= 400) and ERROR+ app logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        status_code = getattr(record, "status_code", None)
        if status_code is not None:
            return status_code >= 400
        return record.levelno >= logging.ERROR


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger for application code."""
    return structlog.get_logger(name)


def resolve_log_dir(log_dir: str | Path | None = None) -> Path:
    """Resolve and create the log directory (relative paths are under the repo root)."""
    raw = log_dir if log_dir is not None else os.environ.get("LOG_DIR", "logs")
    path = Path(raw)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _configure_structlog() -> None:
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _make_formatter(*, use_json: bool) -> structlog.stdlib.ProcessorFormatter:
    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer()
    )
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def _rotating_file_handler(
    path: Path,
    level: int,
    formatter: logging.Formatter,
    log_filter: logging.Filter,
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(log_filter)
    return handler


def _attach_file_handlers(
    root: logging.Logger,
    log_dir: Path,
    *,
    log_level: int,
) -> None:
    json_formatter = _make_formatter(use_json=True)
    root.addHandler(
        _rotating_file_handler(
            log_dir / INFO_LOG_NAME,
            logging.INFO,
            json_formatter,
            _InfoLogFilter(),
        )
    )
    root.addHandler(
        _rotating_file_handler(
            log_dir / ERROR_LOG_NAME,
            logging.INFO,
            json_formatter,
            _ErrorLogFilter(),
        )
    )
    root.setLevel(log_level)


def _log_http_response(
    event: str,
    *,
    status_code: int,
    method: str,
    path: str,
    remote_addr: str | None = None,
    **extra,
) -> None:
    """Write HTTP response logs to info.log (2xx/3xx) or error.log (4xx/5xx)."""
    fields = {
        "status_code": status_code,
        "method": method,
        "path": path,
        **extra,
    }
    if remote_addr is not None:
        fields["remote_addr"] = remote_addr

    if status_code >= 400:
        http_logger.error(event, **fields)
    else:
        http_logger.info(event, **fields)


def log_startup_error(message: str, *, exc: BaseException | None = None) -> None:
    """Write startup/configuration failures to error.log and stderr."""
    log_dir = resolve_log_dir()

    root = logging.getLogger()
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).name == ERROR_LOG_NAME
        for handler in root.handlers
    ):
        _configure_structlog()
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(_make_formatter(use_json=False))
        root.handlers.clear()
        root.addHandler(stderr_handler)
        _attach_file_handlers(root, log_dir, log_level=logging.ERROR)

    logger = logging.getLogger("app.startup")
    if exc is not None:
        logger.error(message, exc_info=exc)
    else:
        logger.error(message)


def register_request_and_error_logging(app: Flask) -> None:
    """Log requests by response status: success -> info.log, 4xx/5xx -> error.log."""
    if app.extensions.get(_REQUEST_LOGGING_KEY):
        return

    @app.before_request
    def log_request_started():
        http_logger.info(
            "request_started",
            method=request.method,
            path=request.path,
            remote_addr=request.remote_addr,
        )

    @app.after_request
    def log_request_completed(response):
        _log_http_response(
            "request_completed",
            status_code=response.status_code,
            method=request.method,
            path=request.path,
            remote_addr=request.remote_addr,
        )
        return response

    @app.errorhandler(Exception)
    def log_exception(exc: Exception):
        if isinstance(exc, HTTPException):
            return exc

        http_logger.exception(
            "unhandled_exception",
            status_code=500,
            method=request.method,
            path=request.path,
        )
        if app.config.get("DEBUG"):
            raise exc
        return jsonify({"error": "Internal server error"}), 500

    app.extensions[_REQUEST_LOGGING_KEY] = True


def setup_logging(app: Flask) -> None:
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    use_json = app.config.get("LOG_JSON", True)
    log_dir = resolve_log_dir(app.config.get("LOG_DIR", "logs"))

    _configure_structlog()

    console_formatter = _make_formatter(use_json=use_json)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(console_formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stdout_handler)
    _attach_file_handlers(root, log_dir, log_level=log_level)

    for name in ("werkzeug", "celery", "gunicorn.error", "gunicorn.access"):
        logging.getLogger(name).setLevel(log_level)
        logging.getLogger(name).propagate = True

    app.logger.handlers.clear()
    app.logger.propagate = True
    app.logger.setLevel(logging.NOTSET)

    register_request_and_error_logging(app)

    http_logger.info(
        "logging_configured",
        log_dir=str(log_dir),
        info_log=str(log_dir / INFO_LOG_NAME),
        error_log=str(log_dir / ERROR_LOG_NAME),
    )
