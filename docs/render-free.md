# 무료 Render 배포

코드는 무료 Render Web Service + Supabase PostgreSQL + HTTPS 이메일 API 조합입니다.
Render의 로컬 파일을 운영 DB로 사용하지 않습니다. `.env`의 비밀값과 로컬 DB는 Git에 올리지 않습니다.

## 1. Supabase 정보

기존 프로젝트를 열고 다음 항목을 `.env`에 저장합니다.

- `SUPABASE_URL`: Connect 또는 Settings의 Data API에 있는 Project URL.
- `SUPABASE_KEY`: Settings > API Keys의 서버용 Secret key (`sb_secret_...`). 기존 service_role도 지원합니다.
- `DATABASE_URL`: Connect > Connection string > Shared Pooler > Transaction 주소.

`DATABASE_URL`의 `[YOUR-PASSWORD]`를 **프로젝트 DB 비밀번호**로 바꿉니다.
Supabase 웹사이트 로그인 비밀번호와 다릅니다. 모르면 Database 설정에서 재설정합니다.
비밀번호에 `@`, `#`, `/`, `:` 같은 문자가 있으면 비밀번호 부분을 URL 인코딩해야 합니다.
API 키나 전체 연결 주소를 공개 URL 인코더 사이트에 붙여넣지 않습니다.
연결 주소의 호스트·포트·프로젝트 참조는 대시보드에서 복사한 값을 유지합니다.

앱은 Supabase transaction pooler를 위해 prepared statement를 끄고,
트랜잭션 advisory lock으로 동시 쓰기를 직렬화합니다. 시장·관리자·인증번호 데이터는
`stockolon_private` 스키마에 생성하고 `anon`, `authenticated`, `PUBLIC`의 스키마 접근을 차단합니다.
기존 `public.users` 테이블은 변경하지 않습니다. 회원가입/로그인에는 기존 users 테이블의
`id`, `name`, `usernum`, `email`, `password`, `club_id`, `cash` 컬럼이 필요합니다.
기존 회원 테이블은 RLS를 켜고 브라우저에 비밀번호 해시를 공개하는 정책을 만들지 마세요.

