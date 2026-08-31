"""구글 ID 토큰을 검증하는 자리. 검증된 payload만 밖으로 내보낸다."""

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.core.config import GOOGLE_CLIENT_ID


def verify_google_token(token: str) -> dict:
    """서명·발급자·대상(client_id)까지 검증한다. 실패하면 ValueError."""
    payload = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
    return {
        "sub": payload["sub"],
        "email": payload["email"],
        "name": payload.get("name", ""),
    }

# CHOI 추가. 실제유저정보 sub email name 딕셔너리를 구글 payload라고 부름.