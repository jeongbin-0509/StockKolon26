import re
import tempfile
import unittest
from pathlib import Path

from app import create_app


class FavoriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'favorite-test',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.client = self.app.test_client()

    def login_as(self, user):
        with self.client.session_transaction() as session:
            session.clear()
            session['user_id'] = user
        page = self.client.get('/buy').get_data(as_text=True)
        self.assertIn('id="stock-search"', page)
        return re.search(r'data-csrf="([^"]+)"', page).group(1)

    def test_account_isolation_persistence_and_idempotent_updates(self):
        self.assertEqual(self.client.get('/api/favorites').status_code, 401)
        token = self.login_as('first')
        headers = {'X-CSRF-Token': token}
        for _ in range(2):
            response = self.client.put('/api/favorites', json={'clubNum': 61}, headers=headers)
            self.assertEqual(response.json['favorites'], [61])
        self.assertEqual(self.client.get('/api/favorites').json['favorites'], [61])
        self.login_as('second')
        self.assertEqual(self.client.get('/api/favorites').json['favorites'], [])
        token = self.login_as('first')
        for _ in range(2):
            response = self.client.delete('/api/favorites', json={'clubNum': 61}, headers={'X-CSRF-Token': token})
            self.assertEqual(response.json['favorites'], [])

    def test_invalid_requests_do_not_modify_favorites(self):
        token = self.login_as('first')
        self.assertEqual(self.client.put('/api/favorites', json={'clubNum': 61}).status_code, 403)
        for club in (True, '61', 999, None):
            response = self.client.put('/api/favorites', json={'clubNum': club}, headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/favorites').json['favorites'], [])
        self.assertEqual(self.client.get('/api/favorites').headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
