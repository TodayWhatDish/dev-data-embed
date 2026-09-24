# Last Updated : 2026-09-24

"""services의 AppError를 HTTP 응답으로 바꾸는 유일한 자리."""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError, Conflict, Forbidden, InvalidInput, NotFound, Unauthorized
from app.services.products import ProductError

STATUS = {InvalidInput: 400, Unauthorized: 401, Forbidden: 403, NotFound: 404, Conflict: 409}
PRODUCT_STATUS = {"not_found": 404, "conflict": 409}

# 응답은 {"detail": ...} 모양으로 보내지 않으면, 
# 프론트엔드가 err.detail을 읽기 때문에, 이 모양을 바꾸면 web쪽 까지 고쳐야 함.
async def app_error_handler(req: Request, exc: AppError) -> JSONResponse:
    """응답 모양을 HTTPException과 같은 {"detail": ...}로 맞추고 프론트가 detail을 읽는다."""

    return JSONResponse(status_code=STATUS.get(type(exc), 400), content={"detail": exc.msg})

def product_http(exc: ProductError) -> HTTPException:
    """ProductError.kind를 HTTP 상태로 옮긴다. BE-21 2단계에서 삭제."""
    return HTTPException(status_code=PRODUCT_STATUS.get(exc.kind, 400), detail=exc.message)