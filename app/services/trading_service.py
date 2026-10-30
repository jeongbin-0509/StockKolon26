"""모의 체결·잔액·보유 주식을 같은 DB 트랜잭션에서 처리한다."""
import uuid

from app.logics.logic import TICK_SECONDS
from app.market_catalog import CLUBS, CATEGORIES
from app.services.market_service import trade_quotes


class TradingService:
    MAX_QUANTITY = 1000
    MAX_CASH = 2147483647  # public.users.cash는 PostgreSQL integer다.

    def __init__(self, market):
        self.market = market

    def initialize(self):
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS stock_favorites (user_id TEXT NOT NULL, club_num INTEGER NOT NULL, '
                       'PRIMARY KEY (user_id, club_num))')
            db.execute('CREATE TABLE IF NOT EXISTS trade_holdings (user_id TEXT NOT NULL, club_num INTEGER NOT NULL, '
                       'quantity INTEGER NOT NULL CHECK(quantity >= 0), cost_basis INTEGER NOT NULL CHECK(cost_basis >= 0), '
                       'PRIMARY KEY(user_id, club_num))')
            db.execute('CREATE TABLE IF NOT EXISTS trade_orders (order_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, '
                       'club_num INTEGER NOT NULL, side TEXT NOT NULL, quantity INTEGER NOT NULL, '
                       'price INTEGER NOT NULL, total INTEGER NOT NULL, cash_after INTEGER NOT NULL, '
                       'quantity_after INTEGER NOT NULL, created_at INTEGER NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS trade_orders_user ON trade_orders(user_id, created_at)')

    def _users_table(self):
        return 'public.users' if self.market.store.postgres else 'users'

    def place_order(self, user_id, order_id, club_num, side, quantity):
        try:
            if not isinstance(order_id, str) or str(uuid.UUID(order_id)) != order_id:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ValueError('주문 식별자를 확인해주세요.') from None
        if type(club_num) is not int or club_num not in CLUBS or side not in ('buy', 'sell'):
            raise ValueError('종목과 주문 종류를 확인해주세요.')
        if type(quantity) is not int or not 1 <= quantity <= self.MAX_QUANTITY:
            raise ValueError(f'주문 수량은 1~{self.MAX_QUANTITY}주로 입력해주세요.')
        user_id = str(user_id)
        with self.market.connection(write=True) as db:
            previous = db.execute('SELECT * FROM trade_orders WHERE order_id=?', (order_id,)).fetchone()
            if previous:
                if (previous['user_id'], previous['club_num'], previous['side'], previous['quantity']) != (user_id, club_num, side, quantity):
                    raise ValueError('이미 사용된 주문 번호입니다.')
                return {'success': True, 'replayed': True, 'order': self._order(previous)}
            target = int(self.market.clock()) // TICK_SECONDS * TICK_SECONDS
            timestamp = self.market._advance(db, target)
            if timestamp < target:
                return {'success': False, 'message': '시장 가격을 복구 중입니다. 잠시 후 다시 주문해주세요.'}
            stock = db.execute('SELECT price FROM market_stocks WHERE club_num=?', (club_num,)).fetchone()
            if not stock:
                raise ValueError('종목을 찾을 수 없습니다.')
            buy_price, sell_price = trade_quotes(stock['price'])
            price = buy_price if side == 'buy' else sell_price
            # 모든 거래는 DB의 스키마별 쓰기 잠금 안에서 처리한다.
            user = db.execute(f'SELECT cash FROM {self._users_table()} WHERE id=?', (user_id,)).fetchone()
            if not user or user['cash'] is None or user['cash'] < 0:
                raise ValueError('계정의 보유 현금을 확인할 수 없습니다.')
            cash = int(user['cash'])
            holding = db.execute('SELECT quantity, cost_basis FROM trade_holdings WHERE user_id=? AND club_num=?',
                                 (user_id, club_num)).fetchone()
            held = holding['quantity'] if holding else 0
            basis = holding['cost_basis'] if holding else 0
            total = price * quantity
            if total > self.MAX_CASH:
                raise ValueError('주문 금액이 너무 큽니다.')
            if side == 'buy':
                if cash < total:
                    raise ValueError('보유 현금이 부족합니다.')
                cash_after, quantity_after, basis_after = cash - total, held + quantity, basis + total
                if basis_after > self.MAX_CASH:
                    raise ValueError('보유 금액이 허용 범위를 초과합니다.')
            else:
                if held < quantity:
                    raise ValueError('보유 주식 수량이 부족합니다.')
                cash_after, quantity_after = cash + total, held - quantity
                if cash_after > self.MAX_CASH:
                    raise ValueError('보유 현금이 허용 범위를 초과합니다.')
                basis_after = 0 if quantity_after == 0 else basis - (basis * quantity // held)
            changed = db.execute(f'UPDATE {self._users_table()} SET cash=? WHERE id=? AND cash=?',
                                 (cash_after, user_id, cash))
            if changed.rowcount != 1:
                raise ValueError('잔액이 변경되었습니다. 새로고침하고 다시 시도해주세요.')
            db.execute('INSERT INTO trade_holdings VALUES (?, ?, ?, ?) ON CONFLICT(user_id, club_num) '
                       'DO UPDATE SET quantity=excluded.quantity, cost_basis=excluded.cost_basis',
                       (user_id, club_num, quantity_after, basis_after))
            now = int(self.market.clock())
            db.execute('INSERT INTO trade_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (order_id, user_id, club_num, side, quantity, price, total, cash_after, quantity_after, now))
            effective = self.market._event_time(db, None)
            db.execute('INSERT INTO market_flows VALUES (?, ?, ?, ?)',
                       ('order:' + order_id, club_num, quantity if side == 'buy' else -quantity, effective))
            row = db.execute('SELECT * FROM trade_orders WHERE order_id=?', (order_id,)).fetchone()
            return {'success': True, 'replayed': False, 'order': self._order(row)}

    @staticmethod
    def _order(row):
        return {'id': row['order_id'], 'club_num': row['club_num'], 'club_name': CLUBS[row['club_num']],
                'side': row['side'], 'quantity': row['quantity'], 'price': row['price'], 'total': row['total'],
                'cash_after': row['cash_after'], 'quantity_after': row['quantity_after'], 'timestamp': row['created_at']}

    def portfolio(self, user_id, cash=None):
        with self.market.connection() as db:
            if cash is None:
                user_key = 'CAST(u.id AS TEXT)' if self.market.store.postgres else 'u.id'
                rows = list(db.execute(f'SELECT u.cash,h.club_num,h.quantity,h.cost_basis,s.price FROM {self._users_table()} u '
                                       f'LEFT JOIN trade_holdings h ON h.user_id={user_key} AND h.quantity>0 '
                                       'LEFT JOIN market_stocks s ON s.club_num=h.club_num WHERE u.id=? ORDER BY h.club_num',
                                       (str(user_id),)))
                if not rows or rows[0]['cash'] is None:
                    raise ValueError('계정의 보유 현금을 확인할 수 없습니다.')
                cash = rows[0]['cash']
                rows = [row for row in rows if row['club_num'] is not None and row['price'] is not None]
            else:
                rows = list(db.execute('SELECT h.club_num,h.quantity,h.cost_basis,s.price FROM trade_holdings h '
                                       'JOIN market_stocks s ON s.club_num=h.club_num WHERE h.user_id=? AND h.quantity>0 '
                                       'ORDER BY h.club_num', (str(user_id),)))
        holdings = []
        for row in rows:
            number, quantity, basis = row['club_num'], row['quantity'], row['cost_basis']
            price = trade_quotes(row['price'])[1]
            value = price * quantity
            holdings.append({'club_num': number, 'name': CLUBS[number], 'category': CATEGORIES[number // 10],
                             'quantity': quantity, 'price': price, 'value': value, 'cost': basis,
                             'profit': value - basis, 'rate': (value / basis - 1) * 100 if basis else 0})
        cost = sum(item['cost'] for item in holdings)
        value = sum(item['value'] for item in holdings)
        return {'cash': int(cash), 'holdings': holdings, 'cost': cost, 'value': value,
                'total': int(cash) + value, 'profit': value - cost}

    def history(self, user_id):
        with self.market.connection() as db:
            rows = db.execute('SELECT * FROM trade_orders WHERE user_id=? ORDER BY created_at DESC, order_id DESC LIMIT 30',
                              (str(user_id),)).fetchall()
        return [self._order(row) for row in rows]
