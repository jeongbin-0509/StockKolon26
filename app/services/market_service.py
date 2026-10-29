"""영속 모의시장. DB 트랜잭션으로 워커·배포 재시작 간 중복 틱을 방지한다."""

import hashlib
import json
import math
import random
import secrets
import time
from decimal import Decimal, ROUND_HALF_UP

from app.logics.logic import CANDLE_SECONDS, NEWS_TICKS, TICK_SECONDS, news_return, next_tick
from app.market_catalog import CATEGORIES, CLUBS
from app.services.database import Database


def trade_quotes(price):
    mid = Decimal(str(price))
    return tuple(max(1, int((mid * factor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
                 for factor in (Decimal('1.0025'), Decimal('0.9975')))


class MarketService:
    def __init__(self, database, clock=time.time, max_catchup=240, schema='stockolon_private'):
        self.database = str(database)
        self.clock = clock
        self.max_catchup = max_catchup
        self.store = Database(database, schema=schema)

    def connection(self, write=False):
        return self.store.connection(write=write)

    def initialize(self):
        self.store.initialize()
        with self.connection(write=True) as db:
            # DDL과 최초 가격도 같은 트랜잭션에서 생성한다.
            for statement in (
                "CREATE TABLE IF NOT EXISTS market_state (id INTEGER PRIMARY KEY CHECK(id=1), "
                "last_tick INTEGER NOT NULL, seed TEXT NOT NULL, state TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS market_stocks (club_num INTEGER PRIMARY KEY, "
                "price REAL NOT NULL CHECK(price >= 1))",
                "CREATE TABLE IF NOT EXISTS market_ticks (club_num INTEGER NOT NULL, "
                "timestamp INTEGER NOT NULL, price REAL NOT NULL, volume INTEGER NOT NULL, "
                "components TEXT NOT NULL, PRIMARY KEY(timestamp, club_num))",
                "CREATE TABLE IF NOT EXISTS market_candles (club_num INTEGER NOT NULL, "
                "timestamp INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, "
                "low REAL NOT NULL, close REAL NOT NULL, volume INTEGER NOT NULL, "
                "PRIMARY KEY(club_num, timestamp))",
                "CREATE TABLE IF NOT EXISTS market_news (event_id TEXT PRIMARY KEY, "
                "target_kind TEXT NOT NULL, target INTEGER NOT NULL, impact REAL NOT NULL, "
                "effective_at INTEGER NOT NULL)",
                "CREATE TABLE IF NOT EXISTS market_flows (event_id TEXT PRIMARY KEY, "
                "club_num INTEGER NOT NULL, quantity INTEGER NOT NULL, effective_at INTEGER NOT NULL)",
                "CREATE INDEX IF NOT EXISTS market_news_time ON market_news(effective_at)",
                "CREATE INDEX IF NOT EXISTS market_flows_time ON market_flows(effective_at)",
                "CREATE INDEX IF NOT EXISTS market_candles_time ON market_candles(timestamp)",
            ):
                db.execute(statement)
            if db.execute("SELECT 1 FROM market_state").fetchone():
                return
            now = int(self.clock()) // TICK_SECONDS * TICK_SECONDS
            db.execute("INSERT INTO market_state VALUES (1, ?, ?, ?)",
                       (now, secrets.token_hex(32), "{}"))
            for club_num in CLUBS:
                db.execute("INSERT INTO market_stocks VALUES (?, ?)", (club_num, 10000.0))
                self._save_price(db, club_num, now, 10000.0, 0, {})

    @classmethod
    def _save_price(cls, db, club_num, timestamp, price, volume, components):
        cls._save_rows(db, [(club_num, timestamp, price, volume, json.dumps(components))])

    @staticmethod
    def _save_rows(db, rows):
        if not rows:
            return
        db.executemany("INSERT INTO market_ticks VALUES (?, ?, ?, ?, ?)", rows)
        db.executemany(
            "INSERT INTO market_candles VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(club_num, timestamp) DO UPDATE SET "
            "high=CASE WHEN market_candles.high>excluded.high THEN market_candles.high ELSE excluded.high END, "
            "low=CASE WHEN market_candles.low<excluded.low THEN market_candles.low ELSE excluded.low END, "
            "close=excluded.close, volume=market_candles.volume+excluded.volume",
            [(club, stamp // CANDLE_SECONDS * CANDLE_SECONDS, price, price, price, price, volume)
             for club, stamp, price, volume, _ in rows],
        )

    def _advance(self, db, target):
        row = db.execute("SELECT * FROM market_state WHERE id=1").fetchone()
        last_tick, state = row["last_tick"], json.loads(row["state"])
        if target <= last_tick:
            return last_tick
        prices = {r["club_num"]: r["price"] for r in db.execute("SELECT * FROM market_stocks")}
        end = min(target, last_tick + TICK_SECONDS * self.max_catchup)
        events = list(db.execute(
            "SELECT * FROM market_news WHERE effective_at<=? AND effective_at>? ORDER BY event_id",
            (end, last_tick - NEWS_TICKS * TICK_SECONDS),
        ))
        flows_by_tick = {}
        for event in db.execute("SELECT * FROM market_flows WHERE effective_at>? AND effective_at<=? ORDER BY event_id", (last_tick, end)):
            flows_by_tick.setdefault(event["effective_at"], []).append(event)
        rows = []
        for tick in range(last_tick + TICK_SECONDS, end + 1, TICK_SECONDS):
            effects = {}
            for event in events:
                age = (tick - event["effective_at"]) // TICK_SECONDS
                effect = news_return(event["impact"], age)
                if not effect:
                    continue
                for club_num in prices:
                    if (event["target_kind"] == "club" and club_num == event["target"]) or (
                        event["target_kind"] == "sector" and club_num // 10 == event["target"]
                    ):
                        effects[club_num] = effects.get(club_num, 0) + effect
            flows, volumes = {}, {}
            for event in flows_by_tick.get(tick, []):
                club_num, quantity = event["club_num"], event["quantity"]
                flows[club_num] = flows.get(club_num, 0) + quantity
                volumes[club_num] = volumes.get(club_num, 0) + abs(quantity)
            rng_seed = hashlib.sha256(f"{row['seed']}:{tick}".encode()).digest()
            prices, state, parts = next_tick(prices, state, effects, flows, random.Random(rng_seed))
            rows.extend((club_num, tick, price, volumes.get(club_num, 0), json.dumps(parts[club_num]))
                        for club_num, price in prices.items())
        self._save_rows(db, rows)
        db.executemany("UPDATE market_stocks SET price=? WHERE club_num=?", [(price, club) for club, price in prices.items()])
        db.execute("UPDATE market_state SET last_tick=?, state=? WHERE id=1", (end, json.dumps(state)))
        if end // 3600 != last_tick // 3600:
            # 무료 DB 용량에 맞춰 틱 6시간, 5분봉 7일을 유지한다. 현재가/사건은 삭제하지 않는다.
            db.execute("DELETE FROM market_ticks WHERE timestamp<?", (end - 6 * 3600,))
            db.execute("DELETE FROM market_candles WHERE timestamp<?", (end - 7 * 86400,))
        return end

    def snapshot(self):
        """같은 트랜잭션의 현재가·일간 통계·최근 5분봉을 일괄 조회한다."""
        target = int(self.clock()) // TICK_SECONDS * TICK_SECONDS
        with self.connection(write=True) as db:
            timestamp = self._advance(db, target)
            day_start = (timestamp + 9 * 3600) // 86400 * 86400 - 9 * 3600
            daily = {r["club_num"]: r for r in db.execute(
                "SELECT club_num, MAX(CASE WHEN position=1 THEN open END) AS day_open, "
                "MAX(high) AS day_high, MIN(low) AS day_low FROM "
                "(SELECT club_num, open, high, low, ROW_NUMBER() OVER "
                "(PARTITION BY club_num ORDER BY timestamp) AS position FROM market_candles WHERE timestamp>=?) d "
                "GROUP BY club_num", (day_start,),
            )}
            history = {}
            first_bucket = timestamp // CANDLE_SECONDS * CANDLE_SECONDS - 59 * CANDLE_SECONDS
            for candle in db.execute(
                "SELECT club_num, timestamp, open, high, low, close, volume FROM market_candles "
                "WHERE timestamp>=? ORDER BY club_num, timestamp", (first_bucket,),
            ):
                history.setdefault(candle["club_num"], []).append({k: candle[k] for k in ("timestamp", "open", "high", "low", "close", "volume")})
            stocks = []
            for row in db.execute("SELECT * FROM market_stocks ORDER BY club_num"):
                club_num, price = row["club_num"], row["price"]
                stats = daily.get(club_num, {})
                baseline = stats["day_open"] if stats else price
                stocks.append({
                    "club_num": club_num, "club_name": CLUBS[club_num],
                    "categoryKey": club_num // 10, "category": CATEGORIES[club_num // 10],
                    "price": round(price, 2), "changeRate": (price / baseline - 1) * 100,
                    "buyPrice": trade_quotes(price)[0], "sellPrice": trade_quotes(price)[1],
                    "changeWon": round(price - baseline, 2),
                    "high": round(stats["day_high"] if stats else price, 2),
                    "low": round(stats["day_low"] if stats else price, 2),
                    "candles": history.get(club_num, []),
                })
            return {
                "success": True, "timestamp": timestamp,
                "tickSeconds": TICK_SECONDS, "candleSeconds": CANDLE_SECONDS,
                "catchingUp": timestamp < target, "stocks": stocks,
            }

    def five_minute_movers(self):
        """전체 종목의 정확히 5분 전 가격과 현재 가격을 비교한다."""
        target = int(self.clock()) // TICK_SECONDS * TICK_SECONDS
        with self.connection(write=True) as db:
            timestamp = self._advance(db, target)
            points = {}
            for row in db.execute(
                "SELECT club_num, timestamp, price FROM market_ticks "
                "WHERE timestamp>=? AND timestamp<=? ORDER BY club_num, timestamp",
                (timestamp - 300, timestamp),
            ):
                points.setdefault(row['club_num'], []).append(row)
            movers = []
            for club, series in points.items():
                if series[0]['timestamp'] != timestamp - 300 or series[-1]['timestamp'] != timestamp:
                    continue
                first, last = series[0]['price'], series[-1]['price']
                movers.append({'club_num': club, 'name': CLUBS[club],
                               'category': CATEGORIES[club // 10], 'price': last,
                               'change': (last / first - 1) * 100,
                               'prices': [point['price'] for point in series],
                               'timestamps': [point['timestamp'] for point in series]})
            rising = [stock for stock in movers if stock['change'] > 0]
            falling = [stock for stock in movers if stock['change'] < 0]
            return {'up': max(rising, key=lambda stock: stock['change'], default=None),
                    'down': min(falling, key=lambda stock: stock['change'], default=None)}

    def _event_time(self, db, timestamp):
        now = self.clock()
        stamp = now if timestamp is None else timestamp
        if not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp < now:
            raise ValueError("이벤트 시각은 현재 또는 미래여야 합니다.")
        last = db.execute("SELECT last_tick FROM market_state WHERE id=1").fetchone()[0]
        return max(last + TICK_SECONDS, int(stamp) // TICK_SECONDS * TICK_SECONDS + TICK_SECONDS)

    @staticmethod
    def _event_id(event_id):
        if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 200:
            raise ValueError("안정적인 event_id가 필요합니다.")

    def add_news(self, event_id, target_kind, target, impact, timestamp=None):
        """뉴스 발행 서버에서 호출하는 내부 인터페이스."""
        with self.connection(write=True) as db:
            return self._add_news(db, event_id, target_kind, target, impact, timestamp)

    def _add_news(self, db, event_id, target_kind, target, impact, timestamp=None):
        """기사·감사 기록과 가격 이벤트를 하나의 트랜잭션에 저장할 수 있게 분리한다."""
        self._event_id(event_id)
        valid = CLUBS if target_kind == "club" else CATEGORIES if target_kind == "sector" else {}
        if type(target) is not int or target not in valid or type(impact) not in (int, float) or not math.isfinite(impact) or not -0.15 <= impact <= 0.15:
            raise ValueError("뉴스 대상과 영향(-0.15~0.15)을 확인하세요.")
        previous = db.execute("SELECT * FROM market_news WHERE event_id=?", (event_id,)).fetchone()
        if previous:
            if (previous["target_kind"], previous["target"], previous["impact"]) != (target_kind, target, impact):
                raise ValueError("이미 사용된 event_id의 내용을 바꿀 수 없습니다.")
            return False
        effective = self._event_time(db, timestamp)
        db.execute("INSERT INTO market_news VALUES (?, ?, ?, ?, ?)",
                   (event_id, target_kind, target, impact, effective))
        return True

    def record_flow(self, event_id, club_num, signed_quantity, timestamp=None):
        """향후 확정 체결 ID로만 호출. 주문 제출/취소는 가격에 반영하지 않는다.

        현 버전은 거래를 실행하지 않는다. 실제 거래 구현 시 자산 저장과 이 입력의
        원자성은 outbox 등으로 보장해야 한다. 이 함수는 자산을 차감하지 않는다.
        """
        self._event_id(event_id)
        if club_num not in CLUBS or type(signed_quantity) is not int or not 0 < abs(signed_quantity) <= 10**12:
            raise ValueError("유효한 종목과 0이 아닌 정수 체결 수량이 필요합니다.")
        with self.connection(write=True) as db:
            previous = db.execute("SELECT * FROM market_flows WHERE event_id=?", (event_id,)).fetchone()
            if previous:
                if (previous["club_num"], previous["quantity"]) != (club_num, signed_quantity):
                    raise ValueError("이미 사용된 체결 ID의 내용을 바꿀 수 없습니다.")
                return False
            effective = self._event_time(db, timestamp)
            db.execute("INSERT INTO market_flows VALUES (?, ?, ?, ?)",
                       (event_id, club_num, signed_quantity, effective))
        return True
