import os
from functools import lru_cache
from supabase import create_client
from dotenv import load_dotenv
from werkzeug.local import LocalProxy

load_dotenv()

@lru_cache(maxsize=1)
def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("회원 기능에는 SUPABASE_URL과 SUPABASE_KEY 설정이 필요합니다.")
    return create_client(url, key)


# 시장 CLI/테스트/로그인 화면은 Supabase 접속 없이도 시작할 수 있다.
supabase = LocalProxy(get_supabase)
