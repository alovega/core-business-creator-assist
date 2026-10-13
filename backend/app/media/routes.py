"""Private, tenant-scoped media content endpoint."""
import io
from flask import g, jsonify, send_file
from pony.orm import db_session
from app.common.rbac.decorators import login_required, business_required, permission_required
from app.common.rbac.permissions import PermissionKey
from app.messages.models import Message
from app.media.services import MediaError, read_private

from app.media import media_bp

@media_bp.get('/<int:message_id>')
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_CONVERSATIONS)
@db_session
def download_media(message_id):
    message = Message.get(id=message_id, business=g.current_business)
    if message is None or not message.storage_key or message.media_status != 'ready':
        return jsonify({'error': 'Media not found'}), 404
    try:
        data = read_private(message.storage_key, business_id=g.current_business.id)
    except (MediaError, OSError):
        return jsonify({'error': 'Media unavailable'}), 404
    response = send_file(io.BytesIO(data), mimetype=message.media_mime_type or 'application/octet-stream',
                         as_attachment=False, download_name=message.media_filename or f'media-{message.id}')
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response