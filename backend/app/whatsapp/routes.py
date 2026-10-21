"""Verified Meta Cloud API webhook; routes messages by registered phone-number ID."""
from __future__ import annotations
import hashlib
import hmac
from datetime import datetime
from flask import current_app, jsonify, request
from pony.orm import db_session, commit
from app.businesses.models import Business
from app.conversations.models import Conversation
from app.customers.services import get_or_create_customer_from_whatsapp
from app.messages.models import Message
from app.media.services import MediaError, download_whatsapp_media
from app.whatsapp import whatsapp_bp

MEDIA_TYPES = {'image', 'audio', 'document'}

@whatsapp_bp.get('/webhook')
def verify_webhook():
    if (request.args.get('hub.mode') == 'subscribe' and
        hmac.compare_digest(request.args.get('hub.verify_token', ''),
                            current_app.config.get('WHATSAPP_VERIFY_TOKEN', '') or '\0')):
        return request.args.get('hub.challenge', ''), 200
    return jsonify({'error': 'Invalid verification token'}), 403

@whatsapp_bp.post('/webhook')
def receive_webhook():
    raw = request.get_data()
    secret = current_app.config.get('META_APP_SECRET')
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not secret or not hmac.compare_digest(
        signature, 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    ):
        return jsonify({'error': 'Invalid signature'}), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
        return jsonify({'error': 'Invalid event'}), 400
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            if change.get('field') != 'messages':
                continue
            value = change.get('value') or {}
            phone_id = (value.get('metadata') or {}).get('phone_number_id')
            if not phone_id:
                continue
            with db_session:
                businesses = [b for b in Business.select() if (b.settings_json or {}).get('whatsapp_phone_number_id') == phone_id and b.status == 'active']
                # Fail closed if an integration isn't mapped uniquely to a tenant.
                if len(businesses) != 1:
                    current_app.logger.warning('Unmapped or ambiguous WhatsApp phone ID')
                    continue
                business = businesses[0]
                contacts = {c.get('wa_id'): (c.get('profile') or {}).get('name') for c in value.get('contacts', [])}
                for incoming in value.get('messages', []):
                    _receive_message(business, incoming, contacts)
    return jsonify({'received': True}), 200


def _receive_message(business, incoming, contacts):
    sender = incoming.get('from')
    provider_id = incoming.get('id')
    kind = incoming.get('type')
    if not sender or not provider_id or kind not in {'text', *MEDIA_TYPES}:
        return
    if Message.get(business=business, provider_message_id=provider_id):
        return  # Meta webhook retry
    try:
        customer, _ = get_or_create_customer_from_whatsapp(business=business, phone_number=sender,
                                                           name=contacts.get(sender))
    except ValueError:
        return
    conversation = Conversation.get(business=business, customer_id=customer.id, channel='whatsapp')
    if conversation is None:
        conversation = Conversation(business=business, customer_id=customer.id,
                                    channel='whatsapp', contact_phone_number=sender)
    details = incoming.get(kind) or {}
    media_id = details.get('id') if kind in MEDIA_TYPES else None
    message_fields = {
        'business': business,
        'conversation': conversation,
        'customer_id': customer.id,
        'direction': 'incoming',
        'channel': 'whatsapp',
        'message_type': kind,
        'provider_message_id': provider_id,
        'status': 'received',
    }
    body = details.get('body') if kind == 'text' else details.get('caption')
    if body is not None:
        message_fields['body'] = body
    if media_id is not None:
        message_fields['provider_media_id'] = media_id
        message_fields['media_status'] = 'pending'
    if kind == 'document' and details.get('filename') is not None:
        message_fields['media_filename'] = details['filename']
    message = Message(**message_fields)
    conversation.last_message_at = message.created_at
    conversation.updated_at = datetime.utcnow()
    conversation.unread_count += 1
    commit()
    if media_id:
        # Synchronous ingestion for minimal integration; Celery recommended for production.
        try:
            fields = download_whatsapp_media(media_id, business_id=business.id)
            for name, value in fields.items():
                setattr(message, name, value)
            message.media_status = 'ready'
        except MediaError:
            current_app.logger.warning('Media ingestion failed for message id %s', message.id)
            message.media_status = 'rejected'
        commit()