from flask import Blueprint, render_template, session, redirect, url_for, jsonify, current_app, send_from_directory
from app.services.supabase_client import supabase
from app.market_catalog import CLUBS
from app.routes.admin import csrf_token
from postgrest.exceptions import APIError
import httpx
from pathlib import Path

main = Blueprint("main", __name__)


@main.get("/manifest.webmanifest")
def web_manifest():
    return send_from_directory(
        current_app.static_folder,
        "manifest.webmanifest",
        mimetype="application/manifest+json",
        max_age=0,
    )


@main.get("/service-worker.js")
def service_worker():
    response = send_from_directory(
        current_app.static_folder,
        "service-worker.js",
        mimetype="application/javascript",
        max_age=0,
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@main.get("/offline")
def offline():
    return render_template("offline.html")


def club_profile(user):
    default = url_for('static', filename='images/default_stock_logo.png')
    club_id = user.get('club_id')
    if not club_id:
        return default, None
    try:
        result = supabase.table('clubs').select('name').eq('id', club_id).limit(1).execute()
        club_name = result.data[0]['name'] if result.data else None
    except (APIError, httpx.HTTPError, RuntimeError):
        current_app.logger.warning('동아리 프로필을 불러오지 못했습니다.')
        return default, None
    number = next((number for number, name in CLUBS.items() if name == club_name), None)
    if number is None:
        return default, club_name
    filename = f'images/{number}.png'
    if not (Path(current_app.static_folder) / filename).is_file():
        return default, club_name
    return url_for('static', filename=filename), club_name


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

    if current_app.config['AUTO_NEWS_ENABLED']:
        current_app.extensions['admin'].publish_due_automatic_news()
    return render_template("news.html", articles=current_app.extensions["admin"].articles())


@main.get('/api/news/latest')
def latest_news():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    admin = current_app.extensions['admin']
    if current_app.config['AUTO_NEWS_ENABLED']:
        admin.publish_due_automatic_news()
    articles = admin.articles()
    response = jsonify(success=True, latest_id=articles[0]['id'] if articles else None)
    response.headers['Cache-Control'] = 'no-store'
    return response

# 메인에서 매도매수로 이동
@main.route("/buy")
def buy():
    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("buy.html", csrf_token=csrf_token)

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
    profile_image, club_name = club_profile(user)
    trading = current_app.extensions['trading']
    movers = current_app.extensions['market'].five_minute_movers()
    portfolio = trading.portfolio(user_id, None if trading.market.store.postgres else user.get('cash', 0))
    rate = (portfolio['profit'] / portfolio['cost'] * 100) if portfolio['cost'] else 0

    def stock_card(stock):
        if stock is None:
            return {'name': '데이터 없음', 'sub': '최근 5분 기준', 'change': None, 'prices': [], 'timestamps': [],
                    'logo': url_for('static', filename='images/default_stock_logo.png')}
        filename = f"images/{stock['club_num']}.png"
        if not (Path(current_app.static_folder) / filename).is_file():
            filename = 'images/default_stock_logo.png'
        return {'name': stock['name'], 'sub': f"{stock['price']:,.0f}원 · {stock['category']}",
                'change': stock['change'], 'prices': stock['prices'], 'timestamps': stock['timestamps'],
                'logo': url_for('static', filename=filename)}

    data = {
        "success": True,
        "profile": {
            "username": user["name"],
            "profileImg": profile_image,
            "clubName": club_name
        },
        "portfolio": {
            "assets": f"{portfolio['total']:,}원",
            "rate": f"{rate:+.2f}%",
            "cash": portfolio['cash'],
            "stockValue": portfolio['value']
        },
        "topUpStock": stock_card(movers['up']),
        "topDownStock": stock_card(movers['down'])
    }

    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store'
    return response

@main.route("/api/profile-data")
def profile_data():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    user_id = session["user_id"]

    result = supabase.table("users").select("*").eq("id", user_id).single().execute()
    user = result.data
    profile_image, club_name = club_profile(user)
    trading = current_app.extensions['trading']
    market = current_app.extensions['market'].snapshot()
    portfolio = trading.portfolio(user_id, None if trading.market.store.postgres else user.get('cash', 0))
    market_by_club = {stock['club_num']: stock for stock in market['stocks']}
    for holding in portfolio['holdings']:
        candles = market_by_club.get(holding['club_num'], {}).get('candles', [])[-7:]
        holding['prices'] = [candle['close'] for candle in candles]
        holding['timestamps'] = [candle['timestamp'] for candle in candles]
    cash = portfolio['cash']
    rate = (portfolio['profit'] / portfolio['cost'] * 100) if portfolio['cost'] else 0

    response = jsonify({
        "success": True,
        "user": {
            "name": user["name"],
            "profileImg": profile_image,
            "clubName": club_name,
            "cash": cash,
            "total_assets": portfolio['total'],
            "rank": "전체 순위 준비중"
        },
        "summary": {
            "total_assets": f"{portfolio['total']:,}원",
            "daily_change": f"{portfolio['profit']:+,}원",
            "daily_rate": f"({rate:+.2f}%)",
            "purchase_amount": f"{portfolio['cost']:,}원",
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
        "holdings": portfolio['holdings'],
        "orders": trading.history(user_id)
    })
    response.headers['Cache-Control'] = 'no-store'
    return response
