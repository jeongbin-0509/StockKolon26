"""TEST_POSTGRES_URL을 지정하면 실제 PostgreSQL에서도 권한·거래 저장을 검증한다."""
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql

from app import create_app
from app.services.market_service import MarketService
import test_admin
import test_market

TEST_URL = os.getenv('TEST_POSTGRES_URL')


class PostgresFixture:
    def new_schema(self):
        self.schema = 'stockolon_test_' + secrets.token_hex(8)
        self.addCleanup(self.drop_schema)

    def drop_schema(self):
        # 오직 이 테스트가 만든 임의의 스키마만 정리한다.
        with psycopg.connect(TEST_URL) as db:
            db.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(self.schema)))


@unittest.skipUnless(TEST_URL, 'TEST_POSTGRES_URL이 없으면 PostgreSQL 통합 검증을 생략합니다.')
class PostgresAdminTests(PostgresFixture, test_admin.AdminTests):
    def setUp(self):
        self.new_schema()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'postgres-tests-only',
                               'DATABASE_URL': TEST_URL, 'DATABASE_SCHEMA': self.schema})
        self.client = self.app.test_client()
        self.admin = self.app.extensions['admin']
        self.market = self.app.extensions['market']
        self.owner = self.admin.create_account('owner', test_admin.PASSWORD, 'owner')


@unittest.skipUnless(TEST_URL, 'TEST_POSTGRES_URL이 없으면 PostgreSQL 통합 검증을 생략합니다.')
class PostgresApiTests(PostgresFixture, test_market.ApiTests):
    def setUp(self):
        self.new_schema()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'postgres-tests-only',
                               'DATABASE_URL': TEST_URL, 'DATABASE_SCHEMA': self.schema})
        self.client = self.app.test_client()


@unittest.skipUnless(TEST_URL, 'TEST_POSTGRES_URL이 없으면 PostgreSQL 통합 검증을 생략합니다.')
class PostgresMarketTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        self.new_schema()
        self.now = 1800000000
        self.service = MarketService(TEST_URL, clock=lambda: self.now, schema=self.schema)
        self.service.initialize()

    def test_restart_concurrency_and_recovery(self):
        self.service.add_news('pg-news', 'club', 61, 0.01)
        self.service.record_flow('pg-fill', 61, 100)
        self.now += 3600
        with ThreadPoolExecutor(max_workers=4) as pool:
            data = list(pool.map(lambda _: self.service.snapshot(), range(4)))
        self.assertTrue(all(snapshot == data[0] for snapshot in data))
        other = MarketService(TEST_URL, clock=lambda: self.now, schema=self.schema)
        other.initialize()
        self.assertEqual(other.snapshot(), data[0])
        with other.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_ticks').fetchone()[0], 121*33)
            self.assertEqual(db.execute('SELECT SUM(volume) FROM market_ticks').fetchone()[0], 100)

    def test_transaction_rolls_back(self):
        with self.assertRaises(ValueError):
            with self.service.connection(write=True) as db:
                db.execute("UPDATE market_stocks SET price=1 WHERE club_num=61")
                raise ValueError('test rollback')
        self.assertEqual(next(s for s in self.service.snapshot()['stocks'] if s['club_num'] == 61)['price'], 10000)

    def test_same_path_as_sqlite_and_bounded_catchup(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            local = MarketService(Path(directory)/'market.sqlite3', clock=lambda: self.now)
            local.initialize()
            for service in (local, self.service):
                with service.connection(write=True) as db:
                    db.execute("UPDATE market_state SET seed='identical-test-seed'")
                service.add_news('same-news', 'club', 61, -0.02)
                service.record_flow('same-fill', 62, -80)
            self.now += 600
            expected, actual = local.snapshot(), self.service.snapshot()
            self.assertEqual(expected, actual)


import test_email


@unittest.skipUnless(TEST_URL, 'TEST_POSTGRES_URL이 없으면 PostgreSQL 통합 검증을 생략합니다.')
class PostgresEmailTests(PostgresFixture, test_email.EmailTests):
    def setUp(self):
        self.new_schema()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'email-tests-only-not-a-real-secret',
                               'DATABASE_URL': TEST_URL, 'DATABASE_SCHEMA': self.schema,
                               'EMAIL_PROVIDER': 'brevo', 'BREVO_API_KEY': 'test-api-key', 'MAIL_FROM': 'sender@example.com'})
        self.client = self.app.test_client()
        self.verification = self.app.extensions['email_verification']
