"""Private WhatsApp media ingestion and retrieval; never expose storage keys to clients."""
from __future__ import annotations

import hashlib
import io
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app

ALLOWED_TYPES = {
    'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
    'application/pdf': '.pdf', 'audio/ogg': '.ogg', 'audio/mpeg': '.mp3',
    'audio/mp4': '.m4a', 'audio/aac': '.aac', 'audio/amr': '.amr',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'text/plain': '.txt',
}
MAX_BYTES = 16 * 1024 * 1024

class MediaError(ValueError):
    pass


def validate_content(content: bytes, mime: str) -> None:
    if mime not in ALLOWED_TYPES:
        raise MediaError('Unsupported media content type')
    if not content or len(content) > current_app.config.get('MEDIA_MAX_BYTES', MAX_BYTES):
        raise MediaError('Media is empty or exceeds the configured size limit')
    signatures = {'image/jpeg': (b'\xff\xd8\xff',), 'image/png': (b'\x89PNG\r\n\x1a\n',),
                  'image/webp': (b'RIFF',), 'application/pdf': (b'%PDF-',),
                  'audio/ogg': (b'OggS',), 'audio/mpeg': (b'ID3', b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'),
                  'audio/amr': (b'#!AMR',)}
    if mime in signatures and not any(content.startswith(s) for s in signatures[mime]):
        raise MediaError('File contents do not match declared type')
    if mime == 'image/webp' and content[8:12] != b'WEBP':
        raise MediaError('Invalid WEBP file')
    if mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or mime == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        if not content.startswith(b'PK\x03\x04'):
            raise MediaError('Invalid Office Open XML file')


def _s3_client():
    import boto3
    return boto3.client('s3', region_name=current_app.config['STORAGE_REGION'])


def store_private(data: bytes, mime: str, *, business_id: int) -> tuple[str, str]:
    validate_content(data, mime)
    key = f'{business_id}/{uuid.uuid4().hex}{ALLOWED_TYPES[mime]}'
    sha256 = hashlib.sha256(data).hexdigest()
    if current_app.config['STORAGE_BACKEND'] == 's3':
        _s3_client().put_object(Bucket=current_app.config['STORAGE_BUCKET'], Key=key, Body=data,
                                ContentType=mime, ServerSideEncryption='AES256')
    elif current_app.config['STORAGE_BACKEND'] == 'local':
        root = Path(current_app.config['STORAGE_LOCAL_PATH']).resolve()
        destination = root / key
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with destination.open('xb') as out:
            os.chmod(destination, 0o600)
            out.write(data)
    else:
        raise MediaError('Unsupported storage backend')
    return key, sha256


def read_private(key: str, *, business_id: int) -> bytes:
    # The key is always generated server-side; perform a second tenant/path check.
    if not key.startswith(f'{business_id}/') or '/' in key.partition('/')[2]:
        raise MediaError('Invalid storage key')
    if current_app.config['STORAGE_BACKEND'] == 's3':
        return _s3_client().get_object(Bucket=current_app.config['STORAGE_BUCKET'], Key=key)['Body'].read()
    root = Path(current_app.config['STORAGE_LOCAL_PATH']).resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise MediaError('Invalid storage key')
    return path.read_bytes()


def _graph_json(path: str, token: str) -> dict:
    import json
    version = current_app.config['WHATSAPP_API_VERSION']
    request = Request(f'https://graph.facebook.com/{version}/{path}',
                      headers={'Authorization': f'Bearer {token}'})
    with urlopen(request, timeout=15) as resp:
        return json.load(resp)


def download_whatsapp_media(media_id: str, *, business_id: int) -> dict:
    """Fetch URL from Meta, then GET bytes with bearer token (never trust webhook URLs)."""
    token = current_app.config.get('WHATSAPP_ACCESS_TOKEN')
    if not token or not media_id or not media_id.replace('-', '').replace('_', '').isalnum():
        raise MediaError('Invalid WhatsApp media credentials or ID')
    try:
        metadata = _graph_json(media_id, token)
        mime = metadata.get('mime_type', '').split(';')[0].strip().lower()
        if mime not in ALLOWED_TYPES:
            raise MediaError('Unsupported media content type')
        size = metadata.get('file_size')
        maximum = current_app.config.get('MEDIA_MAX_BYTES', MAX_BYTES)
        if size is not None and (int(size) <= 0 or int(size) > maximum):
            raise MediaError('Media exceeds configured size limit')
        remote_url = metadata.get('url', '')
        parsed = urlparse(remote_url)
        if parsed.scheme != 'https' or parsed.hostname not in {'lookaside.fbsbx.com', 'graph.facebook.com'} or parsed.port not in (None, 443):
            raise MediaError('Untrusted media URL from provider')
        req = Request(remote_url, headers={'Authorization': f'Bearer {token}'})
        with urlopen(req, timeout=25) as resp:
            if resp.status != 200:
                raise MediaError('Media download failed')
            if resp.headers.get('Content-Length') and int(resp.headers['Content-Length']) > maximum:
                raise MediaError('Media exceeds configured size limit')
            data = resp.read(maximum + 1)
        key, digest = store_private(data, mime, business_id=business_id)
        return {'storage_key': key, 'media_mime_type': mime, 'media_size_bytes': len(data), 'media_sha256': digest}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise MediaError('Could not ingest WhatsApp media') from exc