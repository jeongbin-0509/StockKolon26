from flask import Blueprint, render_template, session, redirect, url_for, jsonify, current_app, send_from_directory, request, make_response
from functools import wraps
from app.services.supabase_client import supabase
from app.market_catalog import CLUBS
from app.routes.admin import csrf_token
from postgrest.exceptions import APIError
from app.services.database import DatabaseError
import httpx
import sqlite3
from pathlib import Path
from flask import abort
from app.services.ranking_service import profile_key
import re
from time import perf_counter
from app.services.database_timing import collect_timings, format_timings, measure

main = Blueprint("main", __name__)
RANKING_ERRORS = (DatabaseError, sqlite3.Error, APIError, httpx.HTTPError, RuntimeError)


def report_database_timing(view):
    @wraps(view)
    def timed_view(*args, **kwargs):
        with collect_timings() as timings:
            with measure('handler'):
                response = make_response(view(*args, **kwargs))
        response.headers.add('Server-Timing', format_timings(timings))
        if 'db_connect' in timings or 'db_pool' in timings:
            current_app.logger.info('home_db_timing endpoint=%s status=%d %s',
                                    request.endpoint, response.status_code, format_timings(timings))
        return response
    return timed_view


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


def display_user(user_id):
    market = current_app.extensions['market']
    if market.store.postgres:
        with market.connection() as db:
            row = db.execute('SELECT u.name,u.cash,u.club_id,c.name AS club_name FROM public.users u '
                             'LEFT JOIN public.clubs c ON c.id=u.club_id WHERE u.id=?', (user_id,)).fetchone()
            if not row:
                abort(401)
            return dict(row)
    return supabase.table('users').select('name,club_id,cash').eq('id', user_id).single().execute().data


def load_viewer_portfolio(user_id):
    trading = current_app.extensions['trading']
    if trading.market.store.postgres:
        try:
            portfolio = trading.portfolio(user_id, include_profile=True)
        except LookupError:
            abort(401)
        return portfolio, portfolio
    user = display_user(user_id)
    return user, trading.portfolio(user_id, user.get('cash', 0))


def club_profile(user):
    default = url_for('static', filename='images/default_stock_logo.png')
    club_id = user.get('club_id')
    if not club_id:
        return default, None
    try:
        if 'club_name' in user:
            club_name = user['club_name']
        else:
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


def set_member_images(members):
    for member in members:
        number = next((n for n, name in CLUBS.items() if name == member.get('club_name')), None)
        filename = f'images/{number}.png'
        if not (Path(current_app.static_folder) / filename).is_file():
            filename = 'images/default_stock_logo.png'
        member['profileImg'] = url_for('static', filename=filename)


@main.route("/")
def index():

    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    # 로그인 되어 있으면 메인 페이지
    return render_template("index.html", csrf_token=csrf_token)

# 메인에서 프로필로 이동
@main.route("/profile")
def profile():
    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("profile.html", csrf_token=csrf_token)

# 메인에서 뉴스로 이동
@main.route("/news")
def news():
    # 로그인 안 되어 있으면 로그인 페이지
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if current_app.config['AUTO_NEWS_ENABLED']:
        current_app.extensions['admin'].publish_due_automatic_news()
    return render_template("news.html", articles=current_app.extensions["admin"].public_articles(), csrf_token=csrf_token)


@main.get('/api/news/latest')
def latest_news():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    admin = current_app.extensions['admin']
    if current_app.config['AUTO_NEWS_ENABLED']:
        admin.publish_due_automatic_news()
    response = jsonify(success=True, latest_id=admin.latest_article_id())
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

