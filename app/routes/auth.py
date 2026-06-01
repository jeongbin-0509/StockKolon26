from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.services.email_service import generate_code, send_email_code
from werkzeug.security import generate_password_hash, check_password_hash
from app.services.supabase_client import supabase

auth = Blueprint("auth", __name__, url_prefix="/auth")


# 로그인 페이지
@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        usernum = request.form.get("usernum")
        password = request.form.get("password")

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
        session["user_id"] = user["id"]
        session["usernum"] = user["usernum"]
        session["name"] = user["name"]
        
        flash("로그인되었습니다.")
        return redirect(url_for("main.index"))
    
    return render_template("auth/login.html")

# 회원가입 페이지
@auth.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":
        name = request.form.get("name")
        
        usernum = request.form.get("usernum")
        
        email_id = request.form.get("email_id")
        email = f"{email_id}@goedu.kr"

        email_code = request.form.get("email_code")
        
        password = request.form.get("password")
        
        password_check = request.form.get("password_check")

        club_id = request.form.get("club_id")

        print("입력 인증번호:", email_code)
        print("세션 인증번호:", session.get("email_code"))
        print("입력 이메일:", email)
        print("세션 이메일:", session.get("email"))

        if password != password_check:
            flash("비밀번호가 일치하지 않습니다.")
            return redirect(url_for("auth.signup"))

        if session.get("email_code") != email_code:
            flash("이메일 인증번호가 올바르지 않습니다.")
            return redirect(url_for("auth.signup"))

        if session.get("email") != email:
            flash("인증받은 이메일과 입력한 이메일이 다릅니다.")
            return redirect(url_for("auth.signup"))

        # 회원가입 DB 저장 로직
        hashed_password = generate_password_hash(password)

        supabase.table("users").insert({
            "name": name,
            "usernum": usernum,
            "email": email,
            "password": hashed_password,
            "club_id": club_id
        }).execute()

        flash("회원가입이 완료되었습니다.")

        return redirect(url_for("auth.login"))
    

    return render_template("auth/signup.html")



# 이메일 인증번호 전송
@auth.route("/send-code", methods=["POST"])
def send_code():
    data = request.get_json()
    email = data.get("email")

    print("받은 이메일:", email)

    if not email:
        return jsonify({
            "success": False,
            "message": "이메일을 입력하세요."
        })

    code = generate_code()
    print("생성된 인증번호:", code)

    session["email"] = email
    session["email_code"] = code

    send_email_code(email, code)

    return jsonify({
        "success": True,
        "message": "인증번호가 전송되었습니다."
    })


# 로그아웃
@auth.route("/logout")
def logout():

    session.clear()

    flash("로그아웃되었습니다.")
    return redirect(url_for("main.index"))