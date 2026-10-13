"""Unit-level checks for private media validation/storage."""
import pytest
from flask import Flask
from app.media.services import MediaError, read_private, store_private, validate_content

@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(STORAGE_BACKEND='local', STORAGE_LOCAL_PATH=str(tmp_path), MEDIA_MAX_BYTES=1024)
    return app

def test_private_round_trip_and_cross_tenant_block(app):
    with app.app_context():
        key, digest = store_private(b'%PDF-1.7\nhello', 'application/pdf', business_id=10)
        assert key.startswith('10/')
        assert len(digest) == 64
        assert read_private(key, business_id=10) == b'%PDF-1.7\nhello'
        with pytest.raises(MediaError):
            read_private(key, business_id=11)

def test_rejects_fake_pdf_unsupported_type_and_oversize(app):
    with app.app_context():
        with pytest.raises(MediaError):
            validate_content(b'<html>bad</html>', 'application/pdf')
        with pytest.raises(MediaError):
            validate_content(b'file', 'text/html')
        with pytest.raises(MediaError):
            validate_content(b'%PDF-' + b'X' * 1024, 'application/pdf')