@main.get('/api/rankings')
def rankings():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    try:
        result = current_app.extensions['ranking'].rankings(session['user_id'], request.args.get('scope', 'school'))
    except ValueError as exc:
        response = jsonify(success=False, message=str(exc))
        response.headers['Cache-Control'] = 'no-store'
        return response, 400
    except RANKING_ERRORS:
        current_app.logger.warning('랭킹 데이터베이스 조회에 실패했습니다.')
        response = jsonify(success=False, message='순위를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.')
        response.headers['Cache-Control'] = 'no-store'
        return response, 503
    set_member_images(result.get('members', []) + ([result['me']] if result.get('me') else []))
    response = jsonify(success=True, **result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@main.route("/settings")
def settings():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("settings.html", csrf_token=csrf_token)


def mover_card(stock):
    if stock is None:
        return {'name': '데이터 없음', 'sub': '최근 5분 기준', 'change': None, 'candles': [], 'timestamps': [],
                'logo': url_for('static', filename='images/default_stock_logo.png'), 'club_num': None}
    filename = f"images/{stock['club_num']}.png"
    if not (Path(current_app.static_folder) / filename).is_file():
        filename = 'images/default_stock_logo.png'
    return dict(stock, sub=f"{stock['price']:,.0f}원 · {stock['category']}",
                logo=url_for('static', filename=filename))


@main.get('/api/market/movers')
def market_movers():
    if 'user_id' not in session:
        return jsonify(success=False), 401
    try:
        movers = current_app.extensions['market'].five_minute_movers()
        response = jsonify(success=True, up=mover_card(movers['up']), down=mover_card(movers['down']))
    except RANKING_ERRORS:
        response = jsonify(success=False, message='등락 종목을 불러오지 못했습니다.')
        response.status_code = 503
    response.headers['Cache-Control'] = 'no-store'
    return response


@main.get('/api/portfolio')
def my_portfolio():
    if 'user_id' not in session:
        return jsonify(success=False), 401
    try:
        result = current_app.extensions['ranking'].rankings(
            session['user_id'], 'school', public_key=profile_key(session['user_id']))
        set_member_images([result['me']])
        response = jsonify(success=True, user=result['me'], portfolio=result['portfolio'],
                           count=result['count'], timestamp=result['timestamp'], catching_up=result['catching_up'])
    except (ValueError, *RANKING_ERRORS):
        response = jsonify(success=False, message='투자 현황을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.')
        response.status_code = 503
    response.headers['Cache-Control'] = 'no-store'
    return response

@main.route("/api/index-data")
@report_database_timing
def index_data():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    user_id = session["user_id"]

    user, portfolio = load_viewer_portfolio(user_id)
    profile_image, club_name = club_profile(user)
    movers = current_app.extensions['market'].five_minute_movers()
    rate = (portfolio['profit'] / portfolio['cost'] * 100) if portfolio['cost'] else 0

    def stock_card(stock):
        if stock is None:
            return {'name': '데이터 없음', 'sub': '최근 5분 기준', 'change': None, 'prices': [], 'timestamps': [], 'candles': [],
                    'logo': url_for('static', filename='images/default_stock_logo.png')}
        filename = f"images/{stock['club_num']}.png"
        if not (Path(current_app.static_folder) / filename).is_file():
            filename = 'images/default_stock_logo.png'
        return {'name': stock['name'], 'sub': f"{stock['price']:,.0f}원 · {stock['category']}",
                'change': stock['change'], 'prices': stock['prices'], 'timestamps': stock['timestamps'],
                'candles': stock['candles'],
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

@main.get('/api/header-profile')
def header_profile():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    user = display_user(session['user_id'])
    profile_image, club_name = club_profile(user)
    response = jsonify(success=True, user={'name': user['name'], 'profileImg': profile_image, 'clubName': club_name})
    response.headers['Cache-Control'] = 'no-store'
    return response


@main.route("/api/profile-data")
@report_database_timing
def profile_data():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    user_id = session["user_id"]
    started = perf_counter()
    trading = current_app.extensions['trading']
    trade_view = request.args.get('view') == 'trade'
    summary_only = request.args.get('view') == 'summary'
    full_view = not (trade_view or summary_only)
    user, portfolio = load_viewer_portfolio(user_id)
    profile_image, club_name = club_profile(user)
    summary_time = (perf_counter() - started) * 1000
    if full_view:
        candles_by_club = trading.holding_candles(user_id)
        for holding in portfolio['holdings']:
            candles = candles_by_club.get(holding['club_num'], [])
            holding['prices'] = [candle['close'] for candle in candles]
            holding['timestamps'] = [candle['timestamp'] for candle in candles]
            holding['candles'] = candles
    cash = portfolio['cash']
    rate = (portfolio['profit'] / portfolio['cost'] * 100) if portfolio['cost'] else 0
    rank_text = None
    if full_view:
        try:
            ranking = current_app.extensions['ranking'].rankings(user_id, 'school')
            rank_text = f"전교 {ranking['me']['rank']:,}위 · {ranking['count']:,}명 중"
        except (ValueError, *RANKING_ERRORS):
            current_app.logger.warning('프로필 순위를 불러오지 못했습니다.')
            rank_text = '순위를 불러올 수 없습니다'

    response = jsonify({
        "success": True,
        "user": {
            "name": user["name"],
            "profileImg": profile_image,
            "clubName": club_name,
            "cash": cash,
            "total_assets": portfolio['total'],
            "rank": rank_text
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
        "orders": trading.history(user_id) if full_view else [],
        **({'totals': {key: portfolio[key] for key in ('cash', 'value', 'cost', 'total', 'profit')}}
           if summary_only else {})
    })
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Server-Timing'] = f'profile_summary;dur={summary_time:.1f}, profile_total;dur={(perf_counter() - started) * 1000:.1f}'
    return response


@main.get('/api/profile-details/<section>')
def profile_details(section):
    if 'user_id' not in session:
        return jsonify(success=False), 401
    trading = current_app.extensions['trading']
    started = perf_counter()
    try:
        if section == 'charts':
            response = jsonify(success=True, candles=trading.holding_candles(session['user_id']))
        elif section == 'history':
            response = jsonify(success=True, orders=trading.history(session['user_id']))
        else:
            abort(404)
    except (DatabaseError, sqlite3.Error):
        current_app.logger.warning('투자 현황 상세 조회 실패: %s', section)
        return jsonify(success=False), 503
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Server-Timing'] = f'profile_{section};dur={(perf_counter() - started) * 1000:.1f}'
    return response


@main.get('/api/my-rank')
def my_rank():
    if 'user_id' not in session:
        return jsonify(success=False), 401
    try:
        data = current_app.extensions['ranking'].rankings(session['user_id'], 'school')
        response = jsonify(success=True, rank=data['me']['rank'], count=data['count'])
    except (ValueError, *RANKING_ERRORS):
        response = jsonify(success=False, message='순위를 불러오지 못했습니다.')
        response.status_code = 503
    response.headers['Cache-Control'] = 'no-store'
    return response


@main.get('/members/<key>')
def member_profile(key):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if not re.fullmatch(r'[a-f0-9]{64}', key):
        abort(404)
    try:
        result = current_app.extensions['ranking'].rankings(session['user_id'], 'school', public_key=key)
    except ValueError:
        abort(404)
    except RANKING_ERRORS:
        return '프로필을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.', 503
    member = result['me']
    set_member_images([member])
    response = current_app.make_response(render_template('member.html', member=member,
        count=result['count'], image=member['profileImg'], portfolio_data={
            'success': True, 'user': member, 'portfolio': result['portfolio'], 'count': result['count'],
            'timestamp': result['timestamp'], 'catching_up': result['catching_up']}))
    response.headers['Cache-Control'] = 'no-store'
    return response
