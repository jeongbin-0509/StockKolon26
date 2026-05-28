from flask import Blueprint, render_template, session, redirect, url_for

main = Blueprint("main", __name__)


@main.route("/")
def index():

    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    # 로그인 되어 있으면 메인 페이지
    return render_template("index.html")

# 메인에서 프로필로 이동
@main.route("/profile")
def profile():
    return render_template("profile.html")