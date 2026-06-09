from flask import Blueprint, render_template, session, redirect, url_for, jsonify
from app.services.supabase_client import supabase

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
    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("profile.html")

# 메인에서 뉴스로 이동
@main.route("/news")
def news():
    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("news.html")

# 메인에서 매도매수로 이동
@main.route("/buy")
def buy():
    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("buy.html")

@main.route("/rank")
def rank():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("rank.html")

@main.route("/settings")
def settings():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("settings.html")

@main.route("/api/index-data")
def index_data():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    user_id = session["user_id"]

    result = supabase.table("users").select("*").eq("id", user_id).single().execute()
    user = result.data

    data = {
        "success": True,
        "profile": {
            "username": user["name"],
            "profileImg": "/static/images/profile.png"
        },
        "portfolio": {
            "assets": f"{user.get('cash', 0):,}원",
            "rate": "+0.0%"
        },
        "topUpStock": {
            "name": "데이터 없음",
            "sub": "보유 주식",
            "change": "0.0",
            "logo": "/static/images/default_stock_logo.png"
        },
        "topDownStock": {
            "name": "데이터 없음",
            "sub": "보유 주식",
            "change": "0.0",
            "logo": "/static/images/default_stock_logo.png"
        }
    }

    return jsonify(data)

@main.route("/api/profile-data")
def profile_data():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    user_id = session["user_id"]

    result = supabase.table("users").select("*").eq("id", user_id).single().execute()
    user = result.data

    cash = user.get("cash", 0)

    return jsonify({
        "success": True,
        "user": {
            "name": user["name"],
            "cash": cash,
            "total_assets": cash,
            "rank": "전체 순위 준비중"
        },
        "summary": {
            "total_assets": f"{cash:,}원",
            "daily_change": "0원",
            "daily_rate": "(0.0%)",
            "purchase_amount": "0원",
            "cash": f"{cash:,}원"
        },
        "top": {
            "up_name": "데이터 없음",
            "up_info": "-",
            "up_rate": "0.0%",
            "down_name": "데이터 없음",
            "down_info": "-",
            "down_rate": "0.0%"
        },
        "holdings": []
    })