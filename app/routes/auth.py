from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app, abort
from app.services.email_service import EmailDeliveryError, generate_code, send_email_code
from app.services.email_verification import EmailRateLimit, EmailVerification
from app.services.database import DatabaseError
from app.market_catalog import CLUBS
import re
import hmac
import time
import sqlite3
import httpx
from postgrest.exceptions import APIError
from werkzeug.security import generate_password_hash, check_password_hash
from app.services.supabase_client import supabase
from app.routes.admin import csrf_token

auth = Blueprint("auth", __name__, url_prefix="/auth")


def valid_csrf():
    expected = session.get("admin_csrf", "")
    supplied = request.form.get("csrf_token", "")
    return bool(expected and supplied and hmac.compare_digest(expected.encode(), supplied.encode()))


# 로그인 페이지
@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        if not valid_csrf():
            abort(403)
        usernum = request.form.get("usernum", "").strip()
        password = request.form.get("password", "")

        # 관리자 아이디가 학번과 겹칠 경우 관리자 계정이 우선한다.
        admin = current_app.extensions["admin"]
        with admin.market.connection() as db:
            account = db.execute('SELECT 1 FROM admin_accounts WHERE username=?', (usernum.lower(),)).fetchone()
        if account or not re.fullmatch(r"[0-9]{5}", usernum):
            try:
                token = admin.login(usernum, password, request.remote_addr or "unknown")
                if token:
                    session.clear()
                    session["admin_token"] = token
                    csrf_token()
                    return redirect(url_for("admin.dashboard"))
                flash("아이디 또는 비밀번호가 올바르지 않습니다.")
            except ValueError as exc:
                flash(str(exc))
            return redirect(url_for("auth.login"))

        # 로그인 로직

        # DB에서 학번으로 사용자 찾기
        result = supabase.table("users").select("*").eq("usernum", usernum).execute()

        # 사용자가 없으면
        if len(result.data) == 0:
            flash("존재하지 않는 학번입니다.")
            return redirect(url_for("auth.login"))

        user = result.data[0]

        # 비밀번호 확인
        if not check_password_hash(user["password"], password):
            flash("비밀번호가 일치하지 않습니다.")
            return redirect(url_for("auth.login"))
        
        # 로그인 성공
        session.clear()
        session["user_id"] = user["id"]
        session["usernum"] = user["usernum"]
        session["name"] = user["name"]
        
        flash("로그인되었습니다.")
        return redirect(url_for("main.index"))
    
    return render_template("auth/login.html", csrf_token=csrf_token)


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        if not valid_csrf():
            abort(403)
        session.pop('password_reset', None)
        usernum = request.form.get('usernum', '').strip()
        try:
            if not re.fullmatch(r'[0-9]{5}', usernum):
                raise ValueError('학번 5자리를 확인해주세요.')
            email = EmailVerification.normalize(request.form.get('email', ''))
            verification = current_app.extensions['email_verification']
            code = generate_code()
            challenge = verification.prepare(email, request.remote_addr or 'unknown', code)
            try:
                result = supabase.table('users').select('id').eq('usernum', usernum).eq('email', email).limit(1).execute()
                user = result.data[0] if result.data else None
                if user:
                    send_email_code(email, code)
                    verification.activate(challenge)
                else:
                    verification.fail(challenge)
            except (APIError, httpx.HTTPError, RuntimeError, EmailDeliveryError, sqlite3.Error, DatabaseError):
                verification.fail(challenge)
                raise ValueError('인증 요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.') from None
            with verification.market.connection(write=True) as db:
                db.execute('DELETE FROM password_reset_requests WHERE created_at<?', (int(time.time()) - 86400,))
                db.execute('INSERT INTO password_reset_requests VALUES (?, ?, ?, ?, ?)',
                           (challenge, email, usernum, str(user['id']) if user else None, int(time.time())))
            session['password_reset'] = challenge
            flash('입력한 정보와 일치하는 계정이 있다면 인증번호를 보냈습니다. 학교 메일함을 확인해주세요.')
            return redirect(url_for('auth.reset_password'))
        except (ValueError, EmailRateLimit) as exc:
            flash(str(exc))
        except (sqlite3.Error, DatabaseError):
            flash('인증 서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 시도해주세요.')
    return render_template('auth/forgot_password.html', csrf_token=csrf_token)


