import tempfile
import re
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from werkzeug.security import check_password_hash

from app import create_app
from app.services.email_service import EmailDeliveryError, send_email_code
from app.services.email_verification import EmailRateLimit


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'email-tests-only-not-a-real-secret',
                               'MARKET_DATABASE': str(Path(self.tmp.name)/'market.sqlite3'),
                               'EMAIL_PROVIDER': 'brevo', 'BREVO_API_KEY': 'test-api-key', 'MAIL_FROM': 'sender@example.com'})
        self.client = self.app.test_client()
        self.verification = self.app.extensions['email_verification']

    def issue(self, email='student@goedu.kr'):
        with patch('app.routes.auth.generate_code', return_value='123456'), patch('app.routes.auth.send_email_code'):
            response = self.client.post('/auth/send-code', json={'email': email})
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as sess:
            return sess['email_challenge']

    def test_cookie_has_only_opaque_id_and_database_has_no_plain_code(self):
        challenge = self.issue()
        with self.client.session_transaction() as sess:
            self.assertNotIn('email_code', sess)
            self.assertNotIn('email', sess)
        with self.app.extensions['market'].connection() as db:
            row = dict(db.execute('SELECT * FROM email_verifications WHERE id=?', (challenge,)).fetchone())
        self.assertNotIn('123456', str(row))
        self.assertEqual(len(row['digest']), 64)

    def test_bad_address_and_bad_json_do_not_send_email(self):
        with patch('app.routes.auth.send_email_code') as send:
            self.assertEqual(self.client.post('/auth/send-code', json={'email': 'other@example.com'}).status_code, 400)
            self.assertEqual(self.client.post('/auth/send-code', json=[]).status_code, 400)
            send.assert_not_called()

    def test_failed_provider_does_not_activate_code(self):
        with patch('app.routes.auth.send_email_code', side_effect=EmailDeliveryError('delivery unavailable')):
            response = self.client.post('/auth/send-code', json={'email': 'student@goedu.kr'})
        self.assertEqual(response.status_code, 503)
        with self.client.session_transaction() as sess:
            self.assertNotIn('email_challenge', sess)
        with self.app.extensions['market'].connection() as db:
            self.assertEqual(db.execute('SELECT status FROM email_verifications').fetchone()[0], 'failed')

    def test_expired_code_and_other_email_are_rejected(self):
        challenge = self.issue()
        self.assertFalse(self.verification.consume(challenge, 'someoneelse@goedu.kr', '123456'))
        self.verification.clock = lambda: time.time()+601
        self.assertFalse(self.verification.consume(challenge, 'student@goedu.kr', '123456'))

    def test_five_failed_attempts_lock_the_code(self):
        challenge = self.issue()
        for _ in range(5):
            self.assertFalse(self.verification.consume(challenge, 'student@goedu.kr', '000000'))
        self.assertFalse(self.verification.consume(challenge, 'student@goedu.kr', '123456'))

    def test_resend_limits_and_latest_code(self):
        now = [1800000000]
        self.verification.clock = lambda: now[0]
        first = self.verification.prepare('student@goedu.kr', 'local-test-ip', '111111')
        self.verification.activate(first)
        with self.assertRaises(EmailRateLimit):
            self.verification.prepare('student@goedu.kr', 'local-test-ip', '222222')
        now[0] += 61
        second = self.verification.prepare('student@goedu.kr', 'local-test-ip', '222222')
        self.verification.activate(second)
        self.assertFalse(self.verification.consume(first, 'student@goedu.kr', '111111'))
        self.assertTrue(self.verification.consume(second, 'student@goedu.kr', '222222'))
        now[0] += 61
        third = self.verification.prepare('student@goedu.kr', 'local-test-ip', '333333')
        self.verification.activate(third)
        now[0] += 61
        with self.assertRaises(EmailRateLimit):
            self.verification.prepare('student@goedu.kr', 'local-test-ip', '444444')

    def test_daily_email_limit_resets_at_korean_midnight(self):
        kst = timezone(timedelta(hours=9))
        now = [int(datetime(2026, 11, 1, 22, 0, tzinfo=kst).timestamp())]
        self.verification.clock = lambda: now[0]
        for _ in range(5):
            challenge = self.verification.prepare('student@goedu.kr', 'test-ip', '123456')
            self.verification.activate(challenge)
            now[0] += 901
        with self.assertRaisesRegex(EmailRateLimit, '5회'):
            self.verification.prepare('STUDENT@goedu.kr', 'test-ip', '123456')
        now[0] = int(datetime(2026, 11, 2, 0, 0, tzinfo=kst).timestamp())
        self.assertTrue(self.verification.prepare('student@goedu.kr', 'test-ip', '123456'))

    def test_failed_delivery_does_not_use_daily_allowance(self):
        kst = timezone(timedelta(hours=9))
        now = [int(datetime(2026, 11, 1, 10, 0, tzinfo=kst).timestamp())]
        self.verification.clock = lambda: now[0]
        for _ in range(5):
            challenge = self.verification.prepare('student@goedu.kr', 'test-ip', '123456')
            self.verification.fail(challenge)
            now[0] += 901
        self.assertTrue(self.verification.prepare('student@goedu.kr', 'test-ip', '123456'))

    def test_signup_requires_verified_code_and_consumes_once(self):
        self.issue()
        form = {'name': '학생', 'usernum': '12345', 'email_id': 'student', 'email_code': '123456',
                'password': 'valid-password', 'password_check': 'valid-password', 'club_id': '61'}
        with patch('app.routes.auth.supabase', new=MagicMock()) as supabase:
            response = self.client.post('/auth/signup', data=form)
            self.assertTrue(response.location.endswith('/auth/login'))
            payload = supabase.table.return_value.insert.call_args.args[0]
            self.assertTrue(check_password_hash(payload['password'], 'valid-password'))
            self.client.post('/auth/signup', data=form)
            self.assertEqual(supabase.table.return_value.insert.call_count, 1)

    def test_password_reset_requires_email_code_and_is_single_use(self):
        page = self.client.get('/auth/forgot-password').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        fake = MagicMock()
        table = fake.table.return_value
        table.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{'id': 'member-1'}]
        table.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{'id': 'member-1'}]
        with patch('app.routes.auth.supabase', new=fake), patch('app.routes.auth.generate_code', return_value='123456'), patch('app.routes.auth.send_email_code') as send:
            result = self.client.post('/auth/forgot-password', data={'csrf_token': token, 'usernum': '12345', 'email': 'student@goedu.kr'})
            self.assertTrue(result.location.endswith('/auth/reset-password'))
            send.assert_called_once_with('student@goedu.kr', '123456')
            with self.client.session_transaction() as sess:
                self.assertIsInstance(sess['password_reset'], str)
                self.assertNotIn('member-1', str(dict(sess)))
                self.assertNotIn('student@goedu.kr', str(dict(sess)))
            form = {'csrf_token': token, 'email_code': '000000', 'password': 'new-password', 'password_check': 'new-password'}
            self.client.post('/auth/reset-password', data=form)
            table.update.assert_not_called()
            form['email_code'] = '123456'
            old_cookie = self.client.get_cookie('session').value
            result = self.client.post('/auth/reset-password', data=form)
            self.assertTrue(result.location.endswith('/auth/login'))
            self.assertTrue(check_password_hash(table.update.call_args.args[0]['password'], 'new-password'))
            self.client.post('/auth/reset-password', data=form)
            self.assertEqual(table.update.call_count, 1)
            self.client.set_cookie('session', old_cookie)
            replay = self.client.post('/auth/reset-password', data=form, follow_redirects=True)
            self.assertIn('이미 사용된 인증번호', replay.get_data(as_text=True))
            self.assertEqual(table.update.call_count, 1)

    def test_unknown_account_never_receives_reset_code(self):
        page = self.client.get('/auth/forgot-password').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        fake = MagicMock()
        fake.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        with patch('app.routes.auth.supabase', new=fake), patch('app.routes.auth.send_email_code') as send:
            result = self.client.post('/auth/forgot-password', data={'csrf_token': token, 'usernum': '12345', 'email': 'student@goedu.kr'})
            self.assertTrue(result.location.endswith('/auth/reset-password'))
            send.assert_not_called()
            self.client.post('/auth/reset-password', data={'csrf_token': token, 'email_code': '123456', 'password': 'new-password', 'password_check': 'new-password'})
            fake.table.return_value.update.assert_not_called()

    def test_password_reset_requires_csrf(self):
        self.assertEqual(self.client.post('/auth/forgot-password', data={'usernum': '12345', 'email': 'student@goedu.kr'}).status_code, 403)

    def test_brevo_and_resend_use_https_and_configured_sender(self):
        for provider, endpoint in [('brevo','https://api.brevo.com/v3/smtp/email'), ('resend','https://api.resend.com/emails')]:
            self.app.config.update(EMAIL_PROVIDER=provider, RESEND_API_KEY='test-resend-key')
            result = httpx.Response(201, request=httpx.Request('POST',endpoint), json={'id':'test-only'})
            with self.app.app_context(), patch('app.services.email_service.httpx.post', return_value=result) as post:
                send_email_code('student@goedu.kr', '123456')
            self.assertEqual(post.call_args.args[0], endpoint)
            self.assertFalse(post.call_args.kwargs['follow_redirects'])
            self.assertEqual(post.call_args.kwargs['timeout'], 10)

    def test_http_failure_does_not_expose_provider_response(self):
        failure = httpx.Response(401, request=httpx.Request('POST', 'https://api.brevo.com/v3/smtp/email'), text='sensitive-provider-diagnostics')
        with self.app.app_context(), patch('app.services.email_service.httpx.post', return_value=failure):
            with self.assertRaises(EmailDeliveryError) as caught:
                send_email_code('student@goedu.kr', '123456')
        self.assertNotIn('sensitive-provider-diagnostics', str(caught.exception))
