"""인증번호는 서버 DB의 HMAC으로만 저장하고 쿠키에는 불투명한 요청 ID만 넣는다."""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone


class EmailRateLimit(ValueError):
    pass


class EmailVerification:
    def __init__(self, market, secret, clock=time.time):
        self.market, self.secret, self.clock = market, secret or '', clock

    def initialize(self):
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS email_verifications (id TEXT PRIMARY KEY, email TEXT NOT NULL, '
                       'digest TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, '
                       'attempts INTEGER NOT NULL, status TEXT NOT NULL, ip_hash TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS email_verification_email ON email_verifications(email, created_at)')
            db.execute('CREATE INDEX IF NOT EXISTS email_verification_ip ON email_verifications(ip_hash, created_at)')
            db.execute('CREATE TABLE IF NOT EXISTS password_reset_requests (challenge TEXT PRIMARY KEY, '
                       'email TEXT NOT NULL, usernum TEXT NOT NULL, user_id TEXT, created_at INTEGER NOT NULL)')

    @staticmethod
    def normalize(email):
        if not isinstance(email, str):
            raise ValueError('학교 이메일 주소를 확인해주세요.')
        email = email.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9._%+\-]{0,63}@goedu\.kr', email):
            raise ValueError('@goedu.kr 학교 이메일만 사용할 수 있습니다.')
        return email

    def _digest(self, challenge_id, email, code):
        return hmac.new(self.secret.encode(), f'{challenge_id}:{email}:{code}'.encode(), hashlib.sha256).hexdigest()

    def prepare(self, email, address, code):
        email = self.normalize(email)
        if not self.secret:
            raise ValueError('인증 서비스를 설정해주세요.')
        now = int(self.clock())
        kst = timezone(timedelta(hours=9))
        day_start = int(datetime.fromtimestamp(now, kst).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        ip_hash = hmac.new(self.secret.encode(), address.encode(), hashlib.sha256).hexdigest()
        with self.market.connection(write=True) as db:
            db.execute('DELETE FROM email_verifications WHERE created_at<?', (now - 86400,))
            daily = db.execute("SELECT COUNT(*) FROM email_verifications WHERE email=? AND created_at>=? "
                               "AND status!='failed'", (email, day_start)).fetchone()[0]
            if daily >= 5:
                raise EmailRateLimit('하루 인증 메일 요청 횟수 5회를 초과했습니다. 내일 다시 시도해주세요.')
            recent = db.execute('SELECT COUNT(*), MAX(created_at) FROM email_verifications WHERE email=? AND created_at>?',
                                (email, now - 900)).fetchone()
            if recent[0] >= 3 or (recent[1] is not None and recent[1] > now - 60):
                raise EmailRateLimit('인증 메일 요청이 많습니다. 잠시 후 다시 시도해주세요.')
            count = db.execute('SELECT COUNT(*) FROM email_verifications WHERE ip_hash=? AND created_at>?', (ip_hash, now-900)).fetchone()[0]
            if count >= 60:
                raise EmailRateLimit('인증 메일 요청이 많습니다. 잠시 후 다시 시도해주세요.')
            challenge_id = secrets.token_urlsafe(32)
            db.execute('INSERT INTO email_verifications VALUES (?, ?, ?, ?, ?, 0, ?, ?)',
                       (challenge_id, email, self._digest(challenge_id, email, code), now, now+600, 'pending', ip_hash))
        return challenge_id

    def activate(self, challenge_id):
        with self.market.connection(write=True) as db:
            row = db.execute("SELECT email FROM email_verifications WHERE id=? AND status='pending'", (challenge_id,)).fetchone()
            if not row:
                raise ValueError('인증 요청을 찾을 수 없습니다.')
            db.execute("UPDATE email_verifications SET status='superseded' WHERE email=? AND status='sent'", (row['email'],))
            db.execute("UPDATE email_verifications SET status='sent' WHERE id=?", (challenge_id,))

    def fail(self, challenge_id):
        with self.market.connection(write=True) as db:
            db.execute("UPDATE email_verifications SET status='failed' WHERE id=?", (challenge_id,))

    def consume(self, challenge_id, email, code):
        email = self.normalize(email)
        if not isinstance(challenge_id, str) or not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
            return False
        now = int(self.clock())
        with self.market.connection(write=True) as db:
            row = db.execute("SELECT * FROM email_verifications WHERE id=? AND status='sent'", (challenge_id,)).fetchone()
            if not row or row['email'] != email or row['expires_at'] <= now or row['attempts'] >= 5:
                return False
            if not hmac.compare_digest(row['digest'], self._digest(challenge_id, email, code)):
                db.execute('UPDATE email_verifications SET attempts=attempts+1 WHERE id=?', (challenge_id,))
                return False
            db.execute("UPDATE email_verifications SET status='used' WHERE id=?", (challenge_id,))
            return True