@auth.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    challenge = session.get('password_reset')
    if not isinstance(challenge, str):
        flash('먼저 비밀번호 재설정 인증을 요청해주세요.')
        return redirect(url_for('auth.forgot_password'))
    try:
        with current_app.extensions['email_verification'].market.connection() as db:
            reset = db.execute('SELECT email, usernum, user_id FROM password_reset_requests WHERE challenge=?', (challenge,)).fetchone()
    except (sqlite3.Error, DatabaseError):
        flash('인증 서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 시도해주세요.')
        return redirect(url_for('auth.forgot_password'))
    if not reset:
        session.pop('password_reset', None)
        flash('먼저 비밀번호 재설정 인증을 요청해주세요.')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        if not valid_csrf():
            abort(403)
        password = request.form.get('password', '')
        try:
            if not 6 <= len(password) <= 128 or password != request.form.get('password_check'):
                raise ValueError('6~128자의 비밀번호와 비밀번호 확인을 확인해주세요.')
            verified = current_app.extensions['email_verification'].consume(
                challenge, reset['email'], request.form.get('email_code', ''))
            if not verified or not reset['user_id']:
                with current_app.extensions['email_verification'].market.connection() as db:
                    status = db.execute('SELECT status FROM email_verifications WHERE id=?', (challenge,)).fetchone()
                if status and status['status'] == 'used':
                    raise ValueError('이미 사용된 인증번호입니다. 변경한 비밀번호로 로그인하거나 새 인증번호를 요청해주세요.')
                raise ValueError('인증번호가 올바르지 않거나 만료되었습니다. 다시 확인해주세요.')
            session.pop('password_reset', None)
            result = (supabase.table('users').update({'password': generate_password_hash(password)})
                      .eq('id', reset['user_id']).eq('usernum', reset['usernum']).eq('email', reset['email']).execute())
            if not result.data:
                raise ValueError('계정을 확인할 수 없습니다. 인증을 다시 요청해주세요.')
            flash('비밀번호를 변경했습니다. 새 비밀번호로 로그인해주세요.')
            return redirect(url_for('auth.login'))
        except ValueError as exc:
            flash(str(exc))
        except (APIError, httpx.HTTPError, RuntimeError, sqlite3.Error, DatabaseError):
            session.pop('password_reset', None)
            flash('비밀번호를 변경하지 못했습니다. 인증을 다시 요청해주세요.')
            return redirect(url_for('auth.forgot_password'))
    return render_template('auth/reset_password.html', csrf_token=csrf_token)

# 회원가입 페이지
@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        usernum = request.form.get("usernum", "")
        password = request.form.get("password", "")
        club_id = request.form.get("club_id", "")
        try:
            email = EmailVerification.normalize(f"{request.form.get('email_id', '')}@goedu.kr")
            if not 1 <= len(name) <= 40 or not re.fullmatch(r"[0-9]{5}", usernum):
                raise ValueError("이름과 학번 5자리를 확인해주세요.")
            if not 6 <= len(password) <= 128 or password != request.form.get("password_check"):
                raise ValueError("6~128자의 비밀번호와 비밀번호 확인을 확인해주세요.")
            if club_id not in {"00", "82", *(f"{number:02}" for number in CLUBS)}:
                raise ValueError("소속 동아리를 선택해주세요.")
            verified = current_app.extensions["email_verification"].consume(
                session.get("email_challenge"), email, request.form.get("email_code", ""))
            if not verified:
                raise ValueError("인증번호가 올바르지 않거나 만료되었습니다. 새 인증번호를 받아주세요.")
        except ValueError as exc:
            flash(str(exc))
            return redirect(url_for("auth.signup"))
        except (sqlite3.Error, DatabaseError):
            flash("인증 서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 시도해주세요.")
            return redirect(url_for("auth.signup"))
        session.pop("email_challenge", None)
        try:
            supabase.table("users").insert({
                "name": name, "usernum": usernum, "email": email,
                "password": generate_password_hash(password), "club_id": club_id,
            }).execute()
        except (APIError, httpx.HTTPError, RuntimeError):
            flash("가입하지 못했습니다. 기존 가입 여부를 확인하고 새 인증번호로 다시 시도해주세요.")
            return redirect(url_for("auth.signup"))
        flash("회원가입이 완료되었습니다.")
        return redirect(url_for("auth.login"))
    return render_template("auth/signup.html")


@auth.route("/send-code", methods=["POST"])
def send_code():
    data = request.get_json(silent=True)
    challenge_id = None
    verification = current_app.extensions["email_verification"]
    try:
        email = EmailVerification.normalize(data.get("email") if isinstance(data, dict) else None)
        code = generate_code()
        challenge_id = verification.prepare(email, request.remote_addr or "unknown", code)
        send_email_code(email, code)
        verification.activate(challenge_id)
    except EmailRateLimit as exc:
        return jsonify(success=False, message=str(exc)), 429
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except EmailDeliveryError as exc:
        if challenge_id:
            try:
                verification.fail(challenge_id)
            except (sqlite3.Error, DatabaseError):
                pass
        return jsonify(success=False, message=str(exc)), 503
    except (sqlite3.Error, DatabaseError):
        return jsonify(success=False, message="인증 서비스를 일시적으로 이용할 수 없습니다."), 503
    session.pop("email_code", None)
    session.pop("email", None)
    session["email_challenge"] = challenge_id
    return jsonify(success=True, message="인증번호가 전송되었습니다.")


# 로그아웃
@auth.route("/logout")
def logout():

    session.clear()

    flash("로그아웃되었습니다.")
    return redirect(url_for("main.index"))