참고: [Supabase 연결](https://supabase.com/docs/guides/database/connecting-to-postgres),
[서버용 API 키](https://supabase.com/docs/guides/getting-started/api-keys).

## 2. 인증 메일: Brevo HTTPS API

무료 Render는 SMTP 포트를 차단하므로 `MAIL_USERNAME`, `MAIL_PASSWORD`는 사용하지 않습니다.
Brevo 또는 Resend HTTP API를 지원하고, Blueprint 기본값은 Brevo입니다.

1. [Brevo](https://www.brevo.com/)에 가입합니다. 현재 무료 플랜은 하루 300회 발송 한도가 있습니다.
2. **Settings > Senders, Domains & Dedicated IPs > Senders**에서 발신자를 추가합니다.
   발신 이름은 `STOCKOLON 26`, 이메일은 본인이 확인할 수 있는 주소를 사용합니다.
3. Brevo가 보낸 확인 메일로 발신자를 인증합니다. 계정의 발송 승인/도메인 인증 안내도 완료합니다.
   별도 도메인이 있다면 발신 도메인의 DNS 인증을 적용하는 편이 좋습니다.
4. **Settings > SMTP & API > API Keys & MCP**에서 API 키를 생성합니다. **SMTP key와 다릅니다.**
5. 다음을 `.env`에 추가합니다.

```dotenv
EMAIL_PROVIDER=brevo
BREVO_API_KEY=발급받은_API_키
MAIL_FROM=인증한_발신_이메일_주소
SESSION_COOKIE_SECURE=1
```

학생 수와 재발송량이 일일 발송 한도를 넘는지 확인하세요. 앱은 이메일별 60초 재발송 대기,
15분 3회 제한, IP별 15분 60회 제한을 적용합니다. 인증번호는 10분간 유효하고 5회 틀리면
잠깁니다. 쿠키에는 요청 ID만 저장하며, 인증번호 원문·키·메시지 본문은 로그에 남기지 않습니다.
실패한 메일 발송은 인증을 활성화하지 않습니다. 가입 처리 실패 후에는 새 번호가 필요합니다.

Resend를 이미 사용하는 경우 `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `MAIL_FROM`을 설정합니다.
학생에게 보내려면 해당 서비스의 발신 도메인 검증/수신자 제한 조건을 먼저 충족해야 합니다.

참고: [Brevo 발신자 생성](https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email),
[API 키](https://help.brevo.com/hc/en-us/articles/209467485-Create-and-manage-your-API-keys),
[무료 발송 한도](https://www.brevo.com/products/transactional-email/).

## 3. 로컬에서 설정 검사

`.env.render.example`은 필요한 항목 목록입니다. 기존 `.env`를 덮어쓰지 말고 부족한 항목만 채웁니다.

```bash
source venv/bin/activate
pip install -r requirements.txt
python scripts/check_deploy.py --env .env
```

이 검사는 비밀값을 출력하거나 메일을 발송하거나 DB를 변경하지 않습니다.
형식 검사 통과와 실제 접속 성공은 별개입니다. 실제 DB 접속, users 테이블,
메일 서비스 승인/발신자 인증은 배포 전 별도로 확인해야 합니다.

## 4. Render 서비스 생성

저장소 루트의 `render.yaml`로 Blueprint를 만들거나 기존 Web Service 설정을 수정합니다.
기존 서비스의 이름/주소를 사용한다면 새로운 Blueprint로 중복 서비스를 만들지 마세요.

| 항목 | 값 |
|---|---|
| 저장소 | StockKolon26 |
| 브랜치 | main |
| 서비스 유형 | Python Web Service |
| 인스턴스 | Free |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn run:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 4 --timeout 60` |
| Health Check Path | `/healthz` |
| Python | `.python-version`의 3.14 |

**Environment > Add from .env**로 필요한 값을 등록합니다.
Blueprint는 `SECRET_KEY`를 생성하고 비밀값은 `sync: false` 입력란에서 받습니다.
기존 서비스를 설정할 때는 `.env`의 충분히 긴 임의 `SECRET_KEY`를 유지합니다.
`SESSION_COOKIE_SECURE=1`이 필요합니다. `DATABASE_URL` 또는 메일 API 설정이 없으면
앱은 Render에서 조용히 SQLite/SMTP로 대체하지 않고 시작 오류를 냅니다.

필수 항목: `SECRET_KEY`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`,
`EMAIL_PROVIDER`, 해당 공급자의 API 키, `MAIL_FROM`, `SESSION_COOKIE_SECURE`.

[Render Flask 배포](https://render.com/docs/deploy-flask),
[환경 변수](https://render.com/docs/configure-environment-variables),
[무료 서비스 제한](https://render.com/docs/free).

## 5. 운영 관리자 계정

로컬에서 DB 주소를 연결한 뒤 운영 DB의 관리자를 생성할 수 있습니다.
Render 무료 서비스에는 대화형 Shell이 없으므로 로컬 터미널에서 같은 DB에 접속합니다.

```bash
# .env에 운영 DATABASE_URL이 설정되어 있는지 확인
flask --app run admin create --username admin --role owner
```

입력하는 임시 비밀번호는 화면에 표시되지 않으며, 최초 로그인 시 변경해야 합니다.
배포 URL의 `/admin/login`으로 접속합니다. 로컬 SQLite 계정과 가격 이력은 자동 이전하지 않습니다.
기존 운영 DB에 관리자 계정이 이미 있으면 같은 이름의 계정을 덮어쓰지 않습니다.

## 6. 무료 서비스에서의 시장 시간

무료 Render는 유휴 상태에서 중지될 수 있습니다. 항상 실행되는 30초 백그라운드 프로세스를
보장할 수 없으므로 무료 배포에서는 조회 시 지난 틱을 순서대로 복구합니다.
접속 중에는 화면이 10초마다 조회하고 가격은 30초 경계로 움직입니다.
재시작해도 PostgreSQL의 seed·시장 상태·뉴스·관리자 계정은 유지됩니다.
장기 중지 후에는 한 번에 240틱씩 복구하고 화면에 복구 상태를 표시합니다.
별도의 Render Worker와 SQLite 파일을 공유하는 구조는 사용하지 않습니다.

무료 DB 용량을 고려해 원시 30초 틱은 6시간, 5분봉은 7일을 보관합니다.
정리는 시장 갱신 시 시간 경계를 지날 때 수행합니다. 현재 가격과 뉴스·계정은 삭제하지 않습니다.
Supabase 프로젝트도 무료 플랜의 일시 중지·용량 정책이 적용되므로 실제 운영 시 상태를 확인하세요.

## 검증

기본 `python -m unittest discover -s tests -v`는 로컬 SQLite를 사용합니다.
실제 테스트 PostgreSQL을 별도로 준비하고 `TEST_POSTGRES_URL`을 지정하면 동일한 관리자·메일
테스트와 동시 쓰기·롤백·재시작·SQLite와 동일한 가격 경로를 PostgreSQL에서도 검사합니다.
테스트는 임의의 `stockolon_test_*` 스키마를 생성하고 해당 스키마만 정리합니다.
사용자 회원 테이블과 운영 `stockolon_private` 스키마를 테스트에 사용하지 않습니다.

2026-10-29 검증: SQLite와 독립된 로컬 PostgreSQL을 포함한 자동 테스트 88개 통과.
Render와 같은 환경 변수 조건에서 실제 Gunicorn gthread 서버를 실행해 `/healthz`,
일반 로그인·회원가입·관리자 로그인 화면의 200 응답을 확인했습니다. 실제 운영 DB 접속과
메일 발송은 환경 설정 완료 후 별도 확인이 필요하며 테스트에서 메일은 발송하지 않았습니다.
