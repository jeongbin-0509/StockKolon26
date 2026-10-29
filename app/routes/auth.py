from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app, abort
from app.services.email_service import EmailDeliveryError, generate_code, send_email_code
from app.services.email_verification import EmailRateLimit, EmailVerification
from app.services.database import DatabaseError
from app.market_catalog import CLUBS
import re
import hmac
import sqlite3
import httpx
from postgrest.exceptions import APIError
from werkzeug.security import generate_password_hash, check_password_hash
from app.services.supabase_client import supabase
from app.routes.admin import csrf_token

auth = Blueprint("auth", __name__, url_prefix="/auth")


# 로그인 페이지
@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        expected = session.get("admin_csrf", "")
        supplied = request.form.get("csrf_token", "")
        if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
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
