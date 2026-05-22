import logging

from flask import Flask
from werkzeug.exceptions import InternalServerError, NotFound, Unauthorized

from app.common.logging import ERROR_LOG_NAME, INFO_LOG_NAME, setup_logging


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_app_errors_go_to_error_log_only(tmp_path):
    app = Flask(__name__)
    app.config.update(
        LOG_DIR=str(tmp_path / "logs"),
        LOG_LEVEL="INFO",
        LOG_JSON=True,
    )
    setup_logging(app)

    app.logger.info("info_message")
    app.logger.error("error_message")

    _flush_handlers()

    info_text = (tmp_path / "logs" / INFO_LOG_NAME).read_text(encoding="utf-8")
    error_text = (tmp_path / "logs" / ERROR_LOG_NAME).read_text(encoding="utf-8")
    assert "info_message" in info_text
    assert "error_message" not in info_text
    assert "error_message" in error_text


def test_success_response_logged_to_info_only(tmp_path):
    app = Flask(__name__)
    app.config.update(
        LOG_DIR=str(tmp_path / "logs"),
        LOG_LEVEL="INFO",
        LOG_JSON=True,
        TESTING=True,
    )
    setup_logging(app)

    @app.get("/ok")
    def ok():
        return {"ok": True}, 200

    app.test_client().get("/ok")
    _flush_handlers()

    info_text = (tmp_path / "logs" / INFO_LOG_NAME).read_text(encoding="utf-8")
    error_text = (tmp_path / "logs" / ERROR_LOG_NAME).read_text(encoding="utf-8")
    assert "request_completed" in info_text
    assert '"status_code": 200' in info_text
    assert "request_completed" not in error_text


def test_4xx_response_logged_to_error_only(tmp_path):
    app = Flask(__name__)
    app.config.update(
        LOG_DIR=str(tmp_path / "logs"),
        LOG_LEVEL="INFO",
        LOG_JSON=True,
        TESTING=True,
    )
    setup_logging(app)

    @app.get("/missing")
    def missing():
        raise NotFound("not here")

    @app.get("/unauthorized")
    def unauthorized():
        raise Unauthorized("denied")

    client = app.test_client()
    client.get("/missing")
    client.get("/unauthorized")
    _flush_handlers()

    info_text = (tmp_path / "logs" / INFO_LOG_NAME).read_text(encoding="utf-8")
    error_text = (tmp_path / "logs" / ERROR_LOG_NAME).read_text(encoding="utf-8")
    assert "request_completed" not in info_text
    assert error_text.count("request_completed") == 2
    assert '"status_code": 404' in error_text
    assert '"status_code": 401' in error_text


def test_5xx_response_logged_to_error_only(tmp_path):
    app = Flask(__name__)
    app.config.update(
        LOG_DIR=str(tmp_path / "logs"),
        LOG_LEVEL="INFO",
        LOG_JSON=True,
        TESTING=True,
    )
    setup_logging(app)

    @app.get("/fail")
    def fail():
        raise InternalServerError("server broke")

    app.test_client().get("/fail")
    _flush_handlers()

    info_text = (tmp_path / "logs" / INFO_LOG_NAME).read_text(encoding="utf-8")
    error_text = (tmp_path / "logs" / ERROR_LOG_NAME).read_text(encoding="utf-8")
    assert "request_completed" not in info_text
    assert '"status_code": 500' in error_text
    assert "request_completed" in error_text


def test_unhandled_exception_logged_to_error_only(tmp_path):
    app = Flask(__name__)
    app.config.update(
        LOG_DIR=str(tmp_path / "logs"),
        LOG_LEVEL="INFO",
        LOG_JSON=True,
        DEBUG=False,
        TESTING=True,
    )
    setup_logging(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("something broke")

    response = app.test_client().get("/boom")
    _flush_handlers()

    assert response.status_code == 500
    info_text = (tmp_path / "logs" / INFO_LOG_NAME).read_text(encoding="utf-8")
    error_text = (tmp_path / "logs" / ERROR_LOG_NAME).read_text(encoding="utf-8")
    assert "unhandled_exception" in error_text
    assert "something broke" in error_text
    assert "request_completed" not in info_text
    assert '"status_code": 500' in error_text


def test_logger_exception_includes_traceback_in_error_log(tmp_path):
    app = Flask(__name__)
    app.config.update(
        LOG_DIR=str(tmp_path / "logs"),
        LOG_LEVEL="INFO",
        LOG_JSON=True,
    )
    setup_logging(app)

    try:
        raise ValueError("trace this")
    except ValueError:
        app.logger.exception("caught_failure")

    _flush_handlers()

    info_text = (tmp_path / "logs" / INFO_LOG_NAME).read_text(encoding="utf-8")
    error_text = (tmp_path / "logs" / ERROR_LOG_NAME).read_text(encoding="utf-8")
    assert "caught_failure" not in info_text
    assert "caught_failure" in error_text
    assert "trace this" in error_text
