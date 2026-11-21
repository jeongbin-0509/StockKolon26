import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from app.logics.logic import NEWS_TICKS, TICK_SECONDS, news_return
from app.market_catalog import CLUBS
from app.news_catalog import CATALOG_VERSION, news_presets
from app.services.admin_service import AdminService, AUTO_NEWS_INTERVAL
from app.services.market_service import MarketService


class NewsRotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1800000000  # aligned to a 30-second price tick
        self.market = self.new_market('market')
        self.admin = AdminService(self.market, clock=lambda: self.now)
        self.admin.initialize()

    def new_market(self, name):
        service = MarketService(Path(self.tmp.name) / f'{name}.sqlite3', clock=lambda: self.now)
        service.initialize()
        with service.connection(write=True) as db:
            db.execute("UPDATE market_state SET seed='news-integration-test'")
        return service

    def feed(self):
        return self.admin.articles()[:4]

    def start_full_feed(self):
        self.admin.publish_due_automatic_news()
        self.now += AUTO_NEWS_INTERVAL
        self.admin.publish_due_automatic_news()

    def assert_balanced(self):
        articles = self.feed()
        self.assertEqual(len(articles), 4)
        self.assertEqual(Counter(row['impact'] > 0 for row in articles), {True: 2, False: 2})
        self.assertEqual(len({row['target'] for row in articles}), 4)
        return articles

    def test_rotation_keeps_two_of_each_and_changes_only_the_oldest(self):
        rng = random.Random(26)
        with patch('app.services.admin_service.random.SystemRandom', return_value=rng):
            self.start_full_feed()
            for _ in range(40):
                before = self.assert_balanced()
                self.now += AUTO_NEWS_INTERVAL - 1
                self.assertFalse(self.admin.publish_due_automatic_news())
                self.now += 1
                self.assertTrue(self.admin.publish_due_automatic_news())
                after = self.assert_balanced()
                self.assertEqual([r['id'] for r in after[2:]], [r['id'] for r in before[:2]])
                self.assertEqual(Counter(r['impact'] > 0 for r in after[:2]),
                                 Counter(r['impact'] > 0 for r in before[-2:]))
                for article in after[:2]:
                    self.assertNotIn(article['target'], {r['target'] for r in before})
                self.assertEqual(self.admin.latest_article_id(), after[0]['id'])

    def test_six_candidates_and_initial_order_are_randomized(self):
        seen_variants, seen_orders = set(), set()
        # Independent new games exercise the six choices without depending on probabilistic luck.
        for seed in range(30):
            with self.market.connection(write=True) as db:
                for table in ('news_articles', 'market_news_profiles', 'market_news', 'automatic_news_state'):
                    db.execute(f'DELETE FROM {table}')
            with patch('app.services.admin_service.random.SystemRandom', return_value=random.Random(seed)):
                self.start_full_feed()
            articles = self.assert_balanced()
            seen_orders.add(tuple(r['impact'] > 0 for r in articles))
            by_title = {p['title']: p for p in news_presets()}
            seen_variants.update(by_title[r['title']]['id'].rsplit('-', 1)[1] for r in articles)
        self.assertEqual(seen_variants, set('123456'))
        self.assertGreater(len(seen_orders), 2)

    def test_missed_intervals_do_not_burst_and_restart_preserves_new_articles(self):
        self.admin.publish_due_automatic_news()
        self.now += 6 * 3600
        self.assertTrue(self.admin.publish_due_automatic_news())
        self.assertEqual(len(self.admin.articles()), 4)
        before = self.admin.public_articles()
        self.admin.initialize()
        self.assertEqual(self.admin.public_articles(), before)
        self.assertFalse(self.admin.publish_due_automatic_news())
        self.assert_balanced()

    def test_replacement_removes_legacy_news_once_without_resetting_prices(self):
        self.admin.publish_due_automatic_news()
        with self.market.connection(write=True) as db:
            db.execute("DELETE FROM admin_audit WHERE action='news.catalog.replace'")
            db.execute('UPDATE market_stocks SET price=12345 WHERE club_num=61')
        self.admin.initialize()
        with self.market.connection() as db:
            for table in ('news_articles', 'market_news_profiles', 'market_news', 'automatic_news_state'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT price FROM market_stocks WHERE club_num=61').fetchone()[0], 12345)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM admin_audit WHERE target_id=?',
                                        (CATALOG_VERSION,)).fetchone()[0], 1)
        self.admin.publish_due_automatic_news()
        self.admin.initialize()
        self.assertEqual(len(self.feed()), 2)

    def test_replacement_failure_rolls_back_old_articles_and_events(self):
        self.admin.publish_due_automatic_news()
        before = self.admin.public_articles()
        with self.market.connection(write=True) as db:
            db.execute("DELETE FROM admin_audit WHERE action='news.catalog.replace'")
        with patch.object(self.admin, '_audit', side_effect=RuntimeError('test migration rollback')):
            with self.assertRaises(RuntimeError):
                self.admin.initialize()
        self.assertEqual(self.admin.public_articles(), before)
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM market_news').fetchone()[0], 2)

    def test_active_event_is_excluded_even_when_not_visible(self):
        self.market.add_news('external-active', 'club', 61, -0.01)
        with self.market.connection() as db:
            effective = db.execute("SELECT effective_at FROM market_news WHERE event_id='external-active'").fetchone()[0]
            self.assertIn(61, self.admin._unavailable_news_clubs(db, effective + 3599))
            self.assertNotIn(61, self.admin._unavailable_news_clubs(db, effective + 3600))

    def test_explicit_reset_restarts_two_then_four_without_resetting_assets(self):
        self.start_full_feed()
        with self.market.connection(write=True) as db:
            db.execute('UPDATE market_stocks SET price=12345 WHERE club_num=61')
        self.now += 77
        self.admin.reset_news()
        self.assertEqual(len(self.feed()), 2)
        self.assertEqual(sum(r['impact'] > 0 for r in self.feed()), 1)
        self.now += AUTO_NEWS_INTERVAL - 1
        self.assertFalse(self.admin.publish_due_automatic_news())
        self.now += 1
        self.admin.publish_due_automatic_news()
        self.assert_balanced()
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT price FROM market_stocks WHERE club_num=61').fetchone()[0], 12345)

    def test_reset_failure_rolls_back_news_and_schedule(self):
        self.start_full_feed()
        before = self.admin.public_articles()
        with patch.object(self.admin, '_audit', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.admin.reset_news()
        self.assertEqual(self.admin.public_articles(), before)
        self.assertFalse(self.admin.publish_due_automatic_news())

    def test_small_scheduler_delay_does_not_shift_next_half_hour(self):
        self.admin.publish_due_automatic_news()
        first = self.now
        self.now += AUTO_NEWS_INTERVAL + 17
        self.admin.publish_due_automatic_news()
        with self.market.connection() as db:
            self.assertEqual(db.execute('SELECT next_at FROM automatic_news_state').fetchone()[0],
                             first + 2 * AUTO_NEWS_INTERVAL)

    def test_manual_publication_cannot_break_balance_or_reuse_visible_stock(self):
        owner = self.admin.create_account('news-owner', 'initial-password-123', 'owner')
        self.admin.change_password(owner, 'initial-password-123', 'changed-password-456')
        self.start_full_feed()
        before = self.assert_balanced()
        self.now += 60
        unused = next(club for club in CLUBS if club not in {row['target'] for row in before})
        matching_impact = 0.01 if before[-1]['impact'] > 0 else -0.01
        with self.assertRaises(ValueError):
            self.admin.publish_news('wrong-sign', '제목', '내용', 'club', unused, -matching_impact, owner)
        with self.assertRaises(ValueError):
            self.admin.publish_news('same-stock', '제목', '내용', 'club', before[0]['target'], matching_impact, owner)
        self.admin.publish_news('manual-valid', '제목', '내용', 'club', unused, matching_impact, owner)
        self.assert_balanced()
        self.assertEqual(self.admin.public_articles()[0]['id'], 'manual-valid')

    def test_published_articles_change_only_target_prices_and_expire_at_one_hour(self):
        baseline = self.new_market('baseline')
        self.admin.publish_due_automatic_news()
        articles = self.feed()
        self.assertEqual(len(articles), 2)
        self.assertEqual(sum(r['impact'] > 0 for r in articles), 1)
        targets = {r['target']: r for r in articles}
        catalog = {p['title']: p for p in news_presets()}
        for article in articles:
            preset = catalog[article['title']]
            self.assertEqual((article['target'], article['impact'], article['body']),
                             (preset['club_num'], preset['impact'], preset['body']))
        start = self.now
        for age in (0, 60, 119, 120):
            self.now = start + TICK_SECONDS * (age + 1)
            self.market.snapshot()
            baseline.snapshot()
            with self.market.connection() as db, baseline.connection() as no_news:
                actual = {r['club_num']: r for r in db.execute('SELECT * FROM market_ticks WHERE timestamp=?', (self.now,))}
                control = {r['club_num']: r for r in no_news.execute('SELECT * FROM market_ticks WHERE timestamp=?', (self.now,))}
                for club in CLUBS:
                    part = json.loads(actual[club]['components'])['news']
                    expected = news_return(targets[club]['impact'], age) if club in targets else 0
                    self.assertAlmostEqual(part, expected)
                    if age == 0:
                        if club in targets and targets[club]['impact'] > 0:
                            self.assertGreater(actual[club]['price'], control[club]['price'])
                        elif club in targets:
                            self.assertLess(actual[club]['price'], control[club]['price'])
                        else:
                            self.assertEqual(actual[club]['price'], control[club]['price'])
        self.assertEqual(NEWS_TICKS * TICK_SECONDS, 3600)

    def test_catalog_covers_all_clubs_with_six_each_and_three_difficulties(self):
        presets = news_presets()
        self.assertEqual(len(presets), 396)
        groups = Counter((p['club_num'], p['sentiment'], p['difficulty']) for p in presets)
        self.assertEqual(len(groups), 33 * 2 * 3)
        self.assertEqual(set(groups.values()), {2})
        for p in presets:
            self.assertTrue(1 <= len(p['title']) <= 120)
            self.assertTrue(1 <= len(p['body']) <= 3000)


if __name__ == '__main__':
    unittest.main()
