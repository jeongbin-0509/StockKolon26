# Blueprint와 HTML 렌더링 함수 가져오기
from flask import Blueprint, render_template


# Blueprint 생성
# "main" 이라는 이름의 미니 Flask 앱 생성
main = Blueprint("main", __name__)


# 메인 페이지
@main.route("/")
def index():

    # templates/index.html 반환
    return render_template("index.html")