import hmac
import re
import sqlite3
import httpx
from postgrest.exceptions import APIError

from flask import Blueprint, current_app, jsonify, request, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from app.services.database import DatabaseError
from app.services.profile_images import MAX_UPLOAD_BYTES, normalize_image
from app.services.ranking_service import profile_key


photos = Blueprint('photos', __name__)


def photo_url(key, revision):
    return url_for('photos.image', key=key, revision=revision)


@photos.after_request
def protect_response(response):
    response.headers.setdefault('Cache-Control', 'no-store')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@photos.route('/api/profile-image', methods=['GET', 'POST', 'DELETE'])
def profile_image():
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    if request.method != 'GET':
        expected = session.get('admin_csrf', '')
        supplied = request.headers.get('X-CSRF-Token', '')
        if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
            return jsonify(success=False, message='화면을 새로고침한 후 다시 시도해주세요.'), 403
    service = current_app.extensions['profile_images']
    user_id = session['user_id']
    try:
        # Resolve the default before mutation so failed lookups cannot report a saved upload as failed.
        from app.routes.main import display_user, club_profile
        user = display_user(user_id)
        default_image, club_name = club_profile(user)
        if request.method == 'POST':
            request.max_content_length = MAX_UPLOAD_BYTES + 64 * 1024
            uploaded = request.files.get('photo')
            if uploaded is None:
                raise ValueError('사진을 선택해주세요.')
            revision = service.save(user_id, uploaded.stream.read(MAX_UPLOAD_BYTES + 1))
        elif request.method == 'DELETE':
            service.remove(user_id)
            revision = None
        else:
            revision = service.revisions([profile_key(user_id)]).get(profile_key(user_id))
        return jsonify(success=True, image=photo_url(profile_key(user_id), revision) if revision else default_image,
                       defaultImage=default_image, hasCustom=bool(revision), name=user['name'], clubName=club_name)
    except RequestEntityTooLarge:
        return jsonify(success=False, message='5MB 이하의 사진을 선택해주세요.'), 413
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except (DatabaseError, sqlite3.Error, APIError, httpx.HTTPError, RuntimeError):
        current_app.logger.warning('프로필 사진 저장소 요청 실패')
        return jsonify(success=False, message='사진을 불러오거나 저장하지 못했습니다. 다시 시도해주세요.'), 503


@photos.get('/profile-images/<key>/<revision>.webp')
def image(key, revision):
    if 'user_id' not in session:
        return '', 401
    if not re.fullmatch(r'[a-f0-9]{64}', key) or not re.fullmatch(r'[a-f0-9]{64}', revision):
        return '', 404
    try:
        raw = current_app.extensions['profile_images'].read(key, revision)
    except (DatabaseError, sqlite3.Error):
        return '', 503
    if raw is None:
        return '', 404
    response = current_app.response_class(raw, mimetype='image/webp')
    response.headers['Cache-Control'] = 'private, no-cache'
    response.set_etag(revision)
    return response.make_conditional(request)


@photos.post('/api/profile-image/prepare')
def prepare_image():
    """Compatibility fallback only: normalize for the editor without saving a profile."""
    if 'user_id' not in session:
        return jsonify(success=False, message='로그인이 필요합니다.'), 401
    expected = session.get('admin_csrf', '')
    supplied = request.headers.get('X-CSRF-Token', '')
    if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
        return jsonify(success=False, message='화면을 새로고침한 후 다시 시도해주세요.'), 403
    try:
        request.max_content_length = MAX_UPLOAD_BYTES + 64 * 1024
        uploaded = request.files.get('photo')
        if uploaded is None:
            raise ValueError('사진을 선택해주세요.')
        raw = normalize_image(uploaded.stream.read(MAX_UPLOAD_BYTES + 1), for_editor=True)
        return current_app.response_class(raw, mimetype='image/png')
    except RequestEntityTooLarge:
        return jsonify(success=False, message='5MB 이하의 사진을 선택해주세요.'), 413
    except ValueError as error:
        return jsonify(success=False, message=str(error)), 400
