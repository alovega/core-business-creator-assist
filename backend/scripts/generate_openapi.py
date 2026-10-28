#!/usr/bin/env python3
"""Generate/check the checked-in OpenAPI 3.1 document from actual Flask route decorators.

No Flask/database import or third-party dependency is required. API examples below
are curated from routes, validators and model to_dict() methods. Every new route
appears in the generation, so the --check CI command catches documentation drift.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUTPUT = BACKEND / 'app' / 'api_docs' / 'openapi.json'
PREFIXES = {
    'auth': '/api/auth', 'businesses': '/api/businesses',
    'customers': '/api/customers', 'conversations': '/api/conversations',
    'messages': '/api/messages', 'leads': '/api/leads',
    'bookings': '/api/bookings', 'payments': '/api/payments',
    'whatsapp': '/api/whatsapp', 'users': '/api/users',
    'dashboard': '/api/dashboard', 'notifications': '/api/notifications',
    'media': '/api/media', 'automations': '/api/automations',
    'ai': '/api/ai', 'audit_logs': '/api/audit-logs',
}
DATE = '2026-10-01T10:30:00Z'

# Representative records use the exact keys and types returned by to_dict().
SAMPLES = {
    'user': {'id': 1, 'name': 'Alex Demo', 'email': 'alex@example.com', 'is_active': True,
             'role': 'owner', 'membership_status': 'active', 'current_business_id': 1,
             'business_id': 1, 'created_at': DATE, 'updated_at': DATE},
    'business': {'id': 1, 'name': 'Acme Salon', 'slug': 'acme-salon', 'phone_number': '+254700000001',
                 'email': 'alex@example.com', 'industry': 'beauty', 'plan': 'free',
                 'status': 'active', 'settings': {}, 'created_at': DATE, 'updated_at': DATE},
    'membership': {'id': 1, 'user_id': 1, 'business_id': 1, 'role': 'owner', 'status': 'active',
                   'invited_by_id': None, 'invited_at': None, 'joined_at': DATE,
                   'created_at': DATE, 'updated_at': DATE},
    'customer': {'id': 10, 'business_id': 1, 'name': 'Jane Doe', 'phone_number': '+254711222333',
                 'normalized_phone_number': '254711222333', 'email': 'jane@example.com',
                 'source': 'manual', 'tags': ['vip'], 'notes': 'Prefers afternoons',
                 'status': 'active', 'created_by_user_id': 1, 'updated_by_user_id': 1,
                 'created_at': DATE, 'updated_at': DATE},
    'conversation': {'id': 20, 'business_id': 1, 'customer_id': 10, 'channel': 'whatsapp',
                     'status': 'open', 'assigned_to_user_id': 1, 'assigned_to_membership_id': 1,
                     'last_message_at': DATE, 'unread_count': 1, 'tags': ['sales'],
                     'priority': 'normal', 'created_by_id': None, 'updated_by_id': None,
                     'created_at': DATE, 'updated_at': DATE, 'closed_at': None},
    'message': {'id': 30, 'business_id': 1, 'conversation_id': 20, 'customer_id': 10,
                'direction': 'outgoing', 'channel': 'whatsapp', 'message_type': 'text',
                'body': 'Hello from the team', 'media_url': None, 'has_private_media': False,
                'media_mime_type': None, 'media_filename': None, 'media_size_bytes': None,
                'media_status': None, 'media_download_path': None, 'provider_message_id': 'wamid.EXAMPLE',
                'status': 'sent', 'sent_by_user_id': 1, 'created_at': DATE},
    'lead': {'id': 40, 'business_id': 1, 'conversation_id': 20, 'customer_id': 10,
             'stage': 'interested', 'value': 3500.0, 'source': 'whatsapp',
             'notes': 'Asked for pricing', 'assigned_to_user_id': 1,
             'next_follow_up_at': None, 'created_at': DATE, 'updated_at': DATE},
    'booking': {'id': 50, 'business_id': 1, 'customer_id': 10, 'conversation_id': 20,
                'service_name': 'Haircut', 'scheduled_at': '2026-11-05T14:00:00Z',
                'duration_minutes': 60, 'status': 'pending', 'notes': 'First visit',
                'created_at': DATE, 'updated_at': DATE},
    'payment': {'id': 60, 'business_id': 1, 'customer_id': 10, 'conversation_id': 20,
                'amount': '1500.00', 'currency': 'KES', 'reference': 'INV-1001',
                'method': 'mpesa', 'status': 'pending', 'notes': 'Deposit',
                'confirmed_by_user_id': None, 'confirmed_at': None, 'created_at': DATE},
    'faq': {'id': 70, 'business_id': 1, 'question': 'When are you open?',
            'answer': 'We open at 9am.', 'keywords': ['hours', 'open'],
            'is_active': True, 'created_at': DATE, 'updated_at': DATE},
    'rule': {'id': 80, 'business_id': 1, 'name': 'Opening hours',
             'trigger_type': 'keyword', 'trigger_config': {'keywords': ['open']},
             'response_text': 'We open at 9am.', 'is_active': True,
             'created_at': DATE, 'updated_at': DATE},
    'automation': {'id': 90, 'business_id': 1, 'name': 'Welcome message',
                   'trigger_type': 'new_message_received', 'trigger_config': {},
                   'action_type': 'send_whatsapp_message', 'action_config': {'message': 'Welcome!'},
                   'is_active': True, 'created_at': DATE, 'updated_at': DATE},
    'run': {'id': 100, 'business_id': 1, 'automation_id': 90,
            'trigger_type': 'keyword', 'event_payload': {}, 'status': 'completed',
            'result': {}, 'error_message': None, 'started_at': DATE, 'completed_at': DATE},
    'notification': {'id': 110, 'business_id': 1, 'user_id': 1, 'title': 'New message', 'message': 'Jane sent a message',
                     'type': 'new_message', 'is_read': False, 'link_url': '/conversations/20',
                     'created_at': DATE},
    'audit_log': {'id': 120, 'business_id': 1, 'user_id': 1,
                  'action': 'message_sent', 'resource_type': 'message', 'resource_id': 30,
                  'metadata_json': {'channel': 'whatsapp'}, 'created_at': DATE},
}

# Exact example JSON payloads for endpoints that accept request bodies. No request
# body is documented for action endpoints whose implementation does not read one.
BODY = {
    ('post', '/api/auth/register'): {'name': 'Alex Demo', 'email': 'alex@example.com', 'password': 'StrongPassword123!'},
    ('post', '/api/auth/login'): {'email': 'alex@example.com', 'password': 'StrongPassword123!'},
    ('post', '/api/auth/forgot-password'): {'email': 'alex@example.com'},
    ('post', '/api/auth/reset-password'): {'token': '<reset-token>', 'password': 'NewStrongPassword123!'},
    ('post', '/api/businesses'): {'name': 'Acme Salon', 'phone_number': '+254700000001', 'industry': 'beauty'},
    ('post', '/api/businesses/switch'): {'business_id': 1},
    ('patch', '/api/businesses/current'): {'name': 'Acme Salon & Spa'},
    ('patch', '/api/businesses/current/settings'): {'settings': {'timezone': 'Africa/Nairobi'}},
    ('post', '/api/businesses/current/members/invite'): {'email': 'colleague@example.com', 'role': 'staff'},
    ('patch', '/api/businesses/current/members/{membership_id}'): {'role': 'admin'},
    ('post', '/api/customers'): {'name': 'Jane Doe', 'phone_number': '+254711222333', 'email': 'jane@example.com', 'tags': ['vip']},
    ('patch', '/api/customers/{customer_id}'): {'name': 'Jane A. Doe', 'status': 'active'},
    ('patch', '/api/conversations/{conversation_id}'): {'priority': 'high', 'tags': ['sales']},
    ('post', '/api/conversations/{conversation_id}/assign'): {'assigned_to_user_id': 1},
    ('post', '/api/messages/{conversation_id}'): {'message_type': 'text', 'body': 'Hello from the team'},
    ('post', '/api/conversations/{conversation_id}/messages'): {'message_type': 'text', 'body': 'Hello from the team'},
    ('post', '/api/leads'): {'conversation_id': 20, 'stage': 'interested', 'value': 3500.0, 'source': 'whatsapp'},
    ('patch', '/api/leads/{lead_id}'): {'value': 4000.0, 'notes': 'New estimate'},
    ('post', '/api/leads/{lead_id}/move-stage'): {'stage': 'booked'},
    ('post', '/api/bookings'): {'customer_id': 10, 'service_name': 'Haircut', 'scheduled_at': '2026-11-05T14:00:00Z', 'duration_minutes': 60},
    ('patch', '/api/bookings/{booking_id}'): {'status': 'confirmed', 'notes': 'Confirmed by phone'},
    ('post', '/api/payments'): {'customer_id': 10, 'amount': '1500.00', 'currency': 'KES', 'method': 'mpesa', 'reference': 'INV-1001'},
    ('patch', '/api/payments/{payment_id}'): {'status': 'paid'},
    ('post', '/api/automations/faqs'): {'question': 'When are you open?', 'answer': 'We open at 9am.', 'keywords': ['hours']},
    ('patch', '/api/automations/faqs/{faq_id}'): {'answer': 'We open at 8am.'},
    ('post', '/api/automations/rules'): {'name': 'Opening hours', 'trigger_type': 'keyword', 'trigger_config': {'keywords': ['hours']}, 'response_text': 'We open at 9am.'},
    ('patch', '/api/automations/rules/{rule_id}'): {'response_text': 'We open at 8am.'},
    ('post', '/api/automations'): {'name': 'Welcome message', 'trigger_type': 'new_message_received', 'trigger_config': {}, 'action_type': 'send_whatsapp_message', 'action_config': {'message': 'Welcome!'}},
    ('patch', '/api/automations/{automation_id}'): {'is_active': False},
    ('post', '/api/whatsapp/webhook'): {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'field': 'messages', 'value': {'metadata': {'phone_number_id': '123456'}, 'messages': [{'from': '254711222333', 'id': 'wamid.EXAMPLE', 'type': 'text', 'text': {'body': 'Hello'}}]}}]}]},
}

# Known query filters from the actual route implementations.
QUERY = {
    '/api/customers': {'page': 'integer', 'per_page': 'integer', 'status': 'string', 'source': 'string', 'tag': 'string', 'q': 'string'},
    '/api/customers/search': {'page': 'integer', 'per_page': 'integer', 'status': 'string', 'source': 'string', 'tag': 'string', 'q': 'string'},
    '/api/conversations': {'status': 'string', 'channel': 'string', 'priority': 'string', 'search': 'string', 'unread': 'boolean', 'customer_id': 'integer', 'assigned_to_user_id': 'integer', 'assigned_to_membership_id': 'integer', 'tag': 'string', 'from_date': 'string', 'to_date': 'string', 'date_from': 'string', 'date_to': 'string'},
    '/api/messages/updates': {'since': 'string'},
    '/api/conversations/{conversation_id}/messages/updates': {'since': 'string'},
    '/api/leads': {'stage': 'string', 'assignee_id': 'integer'},
    '/api/bookings': {'status': 'string', 'customer_id': 'integer', 'conversation_id': 'integer'},
    '/api/payments': {'status': 'string', 'customer_id': 'integer', 'conversation_id': 'integer'},
    '/api/automations': {'active': 'boolean'},
    '/api/automations/faqs': {'active': 'boolean'},
    '/api/automations/rules': {'active': 'boolean'},
    '/api/automations/runs': {'status': 'string', 'automation_id': 'integer'},
    '/api/audit-logs': {'limit': 'integer', 'offset': 'integer', 'action': 'string'},
    '/api/notifications': {'is_read': 'boolean'},
}
# Contract-level required JSON fields and known enumerations, derived from validators.
REQUIRED_FIELDS = {
    '/api/auth/register': ['name', 'email', 'password'],
    '/api/auth/login': ['email', 'password'],
    '/api/auth/reset-password': ['token', 'password'],
    '/api/businesses': ['name', 'phone_number', 'industry'],
    '/api/businesses/switch': ['business_id'],
    '/api/businesses/current/members/invite': ['email', 'role'],
    '/api/businesses/current/settings': ['settings'],
    '/api/customers': ['phone_number'],
    '/api/leads': ['conversation_id'],
    '/api/leads/{lead_id}/move-stage': ['stage'],
    '/api/bookings': ['customer_id', 'service_name', 'scheduled_at', 'duration_minutes'],
    '/api/payments': ['customer_id', 'amount', 'currency', 'method'],
    '/api/automations/faqs': ['question', 'answer'],
    '/api/automations/rules': ['name', 'trigger_type', 'response_text'],
    '/api/automations': ['name', 'trigger_type', 'action_type'],
    '/api/whatsapp/webhook': ['object', 'entry'],
}
ENUMS = {
    'status': {
        '/api/customers': ['active', 'inactive', 'blocked'],
        '/api/conversations': ['open', 'pending', 'closed', 'archived'],
        '/api/leads': ['new', 'interested', 'negotiating', 'booked', 'paid', 'lost'],
        '/api/bookings': ['pending', 'confirmed', 'completed', 'cancelled', 'no_show'],
        '/api/payments': ['pending', 'paid', 'failed', 'cancelled'],
    },
    'method': {'/api/payments': ['cash', 'mpesa', 'bank_transfer', 'card', 'other']},
    'stage': {'/api/leads': ['new', 'interested', 'negotiating', 'booked', 'paid', 'lost']},
    'source': {'/api/customers': ['manual', 'whatsapp', 'import', 'other']},
    'priority': {'/api/conversations': ['low', 'normal', 'high', 'urgent']},
    'plan': {'/api/businesses': ['free', 'starter', 'pro', 'enterprise']},
    'role': {'/api/businesses/current/members/invite': ['admin', 'staff', 'support']},
    'trigger_type': {'/api/automations': ['new_message_received', 'customer_created', 'lead_created', 'booking_created', 'payment_marked_paid']},
    'action_type': {'/api/automations': ['send_whatsapp_message', 'create_lead', 'update_lead_stage', 'create_follow_up_reminder', 'notify_staff']},
}


def add_fields(schema, path):
    for field, details in ENUMS.items():
        for root, choices in details.items():
            if path == root or path.startswith(root + '/'):  # list and resource updates
                if field in schema.get('properties', {}):
                    schema['properties'][field]['enum'] = choices
                break
    return schema


for _dashboard_route in ('summary', 'conversations', 'leads', 'bookings', 'payments'):
    QUERY[f'/api/dashboard/{_dashboard_route}'] = {'start_date': 'string', 'end_date': 'string'}


def inspect_routes():
    """Get registered app operations without importing Flask or the live DB."""
    found = {}
    for source in (BACKEND / 'app').glob('*/routes.py'):
        tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = node.decorator_list
            auth = any((isinstance(d, ast.Name) and d.id in {'login_required', 'require_auth'}) for d in decorators)
            business = any((isinstance(d, ast.Name) and d.id == 'business_required') for d in decorators)
            perm = None
            for d in decorators:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == 'permission_required' and d.args:
                    perm = ast.unparse(d.args[0]).split('.')[-1].lower()
            for d in decorators:
                if not isinstance(d, ast.Call) or not isinstance(d.func, ast.Attribute):
                    continue
                if not isinstance(d.func.value, ast.Name) or not d.func.value.id.endswith('_bp'):
                    continue
                bp = d.func.value.id.removesuffix('_bp')
                if bp not in PREFIXES or d.func.attr not in {'get', 'post', 'patch', 'put', 'delete', 'route'} or not d.args:
                    continue
                suffix = ast.literal_eval(d.args[0])
                methods = [d.func.attr.upper()] if d.func.attr != 'route' else ['GET']
                if d.func.attr == 'route':
                    methods = next((ast.literal_eval(k.value) for k in d.keywords if k.arg == 'methods'), ['GET'])
                path = PREFIXES[bp] + suffix
                path = re.sub(r'<(?:int:|float:|string:|uuid:|path:)?([a-zA-Z_]+)>', r'{\1}', path)
                for method in methods:
                    key = (method.lower(), path)
                    if key in found:
                        raise ValueError(f'Duplicate route {key}')
                    found[key] = {'func': node.name, 'auth': auth, 'business': business, 'permission': perm}
    return found


def shape(value):
    """Produce a minimal navigable schema from a representative response value."""
    if value is None:
        return {}
    if isinstance(value, bool):
        return {'type': 'boolean'}
    if isinstance(value, int):
        return {'type': 'integer'}
    if isinstance(value, float):
        return {'type': 'number'}
    if isinstance(value, str):
        return {'type': 'string'}
    if isinstance(value, list):
        return {'type': 'array', 'items': shape(value[0]) if value else {}}
    if isinstance(value, dict):
        return {'type': 'object', 'properties': {name: shape(item) for name, item in value.items()}}
    raise TypeError(f'Unsupported example type {type(value)}')


def sample_for(method, path, func):
    """Return the *legacy* payload before app.common.responses adds the envelope."""
    if path == '/api/auth/register' or path == '/api/auth/login':
        return {'user': SAMPLES['user'], 'access_token': '<jwt-access-token>', 'businesses': [{**SAMPLES['business'], 'role': 'owner', 'membership_status': 'active', 'user_id': 1, 'business_id': 1, 'is_current': True}]}
    if path == '/api/auth/me':
        return {'user': SAMPLES['user'], 'businesses': [{**SAMPLES['business'], 'role': 'owner', 'membership_status': 'active', 'user_id': 1, 'business_id': 1, 'is_current': True}]}
    if path == '/api/auth/logout':
        return {'message': 'Logged out successfully'}
    if path == '/api/auth/forgot-password':
        return {'message': 'If an account with that email exists, password reset instructions have been sent.'}
    if path == '/api/auth/reset-password':
        return {'message': 'Password reset successfully'}
    if path == '/api/businesses' and method == 'get':
        return {'businesses': [{**SAMPLES['business'], 'role': 'owner', 'membership_status': 'active', 'user_id': 1, 'business_id': 1, 'is_current': True}]}
    if path in ('/api/businesses', '/api/businesses/switch') and method == 'post':
        return {'business': SAMPLES['business'], 'membership': SAMPLES['membership'], 'access_token': '<jwt-access-token>'}
    if path.endswith('/settings'):
        return {'settings': {'timezone': 'Africa/Nairobi'}}
    if path.endswith('/members') and method == 'get':
        return {'members': [SAMPLES['membership']]}
    if '/members/' in path and method in {'post', 'patch'}:
        return {'membership': SAMPLES['membership']}
    if path.endswith('/members/{membership_id}') and method == 'delete':
        return {'message': 'Member removed'}
    if path.startswith('/api/businesses'):
        return {'business': SAMPLES['business']}
    if path.startswith('/api/customers/') and path.split('/')[-1] in {'conversations', 'leads', 'bookings', 'payments'}:
        resource = path.split('/')[-1]
        return {resource: [SAMPLES[resource[:-1]]]}
    if path.startswith('/api/customers'):
        if path in {'/api/customers', '/api/customers/search'} and method == 'get':
            return {'customers': [SAMPLES['customer']], 'pagination': {'page': 1, 'per_page': 50, 'total': 1, 'pages': 1}}
        return {'customer': SAMPLES['customer']}
    if path.startswith('/api/dashboard/'):
        return {'business_id': 1, 'date_range': {'start': '2026-10-01T00:00:00Z', 'end': '2026-11-01T00:00:00Z'}, 'metrics': {}}
    if path in {'/api/messages/updates', '/api/conversations/updates'}:
        return {'conversations': [SAMPLES['conversation']], 'since': DATE}
    if path.endswith('/messages/updates'):
        return {'messages': [SAMPLES['message']], 'since': DATE}
    if (path.startswith('/api/messages/') or path.endswith('/messages')) and '{conversation_id}' in path:
        return {'messages': [SAMPLES['message']]} if method == 'get' else {'message': SAMPLES['message']}
    if path.endswith('/ai/suggest-reply'):
        return {'conversation_id': 20, 'suggestion': 'Thank you for contacting us!', 'auto_sent': False, 'editable': True}
    if path.startswith('/api/conversations'):
        if path == '/api/conversations' and method == 'get':
            return {'conversations': [SAMPLES['conversation']], 'count': 1}
        conversation = dict(SAMPLES['conversation'])
        if path.endswith('/close'):
            conversation['status'] = 'closed'
            conversation['closed_at'] = DATE
        if path.endswith('/archive'):
            conversation['status'] = 'archived'
        if path.endswith('/reopen'):
            conversation['status'] = 'open'
            conversation['closed_at'] = None
        if path.endswith('/unassign'):
            conversation['assigned_to_user_id'] = None
            conversation['assigned_to_membership_id'] = None
        if path.endswith('/mark-read'):
            conversation['unread_count'] = 0
        return {'conversation': conversation}
    for prefix, singular in [('/api/leads', 'lead'), ('/api/bookings', 'booking'), ('/api/payments', 'payment')]:
        if path.startswith(prefix):
            if path == prefix and method == 'get':
                return {singular+'s': [SAMPLES[singular]]}
            if path.endswith('/send-reminder'):
                return {'payment': SAMPLES['payment'], 'message': SAMPLES['message']}
            record = dict(SAMPLES[singular])
            if path.endswith('/mark-paid') or (singular == 'payment' and method == 'patch'):
                record['status'] = 'paid'
                record['confirmed_at'] = DATE
                record['confirmed_by_user_id'] = 1
            if path.endswith('/move-stage'):
                record['stage'] = 'booked'
            if singular == 'booking' and method == 'patch':
                record['status'] = 'confirmed'
            return {singular: record}
    if path.startswith('/api/automations/') and '/faqs' in path:
        return {'faqs': [SAMPLES['faq']]} if path.endswith('/faqs') and method == 'get' else {'faq': SAMPLES['faq']}
    if path.startswith('/api/automations/') and '/rules' in path:
        return {'rules': [SAMPLES['rule']]} if path.endswith('/rules') and method == 'get' else {'rule': SAMPLES['rule']}
    if path == '/api/automations/runs':
        return {'runs': [SAMPLES['run']]}
    if path.startswith('/api/automations'):
        return {'automations': [SAMPLES['automation']]} if path == '/api/automations' and method == 'get' else {'automation': SAMPLES['automation']}
    if path.startswith('/api/notifications'):
        return {'notifications': [SAMPLES['notification']], 'unread_count': 1} if method == 'get' else {'notification': SAMPLES['notification']}
    if path == '/api/audit-logs':
        return {'audit_logs': [SAMPLES['audit_log']], 'total': 1, 'limit': 50, 'offset': 0}
    if path.startswith('/api/users'):
        return {'users': [SAMPLES['user']]} if path == '/api/users' else {'user': SAMPLES['user']}
    if path == '/api/whatsapp/webhook':
        return {'received': True}
    raise ValueError(f'Missing response example: {method.upper()} {path} ({func})')


def response_example(payload):
    return {
        **payload,
        'success': True,
        'message': payload.get('message') or 'Success',
        'data': copy.deepcopy(payload),
        'error': None, 'code': None, 'details': None,
    }


def response_for(method, path, func):
    if method == 'delete' and path not in {'/api/businesses/current/members/{membership_id}'}:
        return {'204': {'description': 'Deleted. No response body.'}}
    if path == '/api/media/{message_id}':
        return {'200': {'description': 'Private media bytes, not JSON.', 'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}}}}
    if path == '/api/whatsapp/webhook' and method == 'get':
        return {'200': {'description': 'Verification challenge echoed verbatim as a string (Flask default text/html response).', 'content': {'text/html': {'schema': {'type': 'string'}, 'example': '123456'}}}}
    status = '201' if method == 'post' and (func.startswith('create_') or path in {'/api/auth/register', '/api/businesses/current/members/invite', '/api/payments/{payment_id}/send-reminder', '/api/messages/{conversation_id}', '/api/conversations/{conversation_id}/messages'}) else '200'
    data = response_example(sample_for(method, path, func))
    return {status: {'description': 'Successful request (legacy fields are preserved alongside the standard envelope).',
                     'content': {'application/json': {'schema': shape(data), 'example': data}}}}


def query_params(path):
    params = []
    for field, typ in QUERY.get(path, {}).items():
        field_schema = {'type': typ}
        if field == 'per_page':
            field_schema.update(default=50, maximum=100)
        if field == 'page':
            field_schema.update(default=1, minimum=1)
        if field in {'start_date', 'end_date'}:
            field_schema.update(format='date')
        if field == 'since':
            field_schema.update(format='date-time')
        if field in ENUMS and path in ENUMS[field]:
            field_schema['enum'] = ENUMS[field][path]
        params.append({'name': field, 'in': 'query', 'required': False, 'schema': field_schema})
    return params


def build():
    paths = {}
    for (method, path), meta in sorted(inspect_routes().items(), key=lambda i: (i[0][1], i[0][0])):
        func = meta['func']
        tag = path.split('/')[2].replace('-', ' ').title()
        if path.endswith('/ai/suggest-reply'):
            tag = 'AI'
        if '/messages' in path and path.startswith('/api/conversations/'):
            tag = 'Messages'
        summary = func.replace('_', ' ').capitalize()
        params = []
        for param in re.findall(r'{(.*?)}', path):
            params.append({'name': param, 'in': 'path', 'required': True, 'schema': {'type': 'integer'}, 'description': f'{param} identifier.'})
        params += query_params(path) if method == 'get' else []
        if meta['business']:
            params.append({'name': 'X-Business-Id', 'in': 'header', 'required': False,
                           'schema': {'type': 'integer'},
                           'description': 'Optional explicit active business workspace. Requires active membership; otherwise resolved from session/JWT/current workspace.'})
        if path == '/api/whatsapp/webhook' and method == 'get':
            for item in ('hub.mode', 'hub.verify_token', 'hub.challenge'):
                params.append({'name': item, 'in': 'query', 'required': True, 'schema': {'type': 'string'},
                               'example': {'hub.mode': 'subscribe', 'hub.verify_token': '<configured-verification-token>', 'hub.challenge': '123456'}[item]})
        if path == '/api/whatsapp/webhook' and method == 'post':
            params.append({'name': 'X-Hub-Signature-256', 'in': 'header', 'required': True, 'schema': {'type': 'string'},
                           'description': 'sha256=<hex HMAC-SHA256 of the exact raw body using META_APP_SECRET>.'})
        details = []
        if meta['business']:
            details.append('Active business membership required.')
        if meta['permission']:
            details.append('Permission: `' + meta['permission'] + '`.')
        if path == '/api/businesses/current' and method == 'patch' or path == '/api/businesses/current/settings' and method == 'patch':
            details.append('Also requires `manage_business_settings`; owner-only fields/settings are restricted.')
        if path == '/api/whatsapp/webhook':
            details.append('Meta webhook: GET checks WHATSAPP_VERIFY_TOKEN; POST verifies the raw-body signature using META_APP_SECRET. No JWT.')
        if path.startswith('/api/messages/') and method == 'post' or path.endswith('/messages') and method == 'post':
            details.append('Only WhatsApp supported. Text needs `body`; media messages need `media_url` and an appropriate `message_type`. `to` is optional if conversation has a contact phone number.')
        if path == '/api/payments' and method == 'post':
            details.append('`amount` is a decimal value. Serialized payment amounts are strings, not numbers.')
        if path == '/api/auth/forgot-password':
            details.append('Always returns generic text to avoid disclosing whether an account exists.')
        if path == '/api/conversations/{conversation_id}/ai/suggest-reply':
            details.append('Suggestion only; no message is sent automatically.')
        if path == '/api/media/{message_id}':
            details.append('Binary response. Private tenant-scoped media; do not expect a JSON envelope on success.')
        operation = {'tags': [tag], 'operationId': func + '__' + method + '__' + path.replace('/', '_').replace('{','').replace('}','').replace('-','_'),
                     'summary': summary, 'description': ' '.join(details) or 'Existing Flask endpoint.',
                     'responses': response_for(method, path, func)}
        if meta['auth']:
            operation['security'] = [{'bearerAuth': []}]
            operation['responses'].update({
                '401': {'$ref': '#/components/responses/Unauthorized'},
                '403': {'$ref': '#/components/responses/Forbidden'},
            })
        else:
            operation['security'] = []
            if path == '/api/whatsapp/webhook':
                operation['responses']['403'] = {'$ref': '#/components/responses/Forbidden'}
        if method in {'post', 'patch', 'put'} and (method, path) in BODY:
            req = BODY[(method, path)]
            req_schema = add_fields(shape(req), path)
            if method == 'post' and path in REQUIRED_FIELDS:
                req_schema['required'] = REQUIRED_FIELDS[path]
            operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': req_schema, 'example': req}}}
        if params:
            operation['parameters'] = params
        if method in {'post', 'patch'}:
            operation['responses']['400'] = {'$ref': '#/components/responses/BadRequest'}
        if '{' in path and path != '/api/whatsapp/webhook':
            operation['responses']['404'] = {'$ref': '#/components/responses/NotFound'}
        paths.setdefault(path, {})[method] = operation

    error_example = {'success': False, 'message': 'Invalid request', 'data': None,
                     'error': 'Invalid request', 'code': 'VALIDATION_ERROR', 'details': {'field': 'Required'}}
    error_schema = shape(error_example)
    components = {
        'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT',
                                          'description': 'Access token from POST /api/auth/login or /register; use Authorization: Bearer <access_token>.'}},
        'schemas': {name.title().replace('_', ''): shape(value) for name, value in SAMPLES.items()} | {'ErrorResponse': error_schema},
        'responses': {
            'BadRequest': {'description': 'Invalid request or validation error.', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorResponse'}, 'example': error_example}}},
            'Unauthorized': {'description': 'Missing, expired, revoked, or invalid bearer JWT.', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorResponse'}, 'example': dict(error_example, message='Authentication required', error='AUTH_REQUIRED', code='AUTH_REQUIRED', details=None)}}},
            'Forbidden': {'description': 'Missing workspace membership, permission, or webhook signature.', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorResponse'}, 'example': dict(error_example, message='Permission denied', error='PERMISSION_DENIED', code='PERMISSION_DENIED', details=None)}}},
            'NotFound': {'description': 'Entity not found (including a resource belonging to another business).', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorResponse'}, 'example': dict(error_example, message='Resource not found', error='Resource not found', code='NOT_FOUND', details=None)}}},
        },
    }
    return {
        'openapi': '3.1.0',
        'info': {'title': 'Business Creator Assist API', 'version': '1.0.0',
                 'description': ('Documented directly from the existing Flask route decorators. '
                                 'All examples use illustrative data, not live credentials. '
                                 'The API standardizes JSON responses as `success`, `message`, `data`, '
                                 '`error`, `code`, `details`, while retaining legacy top-level fields. '
                                 'For legacy responses, `data` contains the pre-normalization response object. '
                                 '204, binary media, and webhook verification do not use the JSON envelope. '
                                 'Business-scoped endpoints require an active membership and often the listed RBAC permission. '
                                 'Login/register and business switch can return replacement JWTs; use the latest token.')},
        'servers': [{'url': '/', 'description': 'Current API origin (same-origin Swagger UI)'}],
        'tags': [{'name': name} for name in ['Auth', 'Businesses', 'Customers', 'Conversations', 'Messages', 'Leads', 'Bookings', 'Payments', 'Whatsapp', 'Automations', 'Dashboard', 'Notifications', 'Users', 'AI', 'Media', 'Audit Logs']],
        'paths': paths,
        'components': components,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail when committed document differs from current routes/examples')
    args = parser.parse_args()
    result = json.dumps(build(), indent=2, ensure_ascii=False) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != result:
            parser.error('OpenAPI spec out of date. Run python backend/scripts/generate_openapi.py and commit the result.')
        print('OpenAPI spec matches route decorators and curated examples.')
    else:
        OUTPUT.write_text(result, encoding='utf-8')
        print(f'Wrote {OUTPUT.relative_to(BACKEND)} ({sum(len(v) for v in build()["paths"].values())} operations).')


if __name__ == '__main__':
    main()