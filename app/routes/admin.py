from datetime import datetime, timezone, timedelta
from functools import wraps
import hmac
import secrets
import sqlite3

import click
from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from app.market_catalog import CATEGORIES, CLUBS
from app.services.admin_service import PERMISSIONS, ROLE_NAMES
from app.services.database import DatabaseError

admin = Blueprint('admin', __name__, url_prefix='/admin')


def service():
    return current_app.extensions['admin']


def csrf_token():
    if 'admin_csrf' not in session:
        session['admin_csrf'] = secrets.token_urlsafe(32)
    return session['admin_csrf']


@admin.before_request
def protect_admin():
    g.admin = service().get_session(session.get('admin_token'))
    if request.method == 'POST':
        expected = session.get('admin_csrf', '')
        supplied = request.form.get('csrf_token', '')
        if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
            abort(403, '요청을 확인할 수 없습니다. 화면을 새로고침한 후 다시 시도하세요.')


@admin.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )
    return response


@admin.context_processor
def admin_context():
    return {'csrf_token': csrf_token, 'role_names': ROLE_NAMES}


@admin.app_template_filter('kst_time')
def kst_time(timestamp):
    return datetime.fromtimestamp(timestamp, timezone(timedelta(hours=9))).strftime('%m.%d %H:%M')


def require_admin(permission=None, password_change=False):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            is_api = request.path.startswith('/admin/api/')
            if not g.admin:
                if is_api:
                    return jsonify(success=False, message='관리자 로그인이 필요합니다.'), 401
                return redirect(url_for('admin.login'))
            if g.admin['must_change_password'] and not password_change:
                if is_api:
                    return jsonify(success=False, message='먼저 임시 비밀번호를 변경하세요.'), 403
                return redirect(url_for('admin.password'))
            if permission and permission not in PERMISSIONS[g.admin['role']]:
                abort(403, '이 작업을 수행할 관리자 권한이 없습니다.')
            return view(*args, **kwargs)
        return wrapped
    return decorator


@admin.errorhandler(403)
def forbidden(error):
    if request.path.startswith('/admin/api/'):
        return jsonify(success=False, message=error.description), 403
    return render_template('admin/error.html', message=error.description), 403


@admin.errorhandler(sqlite3.Error)
def database_error(error):
    current_app.logger.exception('관리자 저장소 처리 실패')
    if request.path.startswith('/admin/api/'):
        return jsonify(success=False, message='일시적인 저장소 오류입니다.'), 503
    return render_template('admin/error.html', message='일시적인 저장소 오류입니다. 잠시 후 다시 시도하세요.'), 503


admin.register_error_handler(DatabaseError, database_error)


@admin.route('/login', methods=['GET', 'POST'])
def login():
    if g.admin:
        return redirect(url_for('admin.dashboard'))
    if request.method == 'GET':
        return redirect(url_for('auth.login'))
    error = None
    if request.method == 'POST':
        try:
            token = service().login(request.form.get('username', ''), request.form.get('password', ''), request.remote_addr or 'unknown')
            if token:
                session.clear()
                session['admin_token'] = token
                csrf_token()
                return redirect(url_for('admin.dashboard'))
            error = '아이디 또는 비밀번호가 올바르지 않습니다.'
        except ValueError as exc:
            error = str(exc)
    if error:
        flash(error)
    return redirect(url_for('auth.login'))


@admin.route('/logout', methods=['POST'])
@require_admin(password_change=True)
def logout():
    service().logout(session['admin_token'])
    session.clear()
    return redirect(url_for('admin.login'))


@admin.route('/password', methods=['GET', 'POST'])
@require_admin(password_change=True)
def password():
    error = None
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        try:
            if new_password != request.form.get('confirm_password', ''):
                raise ValueError('새 비밀번호가 서로 일치하지 않습니다.')
            service().change_password(g.admin['id'], request.form.get('old_password', ''), new_password)
            session.clear()
            flash('비밀번호를 변경했습니다. 새 비밀번호로 다시 로그인하세요.')
            return redirect(url_for('admin.login'))
        except ValueError as exc:
            error = str(exc)
    return render_template('admin/password.html', error=error)


