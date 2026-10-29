import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app

PASSWORD = 'test-initial-password-123'
NEW_PASSWORD = 'test-changed-password-456'


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'admin-test-only',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.client = self.app.test_client()
        self.admin = self.app.extensions['admin']
        self.market = self.app.extensions['market']
        self.owner = self.admin.create_account('owner', PASSWORD, 'owner')

    def token(self, path='/admin/login'):
        response = self.client.get(path)
        return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)).group(1)

    def login(self, username='owner', password=NEW_PASSWORD):
        token = self.token()
        return self.client.post('/admin/login', data={'csrf_token': token, 'username': username, 'password': password})

    def ready(self):
        self.admin.change_password(self.owner, PASSWORD, NEW_PASSWORD)
        self.login()

    def post(self, path, **data):
        with self.client.session_transaction() as sess:
            data['csrf_token'] = sess['admin_csrf']
        return self.client.post(path, data=data)

    def news_form(self, article_id='news-test'):
        return {'article_id': article_id, 'title': '정보 분야 연구 성과', 'body': '새로운 공동 연구가 발표되었습니다.',
                'target': 'sector:6', 'impact': '1'}

    def test_general_member_and_fake_role_cannot_access_admin(self):
        with self.client.session_transaction() as sess:
            sess.update(user_id='regular-user', role='owner', is_admin=True, admin_id=self.owner)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertEqual(self.client.get('/admin/api/market').status_code, 401)

    def test_first_login_requires_password_change(self):
        self.login(password=PASSWORD)
        response = self.client.get('/admin/')
        self.assertTrue(response.location.endswith('/admin/password'))
        self.assertEqual(self.client.get('/admin/api/market').status_code, 403)
        result = self.post('/admin/password', old_password=PASSWORD, new_password=NEW_PASSWORD, confirm_password=NEW_PASSWORD)
        self.assertTrue(result.location.endswith('/admin/login'))
        self.assertIsNone(self.admin.login('owner', PASSWORD, 'old-password-test'))
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_csrf_required_on_login_and_privileged_actions(self):
        self.assertEqual(self.client.post('/admin/login', data={'username': 'owner', 'password': PASSWORD}).status_code, 403)
        self.ready()
        self.assertEqual(self.client.post('/admin/news', data=self.news_form()).status_code, 403)
        self.assertEqual(self.client.post('/admin/logout').status_code, 403)
        self.assertEqual(self.admin.articles(), [])

    def test_editor_cannot_manage_admin_accounts(self):
        editor = self.admin.create_account('editor', PASSWORD, 'editor')
        self.admin.change_password(editor, PASSWORD, NEW_PASSWORD)
        self.login('editor')
        dashboard = self.client.get('/admin/').get_data(as_text=True)
        self.assertNotIn('id="accounts"', dashboard)
        response = self.post('/admin/accounts', username='intruder', temporary_password=PASSWORD,
                             confirm_password=PASSWORD, role='owner')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.post(f'/admin/accounts/{self.owner}/disable').status_code, 403)

    def test_owner_creates_account_without_disclosing_password(self):
        self.ready()
        result = self.post('/admin/accounts', username='new-editor', temporary_password=PASSWORD,
                           confirm_password=PASSWORD, role='editor')
        self.assertEqual(result.status_code, 302)
        account = next(a for a in self.admin.accounts() if a['username'] == 'new-editor')
        self.assertEqual(account['must_change_password'], 1)
        self.assertNotIn(PASSWORD, str(self.admin.audit()))
        self.assertNotIn('password_hash', account)

    def test_disabling_account_revokes_existing_sessions(self):
        self.ready()
        editor = self.admin.create_account('editor', PASSWORD, 'editor')
        self.admin.change_password(editor, PASSWORD, NEW_PASSWORD)
        token = self.admin.login('editor', NEW_PASSWORD, 'another-ip')
        self.assertIsNotNone(self.admin.get_session(token))
        self.assertEqual(self.post(f'/admin/accounts/{editor}/disable').status_code, 302)
        self.assertIsNone(self.admin.get_session(token))
        self.assertIsNone(self.admin.login('editor', NEW_PASSWORD, 'another-ip'))

    def test_last_owner_and_self_disable_rejected(self):
        self.ready()
        with self.assertRaises(ValueError):
            self.admin.disable_account(self.owner)
        with self.assertRaises(ValueError):
            self.admin.disable_account(self.owner, self.owner)
        self.assertEqual(self.admin.accounts()[0]['active'], 1)

    def test_logout_invalidates_cookie_replay(self):
        self.ready()
        old_cookie = self.client.get_cookie('session').value
        self.post('/admin/logout')
        self.client.set_cookie('session', old_cookie)
        self.assertEqual(self.client.get('/admin/api/market').status_code, 401)

    def test_password_change_invalidates_all_sessions(self):
        self.ready()
        token = self.admin.login('owner', NEW_PASSWORD, 'another-ip')
        self.admin.change_password(self.owner, NEW_PASSWORD, 'another-valid-password-789')
        self.assertIsNone(self.admin.get_session(token))
        self.assertEqual(self.client.get('/admin/api/market').status_code, 401)

    def test_expired_session_is_denied(self):
        self.ready()
        self.admin.clock = lambda: time.time() + 9*3600
        self.assertEqual(self.client.get('/admin/api/market').status_code, 401)

    def test_login_failure_limits_are_persistent(self):
        for _ in range(5):
            self.assertIsNone(self.admin.login('owner', 'incorrect-password', 'test-ip'))
        with self.assertRaises(ValueError):
            self.admin.login('owner', PASSWORD, 'test-ip')
        self.admin.clock = lambda: time.time() + 901
        self.assertIsNotNone(self.admin.login('owner', PASSWORD, 'test-ip'))

    def test_news_article_event_and_audit_are_saved_once(self):
        self.ready()
        self.assertEqual(self.post('/admin/news', **self.news_form()).status_code, 302)
        self.assertEqual(self.post('/admin/news', **self.news_form()).status_code, 302)
        self.assertEqual(len(self.admin.articles()), 1)
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_news').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM admin_audit WHERE action='news.publish'").fetchone()[0], 1)
            event = db.execute('SELECT * FROM market_news').fetchone()
            self.assertEqual(event['target'], 6)
            self.assertEqual(event['impact'], 0.01)
        self.assertEqual(self.admin.articles()[0]['target_name'], '정보')

    def test_atomic_news_failure_rolls_back_price_event(self):
        self.ready()
        with patch.object(self.admin, '_audit', side_effect=sqlite3.OperationalError('test')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.post('/admin/news', **self.news_form())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.admin.articles(), [])
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_news').fetchone()[0], 0)

    def test_invalid_impact_cannot_create_news(self):
        self.ready()
        for impact in ('nan', 'inf', '16', '-16', '0', 'invalid'):
            data = self.news_form()
            data['impact'] = impact
            self.post('/admin/news', **data)
        self.assertEqual(self.admin.articles(), [])

    def test_html_is_escaped_in_admin_and_public_news(self):
        self.ready()
        self.admin.publish_news('xss-test', '<script>alert(1)</script>', '<img src=x onerror=alert(1)>', 'club', 61, 0.01, self.owner)
        dashboard = self.client.get('/admin/').get_data(as_text=True)
        self.assertIn('&lt;script&gt;', dashboard)
        self.assertNotIn('<script>alert(1)', dashboard)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'regular-user'
        public = self.client.get('/news').get_data(as_text=True)
        self.assertIn('&lt;script&gt;', public)
        self.assertNotIn('<img src=x onerror', public)

    def test_private_headers_and_no_internal_market_seed(self):
        self.ready()
        response = self.client.get('/admin/api/market')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertNotIn('seed', response.get_data(as_text=True))

    def test_cli_create_and_reset(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['admin', 'create', '--username', 'cli-admin', '--role', 'editor'],
                               input=f'{PASSWORD}\n{PASSWORD}\n')
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIsNotNone(self.admin.login('cli-admin', PASSWORD, 'cli-ip'))
        reset = runner.invoke(args=['admin', 'reset-password', '--username', 'cli-admin'],
                              input=f'{NEW_PASSWORD}\n{NEW_PASSWORD}\n')
        self.assertEqual(reset.exit_code, 0, reset.output)
        self.assertIsNone(self.admin.login('cli-admin', PASSWORD, 'cli-ip'))
