"""일반 회원과 분리된 관리자 인증·권한·발행 기록. 시장 DB와 동일한 영속 파일을 사용한다."""

import hashlib
import json
import math
import random
import re
import secrets
import time

from werkzeug.security import check_password_hash, generate_password_hash

from app.market_catalog import CATEGORIES, CLUBS
from app.news_catalog import news_presets

PERMISSIONS = {
    'owner': {'market:view', 'news:publish', 'audit:view', 'admins:manage'},
    'editor': {'market:view', 'news:publish', 'audit:view'},
}
ROLE_NAMES = {'owner': '최고관리자', 'editor': '운영관리자'}
SESSION_SECONDS = 8 * 3600
AUTO_NEWS_INTERVAL = 30 * 60


class AdminService:
    def __init__(self, market, clock=time.time):
        self.market = market
        self.clock = clock
        self._dummy_hash = generate_password_hash(secrets.token_urlsafe(32))

    def initialize(self):
        with self.market.connection(write=True) as db:
            for sql in (
                'CREATE TABLE IF NOT EXISTS admin_accounts (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, '
                "password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner','editor')), "
                'active INTEGER NOT NULL DEFAULT 1, must_change_password INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS admin_sessions (token_hash TEXT PRIMARY KEY, admin_id TEXT NOT NULL, expires_at INTEGER NOT NULL)',
                'CREATE INDEX IF NOT EXISTS admin_session_account ON admin_sessions(admin_id)',
                'CREATE TABLE IF NOT EXISTS admin_login_limits (subject TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reset_at INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS admin_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT, '
                'action TEXT NOT NULL, target_id TEXT NOT NULL, detail TEXT NOT NULL, created_at INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS news_articles (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, '
                'target_kind TEXT NOT NULL, target INTEGER NOT NULL, impact REAL NOT NULL, author_id TEXT NOT NULL, published_at INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS automatic_news_state (id INTEGER PRIMARY KEY CHECK(id=1), '
                'next_at INTEGER NOT NULL, published_count INTEGER NOT NULL)',
            ):
                db.execute(sql)

    @staticmethod
    def _audit(db, actor_id, action, target_id, detail, timestamp):
        db.execute('INSERT INTO admin_audit(actor_id, action, target_id, detail, created_at) VALUES (?, ?, ?, ?, ?)',
                   (actor_id, action, target_id, json.dumps(detail, ensure_ascii=False), timestamp))

    @staticmethod
    def _require(db, actor_id, permission):
        actor = db.execute('SELECT * FROM admin_accounts WHERE id=? AND active=1', (actor_id,)).fetchone()
        if not actor or permission not in PERMISSIONS[actor['role']] or actor['must_change_password']:
            raise PermissionError('이 작업을 수행할 관리자 권한이 없습니다.')
        return actor

    @staticmethod
    def validate_password(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 128 or not password.strip():
            raise ValueError('비밀번호는 12~128자로 입력하세요.')

    def create_account(self, username, password, role='editor', actor_id=None):
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}', username):
            raise ValueError('아이디는 영문 소문자·숫자로 시작하는 3~32자의 영문·숫자·._-만 가능합니다.')
        if role not in PERMISSIONS:
            raise ValueError('관리자 권한을 확인하세요.')
        self.validate_password(password)
        hashed = generate_password_hash(password)
        with self.market.connection(write=True) as db:
            if actor_id is not None:
                self._require(db, actor_id, 'admins:manage')
            if db.execute('SELECT 1 FROM admin_accounts WHERE username=?', (username,)).fetchone():
                raise ValueError('이미 사용 중인 관리자 아이디입니다.')
            account_id = secrets.token_hex(16)
            db.execute('INSERT INTO admin_accounts VALUES (?, ?, ?, ?, 1, 1, ?)',
                       (account_id, username, hashed, role, int(self.clock())))
            self._audit(db, actor_id, 'admin.create', account_id, {'username': username, 'role': role}, int(self.clock()))
            return account_id

    def login(self, username, password, address):
        now = int(self.clock())
        username = username.strip().lower()[:128]
        # IP는 프록시 헤더를 신뢰하지 않으며 DB에는 해시만 저장한다.
        subjects = [(hashlib.sha256(f'user:{username}'.encode()).hexdigest(), 5),
                    (hashlib.sha256(f'ip:{address}'.encode()).hexdigest(), 20)]
        with self.market.connection() as db:
            account = db.execute('SELECT * FROM admin_accounts WHERE username=?', (username,)).fetchone()
        valid = len(password) <= 128 and check_password_hash(account['password_hash'] if account else self._dummy_hash, password)
        with self.market.connection(write=True) as db:
            # 해시 검사 중 계정 삭제·비활성화·비밀번호 변경이 있었으면 거부한다.
            current = db.execute('SELECT * FROM admin_accounts WHERE username=?', (username,)).fetchone()
            if current and account and current['password_hash'] != account['password_hash']:
                valid = False
            for subject, maximum in subjects:
                limit = db.execute('SELECT * FROM admin_login_limits WHERE subject=?', (subject,)).fetchone()
                if limit and limit['reset_at'] > now and limit['attempts'] >= maximum:
                    raise ValueError('로그인 시도가 많습니다. 15분 후 다시 시도하세요.')
            if not valid or not current or not current['active']:
                for subject, _ in subjects:
                    db.execute('INSERT INTO admin_login_limits VALUES (?, 1, ?) ON CONFLICT(subject) DO UPDATE SET '
                               'attempts=CASE WHEN admin_login_limits.reset_at<=? THEN 1 ELSE admin_login_limits.attempts+1 END, '
                               'reset_at=CASE WHEN admin_login_limits.reset_at<=? THEN excluded.reset_at ELSE admin_login_limits.reset_at END',
                               (subject, now + 900, now, now))
                self._audit(db, current['id'] if current else None, 'auth.failed', '', {}, now)
                # with 밖에서 오류를 반환해야 실패 횟수도 커밋된다.
                return None
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM admin_sessions WHERE expires_at<=?', (now,))
            db.execute('INSERT INTO admin_sessions VALUES (?, ?, ?)',
                       (hashlib.sha256(token.encode()).hexdigest(), current['id'], now + SESSION_SECONDS))
            db.execute('DELETE FROM admin_login_limits WHERE subject=?', (subjects[0][0],))
            self._audit(db, current['id'], 'auth.login', current['id'], {}, now)
            return token

    def get_session(self, token):
        if not isinstance(token, str) or len(token) > 128:
            return None
        with self.market.connection() as db:
            row = db.execute('SELECT a.id, a.username, a.role, a.must_change_password FROM admin_accounts a '
                             'JOIN admin_sessions s ON s.admin_id=a.id WHERE s.token_hash=? AND s.expires_at>? AND a.active=1',
                             (hashlib.sha256(token.encode()).hexdigest(), int(self.clock()))).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        with self.market.connection(write=True) as db:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            row = db.execute('SELECT admin_id FROM admin_sessions WHERE token_hash=?', (token_hash,)).fetchone()
            db.execute('DELETE FROM admin_sessions WHERE token_hash=?', (token_hash,))
            if row:
                self._audit(db, row[0], 'auth.logout', row[0], {}, int(self.clock()))

    def change_password(self, account_id, old_password, new_password):
        self.validate_password(new_password)
        if old_password == new_password:
            raise ValueError('기존 비밀번호와 다른 비밀번호를 입력하세요.')
        with self.market.connection() as db:
            account = db.execute('SELECT * FROM admin_accounts WHERE id=? AND active=1', (account_id,)).fetchone()
        if not account or len(old_password) > 128 or not check_password_hash(account['password_hash'], old_password):
            raise ValueError('현재 비밀번호가 올바르지 않습니다.')
        hashed = generate_password_hash(new_password)
        with self.market.connection(write=True) as db:
            result = db.execute('UPDATE admin_accounts SET password_hash=?, must_change_password=0 '
                                'WHERE id=? AND active=1 AND password_hash=?', (hashed, account_id, account['password_hash']))
            if result.rowcount != 1:
                raise ValueError('계정 상태가 바뀌었습니다. 다시 로그인하세요.')
            db.execute('DELETE FROM admin_sessions WHERE admin_id=?', (account_id,))
            self._audit(db, account_id, 'admin.password', account_id, {}, int(self.clock()))

    def disable_account(self, account_id, actor_id=None):
        with self.market.connection(write=True) as db:
            if actor_id is not None:
                self._require(db, actor_id, 'admins:manage')
                if actor_id == account_id:
                    raise ValueError('현재 로그인한 계정은 비활성화할 수 없습니다.')
            account = db.execute('SELECT * FROM admin_accounts WHERE id=? AND active=1', (account_id,)).fetchone()
            if not account:
                raise ValueError('활성 관리자 계정을 찾을 수 없습니다.')
            count = db.execute("SELECT COUNT(*) FROM admin_accounts WHERE role='owner' AND active=1").fetchone()[0]
            if account['role'] == 'owner' and count <= 1:
                raise ValueError('마지막 최고관리자는 비활성화할 수 없습니다.')
            db.execute('UPDATE admin_accounts SET active=0 WHERE id=?', (account_id,))
            db.execute('DELETE FROM admin_sessions WHERE admin_id=?', (account_id,))
            self._audit(db, actor_id, 'admin.disable', account_id, {}, int(self.clock()))

    def reset_password(self, username, new_password):
        """서버 CLI 전용 복구. 비밀번호나 해시는 감사 기록에 남기지 않는다."""
        self.validate_password(new_password)
        hashed = generate_password_hash(new_password)
        with self.market.connection(write=True) as db:
            account = db.execute('SELECT id FROM admin_accounts WHERE username=? AND active=1',
                                 (username.strip().lower(),)).fetchone()
            if not account:
                raise ValueError('활성 관리자 계정을 찾을 수 없습니다.')
            db.execute('UPDATE admin_accounts SET password_hash=?, must_change_password=1 WHERE id=?',
                       (hashed, account['id']))
            db.execute('DELETE FROM admin_sessions WHERE admin_id=?', (account['id'],))
            self._audit(db, None, 'admin.reset_password', account['id'], {}, int(self.clock()))

    def accounts(self):
        with self.market.connection() as db:
            return [dict(row) for row in db.execute('SELECT id, username, role, active, must_change_password, created_at '
                                                    'FROM admin_accounts ORDER BY created_at, username')]

    def audit(self):
        with self.market.connection() as db:
            events = []
            for row in db.execute('SELECT l.action, l.target_id, l.detail, l.created_at, a.username '
                                  'FROM admin_audit l LEFT JOIN admin_accounts a ON a.id=l.actor_id '
                                  'ORDER BY l.id DESC LIMIT 50'):
                event = dict(row)
                try:
                    detail = json.loads(event['detail'])
                    if isinstance(detail, dict):
                        detail.pop('impact', None)
                        detail.pop('level', None)
                        event['detail'] = json.dumps(detail, ensure_ascii=False)
                except (TypeError, json.JSONDecodeError):
                    pass
                events.append(event)
            return events

    def publish_news(self, article_id, title, body, target_kind, target, impact, actor_id, preset_id=None):
        self.market._event_id(article_id)
        title, body = title.strip(), body.strip()
        if target_kind != 'club':
            raise ValueError('뉴스는 개별 동아리에만 발행할 수 있습니다.')
        if not 1 <= len(title) <= 120 or not 1 <= len(body) <= 3000:
            raise ValueError('제목은 1~120자, 내용은 1~3,000자로 입력하세요.')
        if not math.isfinite(impact) or not -0.15 <= impact <= 0.15 or impact == 0:
            raise ValueError('영향은 -15%~15% 범위에서 0이 아닌 값으로 입력하세요.')
        with self.market.connection(write=True) as db:
            self._require(db, actor_id, 'news:publish')
            previous = db.execute('SELECT * FROM news_articles WHERE id=?', (article_id,)).fetchone()
            if previous:
                values = (previous['title'], previous['body'], previous['target_kind'], previous['target'], previous['impact'], previous['author_id'])
                if values != (title, body, target_kind, target, impact, actor_id):
                    raise ValueError('이미 사용된 발행 요청입니다. 화면을 새로고침하세요.')
                return False
            if not self.market._add_news(db, article_id, target_kind, target, impact):
                raise ValueError('이 발행 ID는 이미 시장 이벤트에서 사용 중입니다.')
            now = int(self.clock())
            db.execute('INSERT INTO news_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (article_id, title, body, target_kind, target, impact, actor_id, now))
            self._audit(db, actor_id, 'news.publish', article_id,
                        {'title': title, 'target_kind': target_kind, 'target': target,
                         **({'preset_id': preset_id} if preset_id else {})}, now)
        return True

    def publish_due_automatic_news(self):
        """Publish one good/bad pair atomically, without replaying missed intervals."""
        now = int(self.clock())
        with self.market.connection(write=True) as db:
            state = db.execute('SELECT next_at, published_count FROM automatic_news_state WHERE id=1').fetchone()
            paired_before = db.execute('SELECT 1 FROM news_articles WHERE id LIKE ? LIMIT 1', ('auto-pair-%',)).fetchone()
            if state and paired_before and now < state['next_at']:
                return False
            count = state['published_count'] if state else 0
            presets = news_presets()
            good = sorted((p for p in presets if p['sentiment'] == 'good'), key=lambda item: item['id'])
            bad = sorted((p for p in presets if p['sentiment'] == 'bad'), key=lambda item: item['id'])
            if not good or len(good) != len(bad):
                return False
            market_seed = db.execute('SELECT seed FROM market_state WHERE id=1').fetchone()['seed']
            cycle, position = divmod(count, len(good))
            rng = random.Random(hashlib.sha256(f'{market_seed}:auto-news-pairs:{cycle}'.encode()).digest())
            rng.shuffle(good)
            rng.shuffle(bad)
            # 충돌하는 쌍을 교환해 같은 동아리가 동시에 호재와 악재를 받지 않도록 한다.
            for i in range(len(good)):
                if good[i]['club_num'] != bad[i]['club_num']:
                    continue
                candidates = list(range(i + 1, len(good))) + list(range(i))
                swap = next((j for j in candidates if good[i]['club_num'] != bad[j]['club_num']
                             and good[j]['club_num'] != bad[i]['club_num']), None)
                if swap is None:
                    raise ValueError('서로 다른 동아리의 뉴스 쌍을 만들 수 없습니다.')
                bad[i], bad[swap] = bad[swap], bad[i]
            for preset in (good[position], bad[position]):
                article_id = f"auto-pair-{count}-{preset['sentiment']}"
                self.market._add_news(db, article_id, 'club', preset['club_num'], preset['impact'])
                db.execute('INSERT INTO news_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           (article_id, preset['title'], preset['body'], 'club', preset['club_num'],
                            preset['impact'], 'system', now))
            db.execute('INSERT INTO automatic_news_state (id, next_at, published_count) VALUES (1, ?, ?) '
                       'ON CONFLICT(id) DO UPDATE SET next_at=excluded.next_at, published_count=excluded.published_count',
                       (now + AUTO_NEWS_INTERVAL, count + 1))
        return True

    def articles(self):
        with self.market.connection() as db:
            rows = db.execute('SELECT a.*, n.effective_at FROM news_articles a '
                              'JOIN market_news n ON n.event_id=a.id ORDER BY a.published_at DESC, a.id DESC LIMIT 50')
            return [{**dict(row), 'target_name': (CLUBS if row['target_kind'] == 'club' else CATEGORIES)[row['target']],
                     'sentiment': '호재' if row['impact'] > 0 else '악재'} for row in rows]
