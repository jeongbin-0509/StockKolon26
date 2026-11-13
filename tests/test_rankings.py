import tempfile
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from app import create_app
from app.services.market_service import trade_quotes
from app.services.ranking_service import RankingService


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.market = self.app.extensions['market']
        # 기존 SQL 경로도 별도로 검증한다. 일반 로컬 앱은 Supabase 회원을 조회한다.
        self.app.extensions['ranking'] = RankingService(self.market)
        self.market.clock = lambda: 1800000000
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE clubs (id TEXT PRIMARY KEY, name TEXT)')
            db.execute('CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT, usernum TEXT, club_id TEXT, cash INTEGER)')
            db.execute("INSERT INTO clubs VALUES ('c1', '온에어'), ('c2', '다른 동아리')")
            db.execute("INSERT INTO users VALUES ('a', '가', '10101', 'c1', 5000), ('b', '나', '10102', 'c2', 14975), ('c', '다', '10201', 'c1', 20000), ('d', '라', '10103', NULL, 1000)")
            db.execute("INSERT INTO trade_holdings VALUES ('a', 1, 1, 10000)")
            db.execute('UPDATE market_stocks SET price=10000 WHERE club_num=1')
            db.execute('UPDATE market_state SET last_tick=?', (1800000000,))
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

    def test_header_rank_is_viewer_specific(self):
        first = self.client.get('/api/my-rank').get_json()
        self.assertEqual(first['rank'], 2)
        with self.client.session_transaction() as session:
            session['user_id'] = 'd'
        self.assertEqual(self.client.get('/api/my-rank').get_json()['rank'], 4)
        self.assertEqual(self.client.get('/api/my-rank').headers['Cache-Control'], 'no-store')

    def test_portfolio_uses_viewer_and_same_valuation_as_ranking(self):
        data = self.client.get('/api/portfolio').json
        self.assertEqual(data['portfolio'], self.app.extensions['trading'].portfolio('a'))
        self.assertEqual(data['user']['assets'], data['portfolio']['total'])
        self.assertEqual(data['portfolio']['holdings'][0]['name'], '온에어')
        self.assertEqual(self.client.get('/api/portfolio').headers['Cache-Control'], 'no-store')
        with self.client.session_transaction() as session:
            session['user_id'] = 'd'
        other = self.client.get('/api/portfolio').json
        self.assertEqual(other['portfolio']['holdings'], [])
        self.assertEqual(other['portfolio']['cash'], 1000)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/portfolio').status_code, 401)

    def test_public_portfolio_shows_selected_investor_not_viewer(self):
        import json, re
        from app.services.ranking_service import profile_key
        with self.client.session_transaction() as session:
            session['user_id'] = 'd'
        page = self.client.get('/members/' + profile_key('a'))
        data = json.loads(re.search(r'id="member-portfolio-data">(.*?)</script>', page.text, re.S).group(1))
        self.assertEqual(data['portfolio'], self.app.extensions['trading'].portfolio('a'))
        self.assertEqual(data['user']['name'], '가')
        for private in ('usernum', 'email', 'password', 'orders', 'user_id', 'club_id'):
            self.assertNotIn(private, str(data))
        self.assertNotIn('portfolio', self.client.get('/api/rankings').json)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')

    def test_portfolio_failure_is_retryable_without_private_details(self):
        with patch.object(self.app.extensions['ranking'], 'rankings', side_effect=sqlite3.Error('private db data')):
            response = self.client.get('/api/portfolio')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private db data', response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_public_profile_is_limited_and_requires_login(self):
        data = self.client.get('/api/rankings').get_json()
        target = next(m for m in data['members'] if m['name'] == '나')
        url = '/members/' + target['profile_key']
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('나의 프로필', body)
        self.assertIn('14,975', body)
        for private in ('10102', 'password', 'email', 'trade_holdings'):
            self.assertNotIn(private, body)
        self.assertEqual(self.client.get('/members/' + '0' * 64).status_code, 404)
        self.assertEqual(self.client.get('/members/bad').status_code, 404)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.get('/api/my-rank').status_code, 401)

    def test_market_compression_preserves_every_value(self):
        import gzip, json
        plain = self.client.get('/api/market').get_json()
        packed = self.client.get('/api/market', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(packed.headers['Content-Encoding'], 'gzip')
        self.assertEqual(json.loads(gzip.decompress(packed.data)), plain)
        refused = self.client.get('/api/market', headers={'Accept-Encoding': 'gzip;q=0'})
        self.assertNotIn('Content-Encoding', refused.headers)

    def test_lossless_image_content_negotiation(self):
        png = self.client.get('/static/images/news_icon.png')
        webp = self.client.get('/static/images/news_icon.png', headers={'Accept':'image/webp'})
        self.addCleanup(png.close)
        self.addCleanup(webp.close)
        self.assertEqual(png.mimetype, 'image/png')
        self.assertEqual(webp.mimetype, 'image/webp')
        self.assertLess(len(webp.data), len(png.data))
        self.assertIn('Accept', png.headers['Vary'])
        self.assertIn('Accept', webp.headers['Vary'])
        refused = self.client.get('/static/images/news_icon.png', headers={'Accept':'image/webp;q=0,image/png'})
        self.addCleanup(refused.close)
        self.assertEqual(refused.mimetype, 'image/png')

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

    def test_cash_and_price_changes_update_rankings(self):
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=25000 WHERE id='a'")
            db.execute('UPDATE market_stocks SET price=12000 WHERE club_num=1')
        data = self.client.get('/api/rankings').get_json()
        self.assertEqual(data['me']['rank'], 1)
        self.assertEqual(data['me']['assets'], self.app.extensions['trading'].portfolio('a')['total'])

    def test_database_failure_returns_safe_json(self):
        ranking = self.app.extensions['ranking']
        with patch.object(ranking, 'rankings', side_effect=httpx.ConnectError('private connection details')):
            response = self.client.get('/api/rankings')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json['success'])
        self.assertNotIn('private connection details', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')


class SupabaseRankingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'ranking-tests',
                               'MARKET_DATABASE': str(Path(tmp.name) / 'market.sqlite3')})
        self.market = self.app.extensions['market']
        self.market.clock = lambda: 1800000000
        with self.market.connection(write=True) as db:
            db.execute('UPDATE market_state SET last_tick=?', (1800000000,))
            db.execute('UPDATE market_stocks SET price=10000')
            db.execute("INSERT INTO trade_holdings VALUES ('a', 1, 2, 20000), ('a', 61, 1, 10000)")
            db.execute("INSERT INTO trade_holdings VALUES ('removed', 1, 100, 1000000)")
        self.rows = {
            'users': [
                {'id': 'a', 'name': '가', 'usernum': '10101', 'club_id': 'c1', 'cash': 5000},
                {'id': 'b', 'name': '나', 'usernum': '10102', 'club_id': 'c2', 'cash': 10000},
                {'id': 'c', 'name': '다', 'usernum': '10201', 'club_id': 'c1', 'cash': 20000},
            ],
            'clubs': [{'id': 'c1', 'name': '세미콜론'}, {'id': 'c2', 'name': '온에어'}],
        }
        self.api_cap = 500
        self.requests = []
        self.fake = MagicMock()
        self.fake.table.side_effect = self.table
        patcher = patch('app.services.ranking_service.get_supabase', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = 'a'

    def table(self, name):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query

        def page(start, end):
            self.requests.append((name, start, end, query.select.call_args.args[0]))
            records = sorted(self.rows[name], key=lambda row: row['id'])
            return SimpleNamespace(execute=lambda: SimpleNamespace(
                data=records[start:min(end + 1, start + self.api_cap)]))

        query.range.side_effect = page
        return query

    def test_remote_members_and_local_holdings_without_local_users_table(self):
        response = self.client.get('/api/rankings')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(data['count'], 3)
        self.assertEqual(data['me']['assets'], 5000 + trade_quotes(10000)[1] * 3)
        self.assertEqual(data['me']['rank'], 1)
        self.assertEqual(data['me']['profileImg'], '/static/images/61.png')
        self.assertEqual({request[3] for request in self.requests}, {'id,name,usernum,club_id,cash', 'id,name'})
        for field in ('id', 'usernum', 'club_id', 'cash', 'email', 'password'):
            self.assertNotIn(field, data['me'])

    def test_remote_class_and_club_filters(self):
        school_class = self.client.get('/api/rankings?scope=class').json
        club = self.client.get('/api/rankings?scope=club').json
        self.assertEqual({member['name'] for member in school_class['members']}, {'가', '나'})
        self.assertEqual({member['name'] for member in club['members']}, {'가', '다'})
        self.rows['users'][0]['club_id'] = None
        self.assertFalse(self.client.get('/api/rankings?scope=club').json['available'])
        self.rows['users'][0]['usernum'] = 'invalid'
        self.assertFalse(self.client.get('/api/rankings?scope=class').json['available'])

    def test_remote_portfolio_uses_target_holdings_and_cash(self):
        from app.services.ranking_service import profile_key
        result = self.app.extensions['ranking'].rankings('b', 'school', public_key=profile_key('a'))
        expected = self.app.extensions['trading'].portfolio('a', 5000)
        self.assertEqual(result['portfolio']['total'], expected['total'])
        self.assertEqual({h['club_num'] for h in result['portfolio']['holdings']}, {1, 61})
        self.assertEqual(result['portfolio']['cash'], 5000)
        self.assertFalse(result['me']['is_me'])

    def test_all_members_are_loaded_even_when_api_caps_each_page(self):
        self.api_cap = 73
        self.rows['users'].extend({'id': f'extra{i:04}', 'name': '학생', 'usernum': '10301',
                                   'club_id': None, 'cash': 100000 + i} for i in range(1100))
        data = self.client.get('/api/rankings').json
        self.assertEqual(data['count'], 1103)
        self.assertEqual(len(data['members']), 100)
        self.assertEqual(data['me']['rank'], 1101)
        self.assertTrue(any(name == 'users' and start > 1000 for name, start, _, _ in self.requests))

    def test_remote_cash_is_refreshed_and_invalid_accounts_are_excluded(self):
        self.rows['users'][1]['cash'] = 100000
        self.rows['users'][2]['cash'] = None
        data = self.client.get('/api/rankings').json
        self.assertEqual(data['me']['rank'], 2)
        self.assertEqual(data['count'], 2)
        self.rows['users'][1]['cash'] = -1
        self.assertEqual(self.client.get('/api/rankings').json['me']['rank'], 1)

    def test_remote_failure_returns_no_partial_ranking(self):
        self.fake.table.side_effect = httpx.ConnectError('private connection details')
        response = self.client.get('/api/rankings')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('members', response.json)
        self.assertNotIn('private connection details', response.get_data(as_text=True))

    def test_profile_uses_same_school_ranking(self):
        user_api = MagicMock()
        user_api.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = self.rows['users'][0]
        with patch('app.routes.main.supabase', new=user_api), \
                patch('app.routes.main.club_profile', return_value=('/static/images/61.png', '세미콜론')):
            data = self.client.get('/api/profile-data').json
        ranking = self.client.get('/api/rankings').json
        self.assertEqual(data['user']['rank'], '전교 1위 · 3명 중')
        self.assertEqual(data['user']['total_assets'], ranking['me']['assets'])

    def test_auth_and_invalid_scope_do_not_query_members(self):
        self.assertEqual(self.client.get('/api/rankings?scope=invalid').status_code, 400)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/rankings').status_code, 401)
        self.fake.table.assert_not_called()
