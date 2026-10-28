"""Browsable OpenAPI reference; deliberately independent of database initialization."""

from pathlib import Path

from flask import Blueprint, send_from_directory

api_docs_bp = Blueprint("api_docs", __name__)
DOCS_DIR = Path(__file__).resolve().parent


@api_docs_bp.get('/api/openapi.json')
def openapi_spec():
    return send_from_directory(DOCS_DIR, 'openapi.json', mimetype='application/json', max_age=0)


@api_docs_bp.get('/api/docs')
@api_docs_bp.get('/api/docs/')
def swagger_ui():
    return send_from_directory(DOCS_DIR, 'swagger.html', mimetype='text/html', max_age=0)