"""비밀값을 출력하거나 외부 서비스를 변경하지 않고 배포 환경 설정을 검사한다."""
import argparse
from pathlib import Path
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values
from psycopg.conninfo import conninfo_to_dict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.supabase_client import is_server_key


def validate(values):
    errors = []
    required = ('SECRET_KEY', 'DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_KEY', 'MAIL_FROM')
    for key in required:
        if not values.get(key):
            errors.append(f'{key}: 설정 필요')
    secret = values.get('SECRET_KEY', '') or ''
    if secret and (len(secret) < 32 or secret == 'replace-with-a-long-random-secret'):
        errors.append('SECRET_KEY: 32자 이상의 임의 문자열 필요')
    database = values.get('DATABASE_URL', '') or ''
    if database:
        try:
            if not database.startswith(('postgresql://', 'postgres://')) or '[YOUR-PASSWORD]' in database:
                raise ValueError()
            options = conninfo_to_dict(database)
            if not options.get('host') or not options.get('user'):
                raise ValueError()
        except Exception:
            errors.append('DATABASE_URL: 프로젝트 DB 비밀번호가 포함된 PostgreSQL 연결 주소 필요')
    project = values.get('SUPABASE_URL', '') or ''
    if project and (urlparse(project).scheme != 'https' or not urlparse(project).hostname or urlparse(project).path not in ('', '/')):
        errors.append('SUPABASE_URL: 유효한 HTTPS 프로젝트 URL 필요')
    if values.get('SUPABASE_KEY') and not is_server_key(values['SUPABASE_KEY']):
        errors.append('SUPABASE_KEY: 브라우저용 키 대신 서버용 Secret/service_role 키 필요')
    provider = values.get('EMAIL_PROVIDER', '') or ''
    if provider not in ('brevo', 'resend'):
        errors.append('EMAIL_PROVIDER: 무료 Render에는 brevo 또는 resend 필요')
    elif not values.get(f'{provider.upper()}_API_KEY'):
        errors.append(f'{provider.upper()}_API_KEY: 설정 필요')
    sender = values.get('MAIL_FROM', '') or ''
    if sender and ('@' not in sender or '\n' in sender or '\r' in sender):
        errors.append('MAIL_FROM: 메일 서비스에서 인증한 발신 이메일 주소 필요')
    if values.get('SESSION_COOKIE_SECURE') != '1':
        errors.append('SESSION_COOKIE_SECURE: HTTPS 배포에서는 1 필요')
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', default='.env', help='검사할 로컬 env 파일 (값은 출력하지 않음)')
    args = parser.parse_args()
    path = Path(args.env)
    if not path.is_file():
        print('환경 설정 파일을 찾을 수 없습니다.')
        return 1
    errors = validate(dotenv_values(path))
    if errors:
        print('배포 전 필요한 설정:')
        for error in errors:
            print(f'- {error}')
        return 1
    print('배포 설정 형식 검사 통과. 실제 DB 접속·users 테이블·발신자 인증은 별도 확인이 필요합니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
