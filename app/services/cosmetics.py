"""Permanent achievements, evaluated inside the same transaction as prices and trades."""
import json

from app.logics.logic import NEWS_TICKS, TICK_SECONDS, news_return
from app.services.market_service import trade_quotes
from app.services.ranking_service import profile_key

DAY = 86400
CATALOG = [
    dict(id='prologue', name='PROLOGUE', frame='ORIGIN', tier='ESSENTIAL', condition='모든 사용자에게 지급', goal=1),
    dict(id='prime', name='PRIME', frame='PLATINUM', tier='PRESTIGE', condition='전교 30위 이내 연속 24시간 유지', goal=DAY),
    dict(id='apex', name='APEX', frame='PRISM', tier='ELITE', condition='전교 10위 이내 연속 24시간 유지', goal=DAY),
    dict(id='sovereign', name='SOVEREIGN', frame='REGALIA', tier='LEGENDARY', condition='전교 1위 연속 24시간 유지', goal=DAY),
    dict(id='earlybird', name='일찍 일어나는 새', frame='AURORA', tier='RARE', condition='한국 시간 새벽 3시대에 접속', goal=1),
    dict(id='tracker', name='추적자', frame='VELOCITY', tier='ELITE', condition='24시간 이내 전교 순위 200계단 상승', goal=200),
    dict(id='oracle', name='예언자', frame='ORACLE', tier='PRESTIGE', condition='5번 연속 매도에서 실현 수익 달성', goal=5),
    dict(id='anchor', name='ANCHOR', frame='TIDAL', tier='RARE', condition='한 종목을 연속 3일 이상 보유', goal=3 * DAY),
    dict(id='slayer', name='SLAYER', frame='INFERNO', tier='ELITE', condition='악재 뉴스가 영향을 주는 동안 해당 종목을 수익 매도', goal=1),
]
BY_ID = {item['id']: item for item in CATALOG}


def fresh(now):
    return dict(created=now, asof=now, owned={'prologue': now}, starts={}, history=[], positions={},
                streak=0, rank=None, signature='prologue', frame='prologue')


def decoration(state=None):
    state = state or fresh(0)
    signature, frame = state.get('signature'), state.get('frame')
    return dict(signature=signature, name=BY_ID[signature]['name'] if signature in BY_ID else '', frame=frame)


class RankBatch:
    """Read the roster once; replay every price tick in memory, then persist once."""
    def __init__(self, service, db):
        self.service = service
        self.states = {r['user_id']: json.loads(r['state']) for r in db.execute('SELECT user_id,state FROM cosmetic_profiles')}
        self.original = {key: json.dumps(value, sort_keys=True) for key, value in self.states.items()}
        self.players = {}
        if not service.market.store.postgres and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
            return
        table = 'public.users' if service.market.store.postgres else 'users'
        self.players = {str(r['id']): dict(cash=int(r['cash']), holdings={})
                        for r in db.execute(f'SELECT id,cash FROM {table} WHERE cash IS NOT NULL AND cash>=0')}
        for row in db.execute('SELECT user_id,club_num,quantity FROM trade_holdings WHERE quantity>0'):
            if row['user_id'] in self.players:
                self.players[row['user_id']]['holdings'][str(row['club_num'])] = row['quantity']
        # A previously unseen account must not be backdated through offline catch-up.
        now = int(service.market.clock())
        for key in self.players:
            self.states.setdefault(key, fresh(now))

    def observe(self, prices, now):
        bids = {str(club): trade_quotes(price)[1] for club, price in prices.items()}
        assets = sorted(((p['cash'] + sum(bids.get(c, 0) * q for c, q in p['holdings'].items()), key)
                         for key, p in self.players.items() if self.states[key]['created'] <= now), reverse=True)
        previous, rank = None, 0
        for index, (value, key) in enumerate(assets, 1):
            if value != previous:
                rank = index
            previous = value
            state = self.states[key]
            if now < state['asof']:
                continue
            state['asof'] = now
            state['rank'] = rank
            for signature, threshold in (('prime', 30), ('apex', 10), ('sovereign', 1)):
                if rank > threshold:
                    state['starts'].pop(signature, None)
                else:
                    start = state['starts'].setdefault(signature, now)
                    if now - start >= DAY:
                        state['owned'].setdefault(signature, now)
            history = state['history']
            # Monotone maximum queue: retain only ranks that can still be a 24h maximum.
            while history and history[0][0] < now - DAY:
                history.pop(0)
            best_jump = history[0][1] - rank if history else 0
            if best_jump >= 200:
                state['owned'].setdefault('tracker', now)
            state['jump'] = max(0, best_jump)
            while history and history[-1][1] <= rank:
                history.pop()
            history.append([now, rank])
            held = self.players[key]['holdings']
            state['positions'] = {club: state['positions'].get(club, now) for club in held}
            if any(now - start >= 3 * DAY for start in state['positions'].values()):
                state['owned'].setdefault('anchor', now)

    def save(self, db):
        rows = []
        for key, state in self.states.items():
            encoded = json.dumps(state, sort_keys=True)
            if self.original.get(key) != encoded:
                rows.append((key, profile_key(key), encoded))
        if rows:
            db.executemany('INSERT INTO cosmetic_profiles VALUES (?,?,?) ON CONFLICT(user_id) '
                           'DO UPDATE SET state=excluded.state', rows)


