"""OpenAPI contract checks that run without PostgreSQL, Redis or Flask imports."""

import importlib.util
import json
from pathlib import Path
import unittest

BACKEND = Path(__file__).resolve().parents[3]
GENERATOR_PATH = BACKEND / 'scripts' / 'generate_openapi.py'
SPEC_PATH = BACKEND / 'app' / 'api_docs' / 'openapi.json'

spec = importlib.util.spec_from_file_location('generate_openapi', GENERATOR_PATH)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class OpenAPIDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(SPEC_PATH.read_text(encoding='utf-8'))

    def operation(self, path, method='get'):
        return self.document['paths'][path][method]

    def test_generated_document_matches_actual_route_decorators(self):
        self.assertEqual(self.document, generator.build(),
                         'Run python backend/scripts/generate_openapi.py and commit the result')
        routes = set(generator.inspect_routes())
        documented = {(method, path) for path, operations in self.document['paths'].items()
                      for method in operations}
        self.assertEqual(routes, documented)

    def test_all_required_domains_have_documented_routes(self):
        for domain in ('auth', 'businesses', 'customers', 'conversations', 'messages',
                       'leads', 'bookings', 'payments', 'whatsapp'):
            self.assertTrue(any(p.startswith('/api/' + domain) for p in self.document['paths']), domain)

    def test_every_operation_has_examples_and_describes_security(self):
        for path, methods in self.document['paths'].items():
            for method, operation in methods.items():
                with self.subTest(method=method, path=path):
                    self.assertIn('summary', operation)
                    self.assertIn('security', operation)
                    self.assertIn('responses', operation)
                    success = next((data for code, data in operation['responses'].items() if code.startswith('2')), None)
                    self.assertIsNotNone(success)
                    if 'content' in success:
                        for content in success['content'].values():
                            self.assertIn('example', content) if path != '/api/media/{message_id}' else None
                    if 'requestBody' in operation:
                        self.assertIn('example', operation['requestBody']['content']['application/json'])

    def test_login_logout_and_me_security(self):
        self.assertEqual(self.operation('/api/auth/login', 'post')['security'], [])
        self.assertEqual(self.operation('/api/auth/register', 'post')['security'], [])
        self.assertEqual(self.operation('/api/auth/me')['security'], [{'bearerAuth': []}])
        self.assertEqual(self.operation('/api/auth/logout', 'post')['security'], [{'bearerAuth': []}])
        self.assertEqual(self.operation('/api/customers', 'post')['security'], [{'bearerAuth': []}])

    def test_business_header_and_permissions(self):
        op = self.operation('/api/bookings', 'post')
        self.assertIn('manage_bookings', op['description'])
        self.assertTrue(any(p['name'] == 'X-Business-Id' and p['in'] == 'header'
                            for p in op['parameters']))
        self.assertIn('manage_business_settings', self.operation('/api/businesses/current', 'patch')['description'])

    def test_webhook_signature_without_bearer_and_challenge(self):
        post = self.operation('/api/whatsapp/webhook', 'post')
        self.assertEqual(post['security'], [])
        self.assertTrue(any(p['name'] == 'X-Hub-Signature-256' for p in post['parameters']))
        get = self.operation('/api/whatsapp/webhook')
        self.assertEqual(get['responses']['200']['content']['text/html']['example'], '123456')
        self.assertTrue(any(p['name'] == 'hub.verify_token' for p in get['parameters']))

    def test_payment_amount_is_a_string_and_bookings_have_required_fields(self):
        p = self.operation('/api/payments', 'post')
        self.assertEqual(p['requestBody']['content']['application/json']['schema']['required'],
                         ['customer_id', 'amount', 'currency', 'method'])
        payload = p['responses']['201']['content']['application/json']['example']['payment']
        self.assertIsInstance(payload['amount'], str)
        booking = self.operation('/api/bookings', 'post')
        self.assertIn('scheduled_at', booking['requestBody']['content']['application/json']['schema']['required'])

    def test_no_content_and_media_binary_stay_unwrapped(self):
        self.assertEqual(list(self.operation('/api/bookings/{booking_id}', 'delete')['responses'].keys())[0], '204')
        media = self.operation('/api/media/{message_id}')['responses']['200']
        self.assertIn('application/octet-stream', media['content'])

    @unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask not installed in standalone docs-check environment')
    def test_documentation_http_routes_return_raw_openapi_and_html(self):
        # A minimal Flask app reproduces the shared after_request normalizer without DB/Redis.
        from flask import Flask
        blueprint_spec = importlib.util.spec_from_file_location('docs_http_blueprint', BACKEND / 'app' / 'api_docs' / '__init__.py')
        blueprint_module = importlib.util.module_from_spec(blueprint_spec)
        blueprint_spec.loader.exec_module(blueprint_module)
        responses_spec = importlib.util.spec_from_file_location('docs_http_responses', BACKEND / 'app' / 'common' / 'responses.py')
        responses_module = importlib.util.module_from_spec(responses_spec)
        responses_spec.loader.exec_module(responses_module)
        mini = Flask(__name__)
        mini.register_blueprint(blueprint_module.api_docs_bp)
        responses_module.standardize_api_responses(mini)
        with mini.test_client() as client:
            spec_response = client.get('/api/openapi.json')
            self.assertEqual(spec_response.status_code, 200)
            self.assertEqual(spec_response.get_json(), self.document)
            self.assertIn('application/json', spec_response.content_type)
            html_response = client.get('/api/docs')
            self.assertEqual(html_response.status_code, 200)
            self.assertIn(b'SwaggerUIBundle', html_response.data)
            self.assertIn('text/html', html_response.content_type)

    def test_documentation_is_registered_and_html_uses_the_spec(self):
        app_factory = (BACKEND / 'app' / '__init__.py').read_text()
        self.assertIn('app.register_blueprint(api_docs_bp)', app_factory)
        responses = (BACKEND / 'app' / 'common' / 'responses.py').read_text()
        self.assertIn('request.path == "/api/openapi.json"', responses)
        html = (BACKEND / 'app' / 'api_docs' / 'swagger.html').read_text()
        self.assertIn("url: '/api/openapi.json'", html)
        self.assertIn('SwaggerUIBundle', html)


if __name__ == '__main__':
    unittest.main()