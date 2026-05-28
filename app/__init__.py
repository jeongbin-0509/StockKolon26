# Flask 클래스 가져오기
import os
from dotenv import load_dotenv
from flask import Flask

load_dotenv()

# Flask 앱 생성 함수
def create_app():

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

    # routes/main.py 에서 main Blueprint 가져오기
    from app.routes.main import main
    from app.routes.auth import auth

    # Blueprint 등록
    app.register_blueprint(main)
    app.register_blueprint(auth)

    # 완성된 Flask 앱 반환
    return app