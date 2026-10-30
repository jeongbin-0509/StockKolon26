import json
import math
from contextlib import closing
from pathlib import Path
import random
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app import create_app
from app.logics.logic import (FLOW_LIQUIDITY_SHARES, FLOW_MAX_LOG_RETURN,
                              MARKET_MEMORY, MAX_LOG_RETURN, NEWS_TICKS,
                              SECTOR_MEMORY, TREND_MEMORY, news_return, next_tick)
from app.market_catalog import CLUBS
from app.services.market_service import MarketService


class EngineTests(unittest.TestCase):
    def test_news_has_finite_budget_and_expiry(self):
        for impact in (-0.15, -0.03, 0, 0.03, 0.15):
            effects = [news_return(impact, age) for age in range(NEWS_TICKS)]
            self.assertAlmostEqual(sum(effects), math.log1p(impact))
            self.assertAlmostEqual(effects[0], math.log1p(impact) * 0.6)
            self.assertEqual(news_return(impact, -1), 0)
            self.assertEqual(news_return(impact, NEWS_TICKS), 0)

    def test_news_and_flows_only_affect_target(self):
        prices = {61: 10000, 62: 10000, 31: 10000}
        base, _, _ = next_tick(prices, {}, {}, {}, random.Random(42))
        good, _, _ = next_tick(prices, {}, {61: 0.003}, {}, random.Random(42))
        sold, _, _ = next_tick(prices, {}, {}, {61: -1000}, random.Random(42))
        self.assertGreater(good[61], base[61])
        self.assertLess(sold[61], base[61])
        self.assertEqual(good[62], base[62])
        self.assertEqual(sold[31], base[31])

    def test_same_sector_shares_factor(self):
        _, _, parts = next_tick({61: 10000, 62: 10000, 31: 10000}, {}, {}, {}, random.Random(3))
        self.assertEqual(parts[61]['sector'], parts[62]['sector'])
        self.assertNotEqual(parts[61]['sector'], parts[31]['sector'])
        self.assertNotEqual(parts[61]['individual'], parts[62]['individual'])

    def test_market_sector_and_stock_trends_decay_smoothly(self):
        class NoShock:
            @staticmethod
            def gauss(mean, deviation):
                return mean

            @staticmethod
            def random():
                return 1.0

        state = {'market': 0.001, 'market_volatility': 1.0,
                 'sectors': {'6': 0.001}, 'trends': {'61': 0.001}}
        _, updated, parts = next_tick({61: 10000}, state, {}, {}, NoShock())
        self.assertAlmostEqual(updated['market'], 0.001 * MARKET_MEMORY)
        self.assertAlmostEqual(updated['sectors']['6'], 0.001 * SECTOR_MEMORY)
        self.assertAlmostEqual(updated['trends']['61'], 0.001 * TREND_MEMORY)
        self.assertGreater(parts[61]['individual'], 0)

    def test_random_event_targets_one_stock_and_finishes_without_resetting_price(self):
        prices = {61: 10000, 62: 10000}
        state = {'random_event': {'club': 61, 'remaining': 3, 'per_tick': 0.003}}
        for remaining in (2, 1, 0):
            previous = prices
            prices, state, parts = next_tick(prices, state, {}, {}, random.Random(42))
            self.assertEqual(parts[61]['random_event'], 0.003)
            self.assertEqual(parts[62]['random_event'], 0)
            self.assertGreater(prices[61], previous[61])
            if remaining:
                self.assertEqual(state['random_event']['remaining'], remaining)
            else:
                self.assertIsNone(state['random_event'])
        self.assertGreater(prices[61], 10000)

    def test_random_events_are_reproducible_and_both_directions_occur(self):
        def simulate(seed):
            prices = {61: 10000, 62: 10000, 31: 10000}
            state, rng, events = {}, random.Random(seed), []
            for _ in range(3000):
                prices, state, parts = next_tick(prices, state, {}, {}, rng)
                active = [(club, part['random_event']) for club, part in parts.items() if part['random_event']]
                self.assertLessEqual(len(active), 1)
                if active:
                    events.append(active[0])
            return prices, events
        prices, events = simulate(987)
        self.assertEqual((prices, events), simulate(987))
        self.assertTrue(any(value > 0 for _, value in events))
        self.assertTrue(any(value < 0 for _, value in events))
        self.assertGreater(len({club for club, _ in events}), 1)

    def test_volatility_decays_after_event(self):
        prices, state, _ = next_tick({61: 10000}, {}, {61: 0.04}, {}, random.Random(3))
        start_vol = state['volatility']['61']
        for i in range(80):
            prices, state, _ = next_tick(prices, state, {}, {}, random.Random(i))
        self.assertGreater(start_vol, 1)
        self.assertLess(state['volatility']['61'], 1.001)

    def test_extreme_inputs_are_bounded_and_positive(self):
        for sign in (-1, 1):
            prices, _, parts = next_tick({61: 10000}, {}, {61: sign * 1000}, {61: sign * 10**12}, random.Random(3))
            self.assertGreater(prices[61], 0)
            self.assertLessEqual(abs(parts[61]['flow']), FLOW_MAX_LOG_RETURN)
            self.assertLessEqual(abs(math.log(prices[61] / 10000)), MAX_LOG_RETURN + 1e-12)

    def test_three_days_no_news_simulation(self):
        # 완만한 시장을 의도한 초기 설정의 회귀 검사. 실제 시장 적합성 검증은 아니다.
        for seed in (7, 19, 42):
            prices = {club: 10000 for club in CLUBS}
            state, rng = {}, random.Random(seed)
            up, down, returns = 0, 0, []
            for _ in range(3 * 24 * 120):
                previous = prices
                prices, state, parts = next_tick(prices, state, {}, {}, rng)
                value = math.log(prices[61] / previous[61])
                returns.append(value)
                up += value > 0
                down += value < 0
                self.assertTrue(all(math.isfinite(p) and 1 <= p < 100000 for p in prices.values()))
            self.assertGreater(up, 3000)
            self.assertGreater(down, 3000)
            rms = math.sqrt(sum(r*r for r in returns) / len(returns))
            self.assertLess(rms, 0.001)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'market.sqlite3'
        self.now = 1800000000  # UTC/KST 자정 경계와 독립적인 고정 시각
        self.service = MarketService(self.path, clock=lambda: self.now)
        self.service.initialize()
        with self.service.connection(write=True) as db:
            db.execute("UPDATE market_state SET seed='fixed-test-seed'")

    def stock(self, data, club=61):
        return next(s for s in data['stocks'] if s['club_num'] == club)

    def test_initial_snapshot_has_no_fabricated_past(self):
        data = self.service.snapshot()
        self.assertEqual(len(data['stocks']), 33)
        self.assertEqual(self.stock(data)['price'], 10000)
        self.assertEqual(len(self.stock(data)['candles']), 1)
        self.assertEqual(self.stock(data)['changeRate'], 0)

    def test_five_minute_movers_cover_all_stocks_and_require_full_history(self):
        self.assertEqual(self.service.five_minute_movers(), {'up': None, 'down': None})
        self.now += 300
        movers = self.service.five_minute_movers()
        with self.service.connection() as db:
            rows = list(db.execute('SELECT club_num, timestamp, price FROM market_ticks '
                                   'WHERE timestamp IN (?, ?) ORDER BY club_num, timestamp',
                                   (self.now - 300, self.now)))
        prices = {}
        for row in rows:
            prices.setdefault(row['club_num'], []).append(row['price'])
        changes = {club: (values[-1] / values[0] - 1) * 100 for club, values in prices.items()}
        self.assertEqual(movers['up']['club_num'], max(changes, key=changes.get))
        self.assertEqual(movers['down']['club_num'], min(changes, key=changes.get))
        self.assertEqual(len(movers['up']['prices']), 11)
        self.assertGreater(movers['up']['change'], 0)
        self.assertLess(movers['down']['change'], 0)

    def test_same_tick_and_restart_are_idempotent(self):
        self.now += 300
        data = self.service.snapshot()
        self.assertEqual(data, self.service.snapshot())
        other = MarketService(self.path, clock=lambda: self.now)
        other.initialize()
        self.assertEqual(data, other.snapshot())
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_ticks').fetchone()[0], 33 * 11)
        self.assertAlmostEqual(self.stock(data)['candles'][-1]['close'], self.stock(data)['price'], places=2)

    def test_concurrent_readers_do_not_duplicate_ticks(self):
        self.now += 300
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.service.snapshot(), range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_ticks').fetchone()[0], 33 * 11)

    def test_catchup_and_continuous_produce_same_path(self):
        other_path = Path(self.tmp.name) / 'other.sqlite3'
        with self.service.connection() as db:
            import sqlite3
            with closing(sqlite3.connect(other_path)) as destination:
                db.backup(destination)
        other = MarketService(other_path, clock=lambda: self.now)
        for _ in range(12):
            self.now += 30
            other.snapshot()
        self.assertEqual(self.service.snapshot(), other.snapshot())

    def test_long_catchup_is_bounded_and_eventually_completes(self):
        self.service.max_catchup = 2
        self.now += 150
        first = self.service.snapshot()
        self.assertTrue(first['catchingUp'])
        self.assertEqual(first['timestamp'], self.now - 90)
        self.assertTrue(self.service.snapshot()['catchingUp'])
        self.assertFalse(self.service.snapshot()['catchingUp'])

    def test_events_are_once_only_and_volume_is_gross(self):
        self.assertTrue(self.service.add_news('news-1', 'club', 61, 0.03))
        self.assertFalse(self.service.add_news('news-1', 'club', 61, 0.03))
        self.assertTrue(self.service.record_flow('trade-1', 61, 200))
        self.assertFalse(self.service.record_flow('trade-1', 61, 200))
        self.service.record_flow('trade-2', 61, -100)
        self.now += 30
        data = self.service.snapshot()
        self.assertEqual(self.stock(data)['candles'][-1]['volume'], 300)
        with self.service.connection() as db:
            parts = {r['club_num']: json.loads(r['components']) for r in db.execute(
                'SELECT * FROM market_ticks WHERE timestamp=?', (self.now,))}
        self.assertGreater(parts[61]['news'], 0)
        self.assertEqual(parts[62]['news'], 0)
        self.assertEqual(parts[31]['news'], 0)
        self.assertAlmostEqual(
            parts[61]['flow'], FLOW_MAX_LOG_RETURN * math.tanh(100 / FLOW_LIQUIDITY_SHARES)
        )
        self.now += 30
        self.service.snapshot()
        with self.service.connection() as db:
            part = json.loads(db.execute('SELECT components FROM market_ticks WHERE timestamp=? AND club_num=61', (self.now,)).fetchone()[0])
        self.assertEqual(part['flow'], 0)

    def test_invalid_events_and_conflicting_ids_are_rejected(self):
        for impact in (float('nan'), float('inf'), 1, -1):
            with self.assertRaises(ValueError):
                self.service.add_news('bad', 'club', 61, impact)
        with self.assertRaises(ValueError):
            self.service.add_news('bad', 'sector', 6, 0.02)
        for quantity in (0, 1.5, True, 10**13):
            with self.assertRaises(ValueError):
                self.service.record_flow('bad', 61, quantity)
        self.service.add_news('news', 'club', 61, 0.02)
        with self.assertRaises(ValueError):
            self.service.add_news('news', 'club', 61, -0.02)
        self.service.record_flow('trade', 61, 10)
        with self.assertRaises(ValueError):
            self.service.record_flow('trade', 61, -10)

    def test_scheduled_news_cannot_affect_past_prices(self):
        self.service.add_news('future', 'club', 61, 0.02, timestamp=self.now + 60)
        self.now += 60
        self.service.snapshot()
        with self.service.connection() as db:
            for row in db.execute("SELECT components FROM market_ticks WHERE club_num=61"):
                self.assertEqual(json.loads(row[0]).get('news', 0), 0)
        self.now += 30
        self.service.snapshot()
        with self.service.connection() as db:
            row = db.execute('SELECT components FROM market_ticks WHERE club_num=61 AND timestamp=?', (self.now,)).fetchone()
            self.assertGreater(json.loads(row[0])['news'], 0)

    def test_candle_ohlc_matches_ticks(self):
        self.now += 600
        data = self.service.snapshot()
        with self.service.connection() as db:
            for candle in self.stock(data)['candles']:
                prices = [r[0] for r in db.execute(
                    'SELECT price FROM market_ticks WHERE club_num=61 AND timestamp>=? AND timestamp<? ORDER BY timestamp',
                    (candle['timestamp'], candle['timestamp'] + 300))]
                self.assertEqual((candle['open'], candle['high'], candle['low'], candle['close']),
                                 (prices[0], max(prices), min(prices), prices[-1]))

    def test_korean_midnight_resets_daily_baseline(self):
        self.now = ((self.now + 9*3600) // 86400 + 1) * 86400 - 9*3600 - 30
        while self.service.snapshot()['catchingUp']:
            pass
        self.now += 30
        data = self.service.snapshot()
        self.assertEqual(self.stock(data)['changeRate'], 0)
        self.assertEqual(self.stock(data)['high'], self.stock(data)['low'])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'tests-only',
                               'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.client = self.app.test_client()

    def test_market_requires_login(self):
        self.assertEqual(self.client.get('/api/market').status_code, 401)

    def test_authenticated_quotes_and_buy_page(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'test-user'
        response = self.client.get('/api/market')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(len(response.json['stocks']), 33)
        self.assertNotIn('seed', response.get_data(as_text=True))
        page = self.client.get('/buy')
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="market-status"', page.get_data(as_text=True))
        self.assertEqual(self.client.post('/api/market', json={'price': 1}).status_code, 405)

    def test_database_failure_returns_retryable_error(self):
        import sqlite3
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'test-user'
        with patch.object(self.app.extensions['market'], 'snapshot', side_effect=sqlite3.OperationalError('test')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.client.get('/api/market')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json['success'])

    def test_market_cli_can_run_without_supabase(self):
        result = self.app.test_cli_runner().invoke(args=['market', 'tick'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('timestamp=', result.output)
