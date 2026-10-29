"""한 서버의 영속 모의시장. SQLite 트랜잭션으로 워커 간 중복 틱을 방지한다."""

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import random
import secrets
import sqlite3
import time

from app.logics.logic import CANDLE_SECONDS, NEWS_TICKS, TICK_SECONDS, news_return, next_tick
from app.market_catalog import CATEGORIES, CLUBS


class MarketService:
    def __init__(self, database, clock=time.time, max_catchup=240):
        self.database = str(database)
        self.clock = clock
        self.max_catchup = max_catchup

    @contextmanager
    def connection(self, write=False):
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
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

    @staticmethod
    def _save_price(db, club_num, timestamp, price, volume, components):
        db.execute("INSERT INTO market_ticks VALUES (?, ?, ?, ?, ?)",
                   (club_num, timestamp, price, volume, json.dumps(components)))
        bucket = timestamp // CANDLE_SECONDS * CANDLE_SECONDS
        db.execute(
            "INSERT INTO market_candles VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(club_num, timestamp) DO UPDATE SET "
            "high=MAX(high, excluded.high), low=MIN(low, excluded.low), "
            "close=excluded.close, volume=volume+excluded.volume",
            (club_num, bucket, price, price, price, price, volume),
        )

    def _advance(self, db, target):
        row = db.execute("SELECT * FROM market_state WHERE id=1").fetchone()
        last_tick, state = row["last_tick"], json.loads(row["state"])
        prices = {r["club_num"]: r["price"] for r in db.execute("SELECT * FROM market_stocks")}
        end = min(target, last_tick + TICK_SECONDS * self.max_catchup)
        for tick in range(last_tick + TICK_SECONDS, end + 1, TICK_SECONDS):
            effects = {}
            for event in db.execute(
                "SELECT * FROM market_news WHERE effective_at<=? AND effective_at>? ORDER BY event_id",
                (tick, tick - NEWS_TICKS * TICK_SECONDS),
            ):
                age = (tick - event["effective_at"]) // TICK_SECONDS
                effect = news_return(event["impact"], age)
                for club_num in prices:
                    if (event["target_kind"] == "club" and club_num == event["target"]) or (
                        event["target_kind"] == "sector" and club_num // 10 == event["target"]
                    ):
                        effects[club_num] = effects.get(club_num, 0) + effect
            flows, volumes = {}, {}
            for event in db.execute("SELECT * FROM market_flows WHERE effective_at=? ORDER BY event_id", (tick,)):
                club_num, quantity = event["club_num"], event["quantity"]
                flows[club_num] = flows.get(club_num, 0) + quantity
                volumes[club_num] = volumes.get(club_num, 0) + abs(quantity)
            # 비공개 영속 seed + 틱 시각: 재시작/요청 순서가 가격 경로를 바꾸지 않는다.
            rng_seed = hashlib.sha256(f"{row['seed']}:{tick}".encode()).digest()
            prices, state, parts = next_tick(prices, state, effects, flows, random.Random(rng_seed))
            for club_num, price in prices.items():
                db.execute("UPDATE market_stocks SET price=? WHERE club_num=?", (price, club_num))
                self._save_price(db, club_num, tick, price, volumes.get(club_num, 0), parts[club_num])
            last_tick = tick
        db.execute("UPDATE market_state SET last_tick=?, state=? WHERE id=1",
                   (last_tick, json.dumps(state)))
        return last_tick

    def snapshot(self):
        """현재가와 5분봉을 같은 트랜잭션에서 읽는다. 장기 중단은 여러 번 나눠 복구한다."""
        target = int(self.clock()) // TICK_SECONDS * TICK_SECONDS
        with self.connection(write=True) as db:
            timestamp = self._advance(db, target)
            day_start = (timestamp + 9 * 3600) // 86400 * 86400 - 9 * 3600
            stocks = []
            for row in db.execute("SELECT * FROM market_stocks ORDER BY club_num"):
                club_num, price = row["club_num"], row["price"]
                daily = db.execute(
                    "SELECT open FROM market_candles WHERE club_num=? AND timestamp>=? "
                    "ORDER BY timestamp LIMIT 1", (club_num, day_start),
                ).fetchone()
                baseline = daily["open"] if daily else price
                extrema = db.execute(
                    "SELECT MAX(high), MIN(low) FROM market_candles WHERE club_num=? AND timestamp>=?",
                    (club_num, day_start),
                ).fetchone()
                candles = [dict(c) for c in db.execute(
                    "SELECT timestamp, open, high, low, close, volume FROM market_candles "
                    "WHERE club_num=? ORDER BY timestamp DESC LIMIT 60", (club_num,),
                )][::-1]
                stocks.append({
                    "club_num": club_num, "club_name": CLUBS[club_num],
                    "categoryKey": club_num // 10, "category": CATEGORIES[club_num // 10],
                    "price": round(price, 2), "changeRate": (price / baseline - 1) * 100,
                    "changeWon": round(price - baseline, 2),
                    "high": round(extrema[0] or price, 2), "low": round(extrema[1] or price, 2),
                    "candles": candles,
                })
            return {
                "success": True, "timestamp": timestamp,
                "tickSeconds": TICK_SECONDS, "candleSeconds": CANDLE_SECONDS,
                "catchingUp": timestamp < target, "stocks": stocks,
            }

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
