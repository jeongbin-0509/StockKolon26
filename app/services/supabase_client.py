import os
import base64
import json
from functools import lru_cache
from supabase import create_client
from dotenv import load_dotenv
from werkzeug.local import LocalProxy

load_dotenv()


def is_server_key(key):
    if not isinstance(key, str):
        return False
    if key.startswith("sb_secret_") and len(key) > 12:
        return True
    try:
        part = key.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return isinstance(payload, dict) and payload.get("role") == "service_role"
    except (ValueError, IndexError, TypeError):
        return False


@lru_cache(maxsize=1)
def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("회원 기능에는 SUPABASE_URL과 SUPABASE_KEY 설정이 필요합니다.")
    if not is_server_key(key):
        raise RuntimeError("SUPABASE_KEY에는 브라우저용 anon 키가 아닌 서버용 Secret/service_role 키가 필요합니다.")
    return create_client(url, key)


# 시장 CLI/테스트/로그인 화면은 Supabase 접속 없이도 시작할 수 있다.
supabase = LocalProxy(get_supabase)
