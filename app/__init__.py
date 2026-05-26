# Flask 클래스 가져오기
from flask import Flask


# Flask 앱 생성 함수
def create_app():

    # Flask 서버 객체 생성
    app = Flask(__name__)

    # routes/main.py 에서 main Blueprint 가져오기
    from app.routes.main import main
    from app.routes.auth import auth

    # Blueprint 등록
    app.register_blueprint(main)
    app.register_blueprint(auth)

    # 완성된 Flask 앱 반환
    return app