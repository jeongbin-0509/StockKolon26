import re
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import create_app


class TradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'test.sqlite3')})
        self.market = self.app.extensions['market']
        self.trade = self.app.extensions['trading']
        self.now = 1800000000
        self.market.clock = lambda: self.now
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE users (id TEXT PRIMARY KEY, cash INTEGER NOT NULL)')
            db.execute('INSERT INTO users VALUES (?, ?)', ('member', 100000))
            db.execute('UPDATE market_state SET last_tick=?', (self.now // 30 * 30,))
        self.client = self.app.test_client()

    def place(self, side='buy', qty=2, price=None, order_id=None):
        stock = next(s for s in self.market.snapshot()['stocks'] if s['club_num'] == 61)
        price = price if price is not None else stock['buyPrice' if side == 'buy' else 'sellPrice']
        return self.trade.place_order('member', order_id or str(uuid.uuid4()), 61, side, qty, price)

    def test_buy_sell_and_valuation_are_saved_together(self):
        buy = self.place()
        self.assertTrue(buy['success'])
        portfolio = self.trade.portfolio('member')
        self.assertEqual(portfolio['cash'], 100000 - buy['order']['total'])
        self.assertEqual(portfolio['holdings'][0]['quantity'], 2)
        sell = self.place('sell', 1)
        self.assertTrue(sell['success'])
        portfolio = self.trade.portfolio('member')
        self.assertEqual(portfolio['holdings'][0]['quantity'], 1)
        self.assertEqual(portfolio['cost'], buy['order']['total'] // 2)
        self.assertEqual(portfolio['cash'], 100000 - buy['order']['total'] + sell['order']['total'])
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trade_orders').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_flows').fetchone()[0], 2)
        self.assertEqual(len(self.trade.history('member')), 2)
        self.assertEqual(self.trade.history('another'), [])

    def test_retry_is_idempotent_and_cannot_change_payload_or_owner(self):
        order_id = str(uuid.uuid4())
        first = self.place(order_id=order_id)
        second = self.place(order_id=order_id)
        self.assertTrue(second['replayed'])
        self.assertEqual(first['order'], second['order'])
        with self.assertRaises(ValueError):
            self.place(qty=3, order_id=order_id)
        with self.assertRaises(ValueError):
            self.trade.place_order('another', order_id, 61, 'buy', 2, first['order']['price'])
        self.assertEqual(self.trade.portfolio('member')['holdings'][0]['quantity'], 2)

    def test_insufficient_funds_holdings_and_old_price_do_not_trade(self):
        with self.assertRaisesRegex(ValueError, '현금'):
            self.place(qty=1000)
        with self.assertRaisesRegex(ValueError, '수량'):
            self.place('sell', qty=1)
        result = self.place(price=1)
        self.assertFalse(result['success'])
        self.assertTrue(result['priceChanged'])
        self.assertEqual(self.trade.portfolio('member')['cash'], 100000)
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trade_orders').fetchone()[0], 0)

    def test_parallel_orders_cannot_overspend(self):
        def attempt(_):
            try:
                return self.trade.place_order('member', str(uuid.uuid4()), 61, 'buy', 6, 10025)['success']
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.trade.portfolio('member')['holdings'][0]['quantity'], 6)

    def test_failed_flow_write_rolls_back_cash_and_holdings(self):
        order_id = str(uuid.uuid4())
        with self.market.connection(write=True) as db:
            db.execute('INSERT INTO market_flows VALUES (?, ?, ?, ?)', ('order:' + order_id, 61, 1, self.now + 30))
        with self.assertRaises(sqlite3.IntegrityError):
            self.trade.place_order('member', order_id, 61, 'buy', 1, 10025)
        self.assertEqual(self.trade.portfolio('member')['cash'], 100000)
        self.assertEqual(self.trade.portfolio('member')['holdings'], [])
        self.assertEqual(self.trade.history('member'), [])

    def test_buy_and_sell_require_session_and_csrf(self):
        payload = {'orderId': str(uuid.uuid4()), 'clubNum': 61, 'side': 'buy', 'quantity': 1, 'quotedPrice': 10025}
        self.assertEqual(self.client.post('/api/orders', json=payload).status_code, 401)
        with self.client.session_transaction() as session:
            session['user_id'] = 'member'
        self.assertEqual(self.client.post('/api/orders', json=payload).status_code, 403)
        page = self.client.get('/buy').get_data(as_text=True)
        token = re.search(r'data-csrf="([^"]+)"', page).group(1)
        response = self.client.post('/api/orders', json=payload, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