@admin.route('/')
@require_admin('market:view')
def dashboard():
    market = current_app.extensions['market'].snapshot()
    return render_template('admin/dashboard.html', market=market, clubs=CLUBS, categories=CATEGORIES,
                           articles=service().articles(), audit=service().audit(),
                           accounts=service().accounts() if g.admin['role'] == 'owner' else [],
                           article_id=secrets.token_urlsafe(24))


@admin.route('/api/market')
@require_admin('market:view')
def market_data():
    return jsonify(current_app.extensions['market'].snapshot())


@admin.route('/news', methods=['POST'])
@require_admin('news:publish')
def publish_news():
    try:
        target_kind, raw_target = request.form.get('target', '').split(':', 1)
        impact = float(request.form.get('impact', '')) / 100
        created = service().publish_news(request.form.get('article_id', ''), request.form.get('title', ''),
                          request.form.get('body', ''), target_kind, int(raw_target), impact, g.admin['id'])
        flash('뉴스를 발행했습니다. 다음 주가 틱부터 영향을 반영합니다.' if created else '이미 발행된 뉴스입니다. 중복 발행하지 않았습니다.')
    except (ValueError, PermissionError) as exc:
        flash(f'발행하지 못했습니다: {exc}')
    return redirect(url_for('admin.dashboard', _anchor='news'))


@admin.route('/accounts', methods=['POST'])
@require_admin('admins:manage')
def create_account():
    try:
        temporary_password = request.form.get('temporary_password', '')
        if temporary_password != request.form.get('confirm_password', ''):
            raise ValueError('임시 비밀번호가 일치하지 않습니다.')
        service().create_account(request.form.get('username', ''), temporary_password,
                                 request.form.get('role', 'editor'), g.admin['id'])
        flash('관리자 계정을 생성했습니다. 첫 로그인 시 비밀번호를 변경해야 합니다.')
    except (ValueError, PermissionError) as exc:
        flash(str(exc))
    return redirect(url_for('admin.dashboard', _anchor='accounts'))


@admin.route('/accounts/<account_id>/disable', methods=['POST'])
@require_admin('admins:manage')
def disable_account(account_id):
    try:
        service().disable_account(account_id, g.admin['id'])
        flash('관리자를 비활성화하고 기존 로그인도 종료했습니다.')
    except (ValueError, PermissionError) as exc:
        flash(str(exc))
    return redirect(url_for('admin.dashboard', _anchor='accounts'))


@admin.cli.command('create')
@click.option('--username', required=True)
@click.option('--role', type=click.Choice(['owner', 'editor']), default='owner', show_default=True)
@click.option('--generate', is_flag=True, help='임시 비밀번호를 자동 발급해 이 터미널에 한 번 표시합니다.')
def create_admin(username, role, generate):
    """서버 터미널에서만 초기 관리자 계정을 만든다. 공개 가입 경로는 없다."""
    password = secrets.token_urlsafe(24) if generate else click.prompt('임시 비밀번호 (12자 이상)', hide_input=True, confirmation_prompt=True)
    try:
        service().create_account(username, password, role)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f'관리자 {username} 생성 완료. /admin/login 에서 로그인하세요.')
    if generate:
        click.echo(f'임시 비밀번호: {password}')


@admin.cli.command('reset-password')
@click.option('--username', required=True)
def reset_password(username):
    """서버 소유자가 관리자 비밀번호를 복구한다. 기존 세션을 모두 만료한다."""
    password = click.prompt('새 임시 비밀번호 (12자 이상)', hide_input=True, confirmation_prompt=True)
    try:
        service().reset_password(username, password)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo('비밀번호를 초기화했습니다. 다음 로그인 때 변경해야 합니다.')