class Cosmetics:
    def __init__(self, market):
        self.market = market

    def initialize(self):
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS cosmetic_profiles (user_id TEXT PRIMARY KEY, '
                       'profile_key TEXT NOT NULL UNIQUE, state TEXT NOT NULL)')
            if self.market.store.postgres:
                db.execute('ALTER TABLE cosmetic_profiles ENABLE ROW LEVEL SECURITY')
                db.execute('REVOKE ALL ON cosmetic_profiles FROM PUBLIC')
                for role in ('anon', 'authenticated'):
                    if db.execute('SELECT 1 FROM pg_roles WHERE rolname=?', (role,)).fetchone():
                        db.execute(f'REVOKE ALL ON cosmetic_profiles FROM {role}')

    def batch(self, db):
        return RankBatch(self, db)

    def observe_now(self, db, now):
        batch = self.batch(db)
        batch.observe({r['club_num']: r['price'] for r in db.execute('SELECT * FROM market_stocks')}, now)
        batch.save(db)

    def read(self, db, user_id):
        row = db.execute('SELECT state FROM cosmetic_profiles WHERE user_id=?', (str(user_id),)).fetchone()
        return json.loads(row['state']) if row else fresh(int(self.market.clock()))

    def save(self, db, user_id, state):
        db.execute('INSERT INTO cosmetic_profiles VALUES (?,?,?) ON CONFLICT(user_id) '
                   'DO UPDATE SET state=excluded.state', (str(user_id), profile_key(user_id), json.dumps(state)))

    def after_trade(self, db, user_id, club, side, profit, now, tick):
        state = self.read(db, user_id)
        if side == 'sell':
            state['streak'] = state['streak'] + 1 if profit > 0 else 0
            if state['streak'] >= 5:
                state['owned'].setdefault('oracle', now)
            if profit > 0:
                events = db.execute('SELECT target_kind,target,impact,effective_at FROM market_news '
                                    'WHERE impact<0 AND effective_at<=? AND effective_at>?',
                                    (tick, tick - NEWS_TICKS * TICK_SECONDS))
                if any(((r['target_kind'] == 'club' and r['target'] == club) or
                        (r['target_kind'] == 'sector' and r['target'] == club // 10)) and
                       news_return(r['impact'], (tick - r['effective_at']) // TICK_SECONDS) < 0 for r in events):
                    state['owned'].setdefault('slayer', now)
        self.save(db, user_id, state)
        self.observe_now(db, now)

    def visit(self, user_id):
        now = int(self.market.clock())
        if (now + 9 * 3600) // 3600 % 24 != 3:
            return
        with self.market.connection(write=True) as db:
            state = self.read(db, user_id)
            if 'earlybird' not in state['owned']:
                state['owned']['earlybird'] = now
                self.save(db, user_id, state)

    def collection(self, user_id):
        now = int(self.market.clock())
        with self.market.connection(write=True) as db:
            tick = self.market._advance(db, now // TICK_SECONDS * TICK_SECONDS)
            if tick >= now // TICK_SECONDS * TICK_SECONDS:
                self.observe_now(db, now)
            state = self.read(db, user_id)
            self.save(db, user_id, state)
        progress = {'prologue': 1, 'earlybird': 0, 'tracker': state.get('jump', 0),
                    'oracle': state['streak'], 'anchor': max((state['asof'] - t for t in state['positions'].values()), default=0), 'slayer': 0}
        for key in ('prime', 'apex', 'sovereign'):
            progress[key] = state['asof'] - state['starts'][key] if key in state['starts'] else 0
        return dict(equipped=decoration(state), catching_up=tick < now // TICK_SECONDS * TICK_SECONDS,
                    items=[dict(item, unlocked=item['id'] in state['owned'], earned_at=state['owned'].get(item['id']),
                                progress=min(item['goal'], progress[item['id']])) for item in CATALOG])

    def equip(self, user_id, signature, frame):
        with self.market.connection(write=True) as db:
            state = self.read(db, user_id)
            for value in (signature, frame):
                if value is not None and (not isinstance(value, str) or value not in BY_ID or value not in state['owned']):
                    raise ValueError('획득한 시그니처와 프레임만 장착할 수 있습니다.')
            state.update(signature=signature, frame=frame)
            self.save(db, user_id, state)
        return decoration(state)

    def public(self, keys):
        keys = list(set(keys))
        if not keys:
            return {}
        with self.market.connection() as db:
            rows = db.execute('SELECT profile_key,state FROM cosmetic_profiles WHERE profile_key IN ('
                              + ','.join('?' for _ in keys) + ')', keys)
            result = {r['profile_key']: decoration(json.loads(r['state'])) for r in rows}
        return {key: result.get(key, decoration()) for key in keys}
