import hmac
import sqlite3

from flask import Blueprint, current_app, jsonify, request, session
from app.services.database import DatabaseError

cosmetics = Blueprint('cosmetics', __name__)


@cosmetics.app_context_processor
def csrf_context():
    from app.routes.admin import csrf_token
    return {'cosmetics_csrf': csrf_token}


@cosmetics.before_request
def authorize():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    if request.method == 'POST':
        expected = session.get('admin_csrf', '')
        supplied = request.headers.get('X-CSRF-Token', '')
        if not expected or not hmac.compare_digest(expected, supplied):
            return jsonify(success=False, message='화면을 새로고침해주세요.'), 403


@cosmetics.after_request
def private(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@cosmetics.errorhandler(DatabaseError)
@cosmetics.errorhandler(sqlite3.Error)
def unavailable(error):
    current_app.logger.warning('시그니처 저장소 요청 실패')
    return jsonify(success=False, message='시그니처를 불러오지 못했습니다. 다시 시도해주세요.'), 503


@cosmetics.get('/api/cosmetics')
def collection():
    return jsonify(success=True, **current_app.extensions['cosmetics'].collection(session['user_id']))


@cosmetics.post('/api/cosmetics/equip')
def equip():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or 'signature' not in data or 'frame' not in data:
        return jsonify(success=False, message='장착할 항목을 선택해주세요.'), 400
    try:
        equipped = current_app.extensions['cosmetics'].equip(session['user_id'], data['signature'], data['frame'])
    except ValueError as error:
        return jsonify(success=False, message=str(error)), 400
    return jsonify(success=True, equipped=equipped)


@cosmetics.post('/api/cosmetics/visit')
def visit():
    current_app.extensions['cosmetics'].visit(session['user_id'])
    return jsonify(success=True)
