import sqlite3
import time

import click
from flask import Blueprint, current_app, jsonify, session

market = Blueprint("market", __name__)


@market.route("/api/market")
def market_data():
    if "user_id" not in session:
        return jsonify(success=False, message="로그인이 필요합니다."), 401
    try:
        data = current_app.extensions["market"].snapshot()
    except sqlite3.Error:
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
