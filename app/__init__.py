import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app():

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

    from app.routes.main import main
    from app.routes.auth import auth

    app.register_blueprint(main)
    app.register_blueprint(auth)

    return app