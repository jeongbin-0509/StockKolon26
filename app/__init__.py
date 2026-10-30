import os
from pathlib import Path
from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()


def create_app(test_config=None):

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    for key in ("MAIL_FROM", "BREVO_API_KEY", "RESEND_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"):
        app.config[key] = os.getenv(key)
    app.config["EMAIL_PROVIDER"] = os.getenv("EMAIL_PROVIDER", "brevo" if os.getenv("RENDER") else "smtp").lower()
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "1" if os.getenv("RENDER") else "0") == "1"
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.config["MARKET_DATABASE"] = os.getenv("MARKET_DATABASE", str(Path(app.instance_path) / "market.sqlite3"))
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")
    app.config["DATABASE_SCHEMA"] = "stockolon_private"
    app.config["AUTO_NEWS_ENABLED"] = True
    if test_config:
        app.config.update(test_config)
        if test_config.get("TESTING") and "AUTO_NEWS_ENABLED" not in test_config:
            app.config["AUTO_NEWS_ENABLED"] = False
        # 개발자의 실제 DATABASE_URL을 로컬 단위 테스트가 사용하지 않도록 한다.
        if test_config.get("TESTING") and "DATABASE_URL" not in test_config:
            app.config["DATABASE_URL"] = None
    if app.config["DATABASE_URL"] and not app.config["DATABASE_URL"].startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL에는 HTTPS API 주소가 아닌 PostgreSQL 연결 주소가 필요합니다.")
    if os.getenv("RENDER") and not app.config.get("TESTING"):
        if not app.config["DATABASE_URL"]:
            raise RuntimeError("Render 배포에는 영속 PostgreSQL DATABASE_URL 설정이 필요합니다.")
        if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"] == "replace-with-a-long-random-secret":
            raise RuntimeError("Render 배포에는 임의의 SECRET_KEY 설정이 필요합니다.")
        if not app.config["SUPABASE_URL"] or not app.config["SUPABASE_KEY"]:
            raise RuntimeError("회원 기능의 SUPABASE_URL과 서버용 SUPABASE_KEY가 필요합니다.")
        from app.services.supabase_client import is_server_key
        if not is_server_key(app.config["SUPABASE_KEY"]):
            raise RuntimeError("SUPABASE_KEY를 서버용 Secret/service_role 키로 설정하세요.")
        provider = app.config["EMAIL_PROVIDER"]
        if provider not in ("brevo", "resend") or not app.config.get(f"{provider.upper()}_API_KEY") or not app.config["MAIL_FROM"]:
            raise RuntimeError("무료 Render에는 HTTP 메일 API 키와 MAIL_FROM 설정이 필요합니다.")
        if not app.config["SESSION_COOKIE_SECURE"]:
            raise RuntimeError("Render HTTPS 배포에서는 SESSION_COOKIE_SECURE=1을 설정하세요.")
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    from app.routes.main import main
    from app.routes.auth import auth
    from app.routes.market import market
    from app.services.market_service import MarketService
    from app.services.admin_service import AdminService
    from app.services.trading_service import TradingService
    from app.services.email_verification import EmailVerification
    from app.services.database import DatabaseError
    import sqlite3
    from app.routes.admin import admin

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(market)
    service = MarketService(app.config["DATABASE_URL"] or app.config["MARKET_DATABASE"], schema=app.config["DATABASE_SCHEMA"])
    service.initialize()
    app.extensions["market"] = service
    trading = TradingService(service)
    trading.initialize()
    app.extensions["trading"] = trading
    admin_service = AdminService(service)
    admin_service.initialize()
    app.extensions["admin"] = admin_service
    app.register_blueprint(admin)
    verification = EmailVerification(service, app.config["SECRET_KEY"])
    verification.initialize()
    app.extensions["email_verification"] = verification

    @app.get("/healthz")
    def healthz():
        try:
            with service.connection() as db:
                db.execute("SELECT last_tick FROM market_state WHERE id=1").fetchone()
        except (sqlite3.Error, DatabaseError):
            return jsonify(status="unavailable"), 503
        return jsonify(status="ok")

    return app
