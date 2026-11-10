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

    def place(self, side='buy', qty=2, order_id=None):
        return self.trade.place_order('member', order_id or str(uuid.uuid4()), 61, side, qty)

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

    def test_large_orders_respect_funds_holdings_and_idempotency(self):
        with self.market.connection(write=True) as db:
            db.execute('UPDATE users SET cash=? WHERE id=?', (30000000, 'member'))
        order_id = str(uuid.uuid4())
        purchase = self.place(qty=1500, order_id=order_id)
        self.assertTrue(purchase['success'])
        self.assertTrue(self.place(qty=1500, order_id=order_id)['replayed'])
        self.assertEqual(self.trade.portfolio('member')['holdings'][0]['quantity'], 1500)
        with self.assertRaisesRegex(ValueError, '수량'):
            self.place('sell', qty=1501)
        sale = self.place('sell', qty=1500)
        self.assertTrue(sale['success'])
        self.assertEqual(self.trade.portfolio('member')['holdings'], [])

    def test_invalid_or_unaffordable_large_order_is_rejected(self):
        for quantity in (0, -1, 1.5, True, '1500'):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.place(qty=quantity)
        with self.assertRaisesRegex(ValueError, '현금'):
            self.place(qty=1500)

    def test_retry_is_idempotent_and_cannot_change_payload_or_owner(self):
        order_id = str(uuid.uuid4())
        first = self.place(order_id=order_id)
        second = self.place(order_id=order_id)
        self.assertTrue(second['replayed'])
        self.assertEqual(first['order'], second['order'])
        with self.assertRaises(ValueError):
            self.place(qty=3, order_id=order_id)
        with self.assertRaises(ValueError):
            self.trade.place_order('another', order_id, 61, 'buy', 2)
        self.assertEqual(self.trade.portfolio('member')['holdings'][0]['quantity'], 2)

    def test_insufficient_funds_and_holdings_do_not_trade(self):
        with self.assertRaisesRegex(ValueError, '현금'):
            self.place(qty=1000)
        with self.assertRaisesRegex(ValueError, '수량'):
            self.place('sell', qty=1)
        self.assertEqual(self.trade.portfolio('member')['cash'], 100000)
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trade_orders').fetchone()[0], 0)

    def test_market_order_uses_latest_server_price(self):
        with self.market.connection(write=True) as db:
            db.execute('UPDATE market_stocks SET price=? WHERE club_num=?', (12345, 61))
        result = self.place(qty=1)
        self.assertEqual(result['order']['price'], 12376)
        self.assertEqual(result['order']['total'], 12376)

    def test_filled_demand_updates_candle_prices_and_volume_on_next_tick(self):
        import json
        self.place(qty=3)
        self.now += 30
        self.market.snapshot()
        self.place('sell', qty=2)
        self.now += 30
        snapshot = self.market.snapshot()
        stock = next(stock for stock in snapshot['stocks'] if stock['club_num'] == 61)
        candle = stock['candles'][-1]
        with self.market.connection() as db:
            rows = list(db.execute('SELECT price, volume, components FROM market_ticks '
                                   'WHERE club_num=61 AND timestamp>=? AND timestamp<? ORDER BY timestamp',
                                   (candle['timestamp'], candle['timestamp'] + 300)))
        prices = [row['price'] for row in rows]
        self.assertGreater(json.loads(rows[-2]['components'])['flow'], 0)
        self.assertLess(json.loads(rows[-1]['components'])['flow'], 0)
        self.assertEqual(candle['volume'], 5)
        self.assertEqual((candle['open'], candle['high'], candle['low'], candle['close']),
                         (prices[0], max(prices), min(prices), prices[-1]))

    def test_parallel_orders_cannot_overspend(self):
        def attempt(_):
            try:
                return self.trade.place_order('member', str(uuid.uuid4()), 61, 'buy', 6)['success']
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
            self.trade.place_order('member', order_id, 61, 'buy', 1)
        self.assertEqual(self.trade.portfolio('member')['cash'], 100000)
        self.assertEqual(self.trade.portfolio('member')['holdings'], [])
        self.assertEqual(self.trade.history('member'), [])

    def test_buy_and_sell_require_session_and_csrf(self):
        payload = {'orderId': str(uuid.uuid4()), 'clubNum': 61, 'side': 'buy', 'quantity': 1,
                   'quotedPrice': 1}
        self.assertEqual(self.client.post('/api/orders', json=payload).status_code, 401)
        with self.client.session_transaction() as session:
            session['user_id'] = 'member'
        self.assertEqual(self.client.post('/api/orders', json=payload).status_code, 403)
        page = self.client.get('/buy').get_data(as_text=True)
        token = re.search(r'data-csrf="([^"]+)"', page).group(1)
        response = self.client.post('/api/orders', json=payload, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        self.assertNotEqual(response.json['order']['price'], payload['quotedPrice'])
