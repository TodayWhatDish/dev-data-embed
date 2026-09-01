"""구글 로그인 엔드포인트. 가입/로그인을 여기서 한 번에 처리한다."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException

from app.adapters.stores.google_auth import verify_google_token
from app.api.schemas import AuthResponse, GoogleLoginRequest
from app.core.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from app.features.auth import login_or_signup # 자동으로 가입 후 로그인. 이후 개정보 입력.

router = APIRouter()


@router.post("/auth/google", response_model=AuthResponse)
def google_login(payload: GoogleLoginRequest) -> AuthResponse:
    try:
        google_payload = verify_google_token(payload.id_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="유효하지 않은 구글 토큰입니다.")

    user_id = login_or_signup(google_payload)

    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    token = jwt.encode({"user_id": user_id, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return AuthResponse(access_token=token)
