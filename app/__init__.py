import os
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app(test_config=None):

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE") == "1"
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.config["MARKET_DATABASE"] = os.getenv("MARKET_DATABASE", str(Path(app.instance_path) / "market.sqlite3"))
    if test_config:
        app.config.update(test_config)

    from app.routes.main import main
    from app.routes.auth import auth
    from app.routes.market import market
    from app.services.market_service import MarketService
    from app.services.admin_service import AdminService
    from app.routes.admin import admin

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(market)
    service = MarketService(app.config["MARKET_DATABASE"])
    service.initialize()
    app.extensions["market"] = service
    admin_service = AdminService(service)
    admin_service.initialize()
    app.extensions["admin"] = admin_service
    app.register_blueprint(admin)

    return app
