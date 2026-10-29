import sqlite3
import time

import click
from flask import Blueprint, current_app, jsonify, session, request
import hmac
from app.services.database import DatabaseError

market = Blueprint("market", __name__)


@market.post('/api/orders')
def place_order():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    expected = session.get('admin_csrf', '')
    supplied = request.headers.get('X-CSRF-Token', '')
    if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
        return jsonify(success=False, message='요청을 확인할 수 없습니다. 화면을 새로고침해주세요.'), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, message='주문 내용을 확인해주세요.'), 400
    try:
        result = current_app.extensions['trading'].place_order(
            session['user_id'], data.get('orderId'), data.get('clubNum'), data.get('side'),
            data.get('quantity'), data.get('quotedPrice'))
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response, 200 if result['success'] else 409
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except (sqlite3.Error, DatabaseError):
        current_app.logger.exception('모의 주문 처리 실패')
        return jsonify(success=False, message='주문 처리 결과를 확인할 수 없습니다. 같은 주문을 다시 시도해주세요.'), 503


@market.route("/api/market")
def market_data():
    if "user_id" not in session:
        return jsonify(success=False, message="로그인이 필요합니다."), 401
    try:
        data = current_app.extensions["market"].snapshot()
    except (sqlite3.Error, DatabaseError):
        current_app.logger.exception("주가 데이터 조회 실패")
        return jsonify(success=False, message="주가 데이터를 불러오지 못했습니다. 잠시 후 다시 시도하세요."), 503
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"
    return response


@market.cli.command("tick")
@click.option("--watch", is_flag=True, help="서버와 별도 프로세스에서 계속 시장을 갱신합니다.")
def market_tick(watch):
    """한 번 갱신하거나 --watch로 30초 틱을 계속 저장한다."""
    service = current_app.extensions["market"]
    while True:
        data = service.snapshot()
        click.echo(f"market timestamp={data['timestamp']} catching_up={data['catchingUp']}")
        if not watch:
            break
        time.sleep(0.1 if data["catchingUp"] else 30 - time.time() % 30 + 0.1)
