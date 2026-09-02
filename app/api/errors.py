# Last Updated : 206-09-02

"""features 계층의 도메인 예외를 HTTP 상태 코드로 바꾼다."""

from fastapi import HTTPException
from app.features.products import ProductError

STATUS = {"not_found":404, "conflict": 409}

def product_http(exc: ProductError) -> HTTPException:
    """ProductError.kind를 HTTP 상태로 옮긴다."""
    return HTTPException(status_code=STATUS.get(exc.kind, 400),detail=exc.message)