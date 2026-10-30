import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from app.services.database import Database, DatabaseError
from scripts.check_deploy import validate


class DeploymentTests(unittest.TestCase):
    def test_render_refuses_ephemeral_sqlite(self):
        with patch.dict(os.environ, {'RENDER': 'true'}):
            with self.assertRaisesRegex(RuntimeError, 'DATABASE_URL'):
                create_app({'DATABASE_URL': None})

    def test_tests_never_use_the_developers_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'DATABASE_URL': 'https://not-a-database.invalid'}):
                app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only',
                                  'MARKET_DATABASE': str(Path(directory)/'market.sqlite3')})
        self.assertIsNone(app.config['DATABASE_URL'])
        self.assertFalse(app.extensions['market'].store.postgres)

    def test_database_error_does_not_disclose_connection_string(self):
        database = Database('postgresql://test:do-not-disclose-password@[invalid-host')
        with self.assertRaises(DatabaseError) as caught:
            database.initialize()
        self.assertNotIn('do-not-disclose-password', str(caught.exception))

    def test_health_endpoint_reports_database_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only',
                              'MARKET_DATABASE': str(Path(directory)/'market.sqlite3')})
            client = app.test_client()
            self.assertEqual(client.get('/healthz').json, {'status': 'ok'})
            with patch.object(app.extensions['market'], 'connection', side_effect=DatabaseError('test')):
                self.assertEqual(client.get('/healthz').status_code, 503)

    def test_pwa_manifest_and_service_worker_are_served_from_root(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only',
                              'MARKET_DATABASE': str(Path(directory)/'market.sqlite3')})
            client = app.test_client()
            manifest_response = client.get('/manifest.webmanifest')
            manifest = json.loads(manifest_response.data)
            self.assertEqual(manifest_response.mimetype, 'application/manifest+json')
            self.assertEqual(manifest['start_url'], '/')
            self.assertTrue(any(icon['sizes'] == '512x512' for icon in manifest['icons']))

            worker = client.get('/service-worker.js')
            self.assertEqual(worker.status_code, 200)
            self.assertEqual(worker.headers['Service-Worker-Allowed'], '/')
            self.assertIn('no-store', worker.headers['Cache-Control'])
            self.assertIn(b"caches.match('/offline')", worker.data)

            login = client.get('/auth/login')
            self.assertIn(b'rel="manifest"', login.data)
            self.assertIn(b'/static/js/pwa.js', login.data)
            manifest_response.close()
            worker.close()
            login.close()

    def test_readiness_checker_rejects_password_placeholder(self):
        values = {'SECRET_KEY': 'x'*64, 'DATABASE_URL': 'postgresql://postgres:[YOUR-PASSWORD]@example.invalid/postgres',
                  'SUPABASE_URL': 'https://example.supabase.co', 'SUPABASE_KEY': 'sb_secret_test_only',
                  'EMAIL_PROVIDER': 'brevo', 'BREVO_API_KEY': 'test-only', 'MAIL_FROM': 'sender@example.com',
                  'SESSION_COOKIE_SECURE': '1'}
        self.assertTrue(any('DATABASE_URL' in error for error in validate(values)))
        values['DATABASE_URL'] = 'postgresql://postgres:test-only@example.invalid/postgres'
        self.assertEqual(validate(values), [])
