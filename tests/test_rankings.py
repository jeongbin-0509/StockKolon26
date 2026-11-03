import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.services.market_service import trade_quotes


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.market = self.app.extensions['market']
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE clubs (id TEXT PRIMARY KEY, name TEXT)')
            db.execute('CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT, usernum TEXT, club_id TEXT, cash INTEGER)')
            db.execute("INSERT INTO clubs VALUES ('c1', '온에어'), ('c2', '다른 동아리')")
            db.execute("INSERT INTO users VALUES ('a', '가', '10101', 'c1', 5000), ('b', '나', '10102', 'c2', 14975), ('c', '다', '10201', 'c1', 20000), ('d', '라', '10103', NULL, 1000)")
            db.execute("INSERT INTO trade_holdings VALUES ('a', 1, 1, 10000)")
            db.execute('UPDATE market_stocks SET price=10000 WHERE club_num=1')
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = 'a'

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_assets_ties_and_privacy(self):
        data = self.client.get('/api/rankings').get_json()
        self.assertEqual([x['rank'] for x in data['members']], [1, 2, 2, 4])
        self.assertEqual(data['me']['assets'], 5000 + trade_quotes(10000)[1])
        self.assertAlmostEqual(data['me']['rate'], -.25)
        self.assertNotIn('usernum', str(data))
        self.assertNotIn('club_id', str(data))
        self.assertEqual(self.client.get('/api/rankings').headers['Cache-Control'], 'no-store')

    def test_scopes(self):
        data = self.client.get('/api/rankings?scope=class').get_json()
        self.assertEqual({x['name'] for x in data['members']}, {'가', '나', '라'})
        data = self.client.get('/api/rankings?scope=club').get_json()
        self.assertEqual({x['name'] for x in data['members']}, {'가', '다'})
        with self.client.session_transaction() as session:
            session['user_id'] = 'd'
        self.assertFalse(self.client.get('/api/rankings?scope=club').get_json()['available'])
        self.assertEqual(self.client.get('/api/rankings?scope=bad').status_code, 400)

    def test_login_required_and_own_rank_after_first_hundred(self):
        with self.market.connection(write=True) as db:
            for i in range(101):
                db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?)',
                           (f'extra{i}', '학생', '10301', None, 100000 + i))
        data = self.client.get('/api/rankings').get_json()
        self.assertEqual(len(data['members']), 100)
        self.assertEqual(data['me']['rank'], 103)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/rankings').status_code, 401)
