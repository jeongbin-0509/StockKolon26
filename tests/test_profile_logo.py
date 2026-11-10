import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import create_app


class ProfileLogoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'profile-tests',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = 'test-user'
        self.fake = MagicMock()
        self.user_table = MagicMock()
        self.club_table = MagicMock()
        self.fake.table.side_effect = lambda name: {'users': self.user_table, 'clubs': self.club_table}[name]
        ranking = patch.object(self.app.extensions['ranking'], 'rankings',
                               return_value={'me': {'rank': 7}, 'count': 42})
        self.ranking = ranking.start()
        self.addCleanup(ranking.stop)

    def set_user(self, club_id, club_name=None):
        self.user_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            'name': '학생', 'cash': 100, 'club_id': club_id}
        self.club_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
            [{'name': club_name}] if club_name else [])

    def test_club_logo_is_shared_by_index_and_profile(self):
        self.set_user('club-uuid', '세미콜론')
        with patch('app.routes.main.supabase', new=self.fake):
            index = self.client.get('/api/index-data').get_json()['profile']
            profile = self.client.get('/api/profile-data').get_json()['user']
        self.assertEqual(index['profileImg'], '/static/images/61.png')
        self.assertEqual(profile['profileImg'], index['profileImg'])
        self.assertEqual(profile['clubName'], '세미콜론')
        self.assertEqual(profile['rank'], '전교 7위 · 42명 중')

    def test_missing_club_or_logo_uses_existing_default(self):
        with patch('app.routes.main.supabase', new=self.fake):
            for club_id, club_name in [(None, None), ('unknown', None), ('club-uuid', '에스쿱')]:
                self.set_user(club_id, club_name)
                image = self.client.get('/api/profile-data').get_json()['user']['profileImg']
                self.assertEqual(image, '/static/images/default_stock_logo.png')
                response = self.client.get(image)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_unauthenticated_cannot_read_profile(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/profile-data').status_code, 401)

    def test_trade_view_skips_expensive_market_and_history_calls(self):
        self.set_user('club-uuid', '세미콜론')
        market = self.app.extensions['market']
        trade = self.app.extensions['trading']
        self.ranking.side_effect = AssertionError('unnecessary ranking query')
        with patch('app.routes.main.supabase', new=self.fake), \
                patch.object(market, 'snapshot', side_effect=AssertionError('unnecessary market snapshot')), \
                patch.object(trade, 'history', side_effect=AssertionError('unnecessary order history')):
            response = self.client.get('/api/profile-data?view=trade')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['profileImg'], '/static/images/61.png')
        self.assertEqual(response.json['user']['cash'], 100)
        self.assertEqual(response.json['orders'], [])
        self.ranking.assert_not_called()

    def test_ranking_failure_preserves_profile_and_portfolio(self):
        self.set_user(None)
        self.ranking.side_effect = RuntimeError('private connection details')
        with patch('app.routes.main.supabase', new=self.fake):
            response = self.client.get('/api/profile-data')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['cash'], 100)
        self.assertEqual(response.json['user']['rank'], '순위를 불러올 수 없습니다')
        self.assertNotIn('private connection details', response.get_data(as_text=True))

    def test_header_profile_does_not_load_portfolio_or_market(self):
        self.set_user('club-uuid', '세미콜론')
        with patch('app.routes.main.supabase', new=self.fake), \
                patch.object(self.app.extensions['market'], 'snapshot', side_effect=AssertionError('unnecessary market snapshot')), \
                patch.object(self.app.extensions['trading'], 'portfolio', side_effect=AssertionError('unnecessary portfolio')):
            response = self.client.get('/api/header-profile')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['profileImg'], '/static/images/61.png')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
