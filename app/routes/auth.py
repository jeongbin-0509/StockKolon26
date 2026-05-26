# Flask 기능 import
from flask import Blueprint
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for


# auth Blueprint 생성
auth = Blueprint("auth", __name__)


# 로그인 페이지
@auth.route("/login", methods=["GET", "POST"])
def login():

    # 로그인 버튼 눌렀을 때
    if request.method == "POST":

        # form 데이터 가져오기
        usernum = request.form.get("usernum")
        password = request.form.get("password")

        # 로그인 로직

        # 메인 페이지로 이동
        return redirect(url_for("main.index"))

    # GET 요청이면 로그인 페이지 반환
    return render_template("auth/login.html")


# 회원가입 페이지
@auth.route("/signup", methods=["GET", "POST"])
def signup():

    # 회원가입 버튼 눌렀을 때
    if request.method == "POST":

        usernum = request.form.get("usernum")
        password = request.form.get("password")

        # 회원가입 처리

        return redirect(url_for("auth.login"))

    # GET 요청이면 회원가입 페이지 반환
    return render_template("auth/signup.html")


# 로그아웃
@auth.route("/logout")
def logout():

    # 나중에 session 삭제 예정

    return redirect(url_for("main.index"))