# Last Updated : 2026-09-29

"""services의 AppError와 요청 검증 실패(422)를 HTTP 응답으로 바꾸는 유일한 자리."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError, Conflict, Forbidden, InvalidInput, NotFound, Unauthorized

STATUS = {InvalidInput: 400, Unauthorized: 401, Forbidden: 403, NotFound: 404, Conflict: 409}

# 422 문구에 쓸 칸 이름. 없는 필드는 필드명이 그대로 나간다
FIELD_LABELS = {
    "email": "이메일",
    "password": "비밀번호",
    "name": "이름",
    "pet_name": "반려동물 이름",
    "pet_gender": "성별",
    "pet_birth_date": "생년월일",
    "pet_weight_kg": "체중",
    "pet_size": "체구",
    "pet_neutered": "중성화",
    "pet_activity_level": "활동량",
    "rating": "별점",
    "body": "후기",
    "quantity": "수량",
}

# 응답은 {"detail": ...} 모양으로 보내지 않으면,
# 프론트엔드가 err.detail을 읽기 때문에, 이 모양을 바꾸면 web쪽 까지 고쳐야 함.
async def app_error_handler(req: Request, exc: AppError) -> JSONResponse:
    """응답 모양을 HTTPException과 같은 {"detail": ...}로 맞추고 프론트가 detail을 읽는다."""

    return JSONResponse(status_code=STATUS.get(type(exc), 400), content={"detail": exc.msg})


async def validation_error_handler(req: Request, exc: RequestValidationError) -> JSONResponse:
    """pydantic 422 의 detail 은 영어 메시지 배열이다 - 화면에 그대로 띄울 한국어 문장 하나로 바꾼다.

    직접 쓴 validator(schemas.py 의 ValueError)는 이미 사용자용 문장이라 그대로 쓰고,
    Field(ge=, le=) 같은 내장 검사는 어느 칸이 틀렸는지만 알려준다.
    """
    msgs = []
    for e in exc.errors():
        if e["type"] == "value_error":
            msgs.append(str(e["ctx"]["error"]))
        else:
            field = str(e["loc"][-1]) if e["loc"] else ""
            msgs.append(f"{FIELD_LABELS.get(field, field)} 값이 올바르지 않습니다.")
    # 같은 칸에서 여러 번 걸려도 한 번만 보인다
    return JSONResponse(status_code=422, content={"detail": " ".join(dict.fromkeys(msgs))})
