"""회원의 실제 평가 자산을 기준으로 개인 순위를 계산한다."""
import re

from app.logics.logic import TICK_SECONDS
from app.services.market_service import trade_quotes


class RankingService:
    def __init__(self, market):
        self.market = market

    def rankings(self, user_id, scope):
        if scope not in ('school', 'class', 'club'):
            raise ValueError('랭킹 범위를 확인해주세요.')
        users = 'public.users' if self.market.store.postgres else 'users'
        clubs = 'public.clubs' if self.market.store.postgres else 'clubs'
        with self.market.connection(write=True) as db:
            target = int(self.market.clock()) // TICK_SECONDS * TICK_SECONDS
            timestamp = self.market._advance(db, target)
            rows = db.execute(
                f'SELECT u.id,u.name,u.usernum,u.club_id,u.cash,c.name AS club_name,'
                f'h.quantity,h.cost_basis,s.price FROM {users} u '
                f'LEFT JOIN {clubs} c ON c.id=u.club_id '
                'LEFT JOIN trade_holdings h ON h.user_id=CAST(u.id AS TEXT) AND h.quantity>0 '
                'LEFT JOIN market_stocks s ON s.club_num=h.club_num'
            ).fetchall()
        members = {}
        for row in rows:
            key = str(row['id'])
            if row['cash'] is None or row['cash'] < 0:
                continue
            if key not in members:
                members[key] = {'id': key, 'name': row['name'], 'usernum': str(row['usernum'] or ''),
                                'club_id': str(row['club_id']) if row['club_id'] else None,
                                'club_name': row['club_name'], 'assets': int(row['cash']), 'value': 0, 'cost': 0}
            if row['quantity'] and row['price'] is not None:
                value = trade_quotes(row['price'])[1] * row['quantity']
                members[key]['assets'] += value
                members[key]['value'] += value
                members[key]['cost'] += row['cost_basis']
        me = members.get(str(user_id))
        if not me:
            raise ValueError('계정의 자산 정보를 확인할 수 없습니다.')
        if scope == 'class':
            if not re.fullmatch(r'[0-9]{5}', me['usernum']):
                return {'available': False, 'message': '학번을 확인할 수 없어 학급 랭킹을 보여드릴 수 없습니다.'}
            selected = [u for u in members.values() if re.fullmatch(r'[0-9]{5}', u['usernum']) and u['usernum'][:3] == me['usernum'][:3]]
        elif scope == 'club':
            if not me['club_id']:
                return {'available': False, 'message': '소속 동아리를 선택한 회원만 동아리 랭킹을 볼 수 있습니다.'}
            selected = [u for u in members.values() if u['club_id'] == me['club_id']]
        else:
            selected = list(members.values())
        selected.sort(key=lambda u: (-u['assets'], u['id']))
        result = []
        my_rank = None
        previous_assets = None
        rank = 0
        for position, member in enumerate(selected, 1):
            if member['assets'] != previous_assets:
                rank = position
                previous_assets = member['assets']
            item = {'rank': rank, 'name': member['name'], 'club_name': member['club_name'],
                    'assets': member['assets'], 'rate': (member['value'] / member['cost'] - 1) * 100 if member['cost'] else None,
                    'is_me': member['id'] == str(user_id)}
            if item['is_me']:
                my_rank = item
            if position <= 100:
                result.append(item)
        return {'available': True, 'members': result, 'me': my_rank, 'count': len(selected),
                'timestamp': timestamp, 'catching_up': timestamp < target}
