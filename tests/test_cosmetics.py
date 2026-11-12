import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.services.cosmetics import Cosmetics, DAY
from app.services.ranking_service import profile_key


class CosmeticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'cosmetics-test',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.market = self.app.extensions['market']
        self.cosmetics = self.app.extensions['cosmetics']
        self.trade = self.app.extensions['trading']
        self.now = 1800000000
        self.market.clock = lambda: self.now
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE users (id TEXT PRIMARY KEY, cash INTEGER NOT NULL)')
            db.execute("INSERT INTO users VALUES ('me',1000000),('other',990000)")
            db.execute('UPDATE market_state SET last_tick=?', (self.now,))

    def state(self, user='me'):
        with self.market.connection() as db:
            return self.cosmetics.read(db, user)

    def observe(self, delta=0):
        self.now += delta
        with self.market.connection(write=True) as db:
            self.cosmetics.observe_now(db, self.now)
            db.execute('UPDATE market_state SET last_tick=?', (self.now // 30 * 30,))

    def order(self, side='buy', qty=1, key=None):
        return self.trade.place_order('me', key or str(uuid.uuid4()), 61, side, qty)

    def price(self, value):
        with self.market.connection(write=True) as db:
            db.execute('UPDATE market_stocks SET price=? WHERE club_num=61', (value,))

    def test_24h_exact_boundary_and_permanent_after_restart(self):
        self.observe()
        self.observe(DAY - 1)
        self.assertNotIn('sovereign', self.state()['owned'])
        self.observe(1)
        self.assertTrue({'prime','apex','sovereign'} <= self.state()['owned'].keys())
        self.cosmetics = Cosmetics(self.market)
        self.cosmetics.initialize()
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=1 WHERE id='me'")
        self.observe(1)
        self.assertNotIn('sovereign', self.state()['starts'])
        self.assertIn('sovereign', self.state()['owned'])

    def test_rank_drop_resets_timer_and_ties_are_first(self):
        self.observe()
        self.observe(DAY - 30)
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=2000000 WHERE id='other'")
        self.observe()
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=1000000 WHERE id='other'")
        self.observe(1)
        self.assertEqual(self.state()['rank'], 1)
        self.observe(29)
        self.assertNotIn('sovereign', self.state()['owned'])
        self.assertIn('prime', self.state()['owned'])

    def test_offline_price_replay_detects_intermediate_drop(self):
        with self.market.connection(write=True) as db:
            db.execute("INSERT INTO trade_holdings VALUES ('me',61,1,10000)")
            db.execute("UPDATE users SET cash=1005000 WHERE id='other'")
        self.observe()
        self.now += 90
        calls = []
        def ticks(prices, state, *args):
            calls.append(1)
            prices[61] = 1 if len(calls) == 2 else 10000
            return prices, state, {club:{} for club in prices}
        with patch('app.services.market_service.next_tick', side_effect=ticks):
            self.market.snapshot()
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.state()['starts']['sovereign'], self.now)

    def test_new_account_not_backdated_during_catchup(self):
        with self.market.connection(write=True) as db:
            db.execute('UPDATE market_state SET last_tick=?', (self.now - DAY,))
        self.market.snapshot()
        self.assertEqual(self.state()['starts'], {})
        self.assertEqual(set(self.state()['owned']), {'prologue'})

    def test_new_player_does_not_rewrite_older_rank_history(self):
        self.observe()
        start = self.now
        self.now += 90
        with self.market.connection(write=True) as db:
            db.execute("INSERT INTO users VALUES ('new',9999999)")
            batch = self.cosmetics.batch(db)
            batch.observe({61:10000}, start + 30)
            self.assertEqual(batch.states['me']['rank'], 1)
            batch.observe({61:10000}, self.now)
            self.assertEqual(batch.states['me']['rank'], 2)
            self.assertNotIn('sovereign', batch.states['me']['starts'])

    def test_trade_resets_rank_between_price_ticks(self):
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=999975 WHERE id='other'")
        self.observe()
        self.now += 1
        self.order()
        self.assertEqual(self.state()['rank'], 2)
        self.assertNotIn('sovereign', self.state()['starts'])

    def test_zero_profit_sell_breaks_streak_and_cannot_earn_slayer(self):
        self.observe()
        with self.market.connection(write=True) as db:
            state = self.cosmetics.read(db, 'me')
            state['streak'] = 4
            self.cosmetics.save(db, 'me', state)
            db.execute("INSERT INTO market_news VALUES ('active','club',61,-0.02,?)", (self.now,))
            self.cosmetics.after_trade(db, 'me', 61, 'sell', 0, self.now, self.now)
        self.assertEqual(self.state()['streak'],0)
        self.assertNotIn('slayer',self.state()['owned'])
        self.assertNotIn('oracle',self.state()['owned'])

    def test_tracker_200_within_window_and_expired_peak(self):
        with self.market.connection(write=True) as db:
            db.executemany('INSERT INTO users VALUES (?,?)', [(f'p{i}',2000000+i) for i in range(200)])
        self.observe()
        self.assertEqual(self.state()['rank'], 201)
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=3000000 WHERE id='me'")
        self.observe(DAY + 1)
        self.assertNotIn('tracker', self.state()['owned'])
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=1000000 WHERE id='me'")
        self.observe(1)
        with self.market.connection(write=True) as db:
            db.execute("UPDATE users SET cash=3000000 WHERE id='me'")
        self.observe(DAY)
        self.assertIn('tracker', self.state()['owned'])

    def test_consecutive_profit_replay_buys_and_loss(self):
        self.order(qty=10)
        self.price(11000)
        key = str(uuid.uuid4())
        self.order('sell', key=key)
        self.assertTrue(self.order('sell', key=key)['replayed'])
        self.assertEqual(self.state()['streak'], 1)
        self.order('buy')
        for _ in range(3):
            self.order('sell')
        self.assertNotIn('oracle', self.state()['owned'])
        self.order('sell')
        self.assertIn('oracle', self.state()['owned'])
        self.price(1)
        self.order('sell')
        self.assertEqual(self.state()['streak'], 0)
        self.assertIn('oracle', self.state()['owned'])

    def test_anchor_partial_sale_preserves_full_exit_resets(self):
        self.order(qty=4)
        start = self.now
        self.observe(DAY)
        self.order('buy')
        self.order('sell')
        self.assertEqual(self.state()['positions']['61'], start)
        self.observe(DAY)
        self.order('sell', 4)
        self.assertEqual(self.state()['positions'], {})
        self.order('buy')
        self.observe(DAY)
        self.assertNotIn('anchor', self.state()['owned'])
        self.observe(2 * DAY)
        self.assertIn('anchor', self.state()['owned'])

    def test_slayer_only_actual_negative_influence_window(self):
        self.order(qty=10)
        self.price(12000)
        with self.market.connection(write=True) as db:
            db.execute('INSERT INTO market_news VALUES (?,?,?,?,?)', ('negative','club',61,-0.02,self.now+30))
        self.order('sell')
        self.assertNotIn('slayer', self.state()['owned'])
        self.observe(30)
        self.order('sell')
        self.assertIn('slayer', self.state()['owned'])

    def test_slayer_expired_wrong_club_and_positive_news_do_not_count(self):
        self.order(qty=5)
        self.price(12000)
        with self.market.connection(write=True) as db:
            db.executemany('INSERT INTO market_news VALUES (?,?,?,?,?)', [
                ('old','club',61,-0.02,self.now-3600), ('other','club',1,-0.02,self.now),
                ('positive','club',61,0.02,self.now)])
        self.order('sell')
        self.assertNotIn('slayer', self.state()['owned'])
        with self.market.connection(write=True) as db:
            db.execute('INSERT INTO market_news VALUES (?,?,?,?,?)', ('last','club',61,-0.02,self.now-3570))
        self.order('sell')
        self.assertIn('slayer', self.state()['owned'])

    def test_earlybird_korean_hour(self):
        self.now = DAY * 21000 + 17 * 3600 + 3599  # UTC 17:59:59 = KST 02:59:59
        self.cosmetics.visit('me')
        self.assertNotIn('earlybird', self.state()['owned'])
        self.now += 1
        self.cosmetics.visit('me')
        self.assertIn('earlybird', self.state()['owned'])
        self.now += 3600
        self.cosmetics.visit('other')
        self.assertNotIn('earlybird', self.state('other')['owned'])

    def test_equip_enforces_ownership_csrf_and_session_identity(self):
        client = self.app.test_client()
        self.assertEqual(client.get('/api/cosmetics').status_code, 401)
        with client.session_transaction() as session:
            session['user_id'] = 'me'
            session['admin_csrf'] = 'test-csrf'
        payload = dict(signature='sovereign', frame='sovereign')
        self.assertEqual(client.post('/api/cosmetics/equip', json=payload).status_code, 403)
        headers = {'X-CSRF-Token':'test-csrf'}
        self.assertEqual(client.post('/api/cosmetics/equip', json=payload, headers=headers).status_code, 400)
        payload = dict(user_id='other', signature='prologue', frame=None)
        result = client.post('/api/cosmetics/equip', json=payload, headers=headers)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(self.state()['frame'])
        self.assertEqual(self.state('other')['frame'], 'prologue')
        for value in ([], {}, 123, '<img onerror=alert(1)>'):
            self.assertEqual(client.post('/api/cosmetics/equip', json=dict(signature=value,frame=None), headers=headers).status_code,400)
        result = client.get('/api/cosmetics')
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(result.json['items']),9)
        self.assertEqual(result.headers['Cache-Control'],'no-store')

    def test_public_decoration_does_not_leak_internal_tracking(self):
        self.observe()
        result = self.cosmetics.public([profile_key('me'),profile_key('new')])
        for item in result.values():
            self.assertEqual(set(item), {'signature','name','frame'})
            self.assertEqual(item['name'], 'PROLOGUE')


if __name__ == '__main__':
    unittest.main()
