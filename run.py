# 실행하는 용도로만 사용하는 파일
# 실제 코딩은 /app/ 에서 하면 됨

# app 폴더 안의 create_app 함수 가져오기
from app import create_app

# Flask 앱 생성
app = create_app()

# 현재 파일을 직접 실행했을 때만 서버 실행
if __name__ == "__main__":
    app.run(debug=True)