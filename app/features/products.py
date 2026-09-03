# Last updated: 2026-09-01

""" 관리자 대시보드에서 상품을 등록/수정/삭제할 자리.

    검색/추천 후보를 고르는 로직(candidates())은 features/searching.py로 옮겼다.
    CRUD와 검색은 서로 다른 이유로 바뀌는 코드라 한 파일에 안 섞는다.
"""

from app.repositories import products as product_repo
from app.repositories import purchases as purchase_repo
from app.core.db import QueryError
import logging

# QueryError.reason -> (ProductError.kind, 사용자에게 보일 말)
# 여기 없는 reason(unknown_table, unknown_column, no_where ...)은 서버 코드 버그다.
# 잡지 않고 그대로 올려보내 500 이 되게 둔다 — 클라이언트 탓으로 돌리면 고칠 사람이 로그를 안 본다
CLIENT_FAULT = {
    'constraint_unique':  ("conflict", "이미 있는 값입니다."),
    'constraint_check':   ("params_error", "입력 값이 허용 범위를 벗어났습니다."),
    'constraint_fk':      ("params_error", "참조하는 대상이 없습니다."),
    'constraint_notnull': ("params_error", "필수 값이 비었습니다."),
    # bad_range 만 constraint_ 가 아닌데 여기 있다. page/size 는 클라이언트가 보낸 값이라
    # 서버 버그가 아니다 — unknown_column 처럼 500 으로 보내면 고칠 게 없는 걸 고치러 간다
    'bad_range':          ("params_error", "페이지 번호나 크기가 잘못되었습니다."),
}

class ProductError(Exception):
    """상품 관련 오류 : CRUD가 거부한 이유로 routes가 HTTP 상태로 옮긴다."""
    def __init__(self, kind:str, message:str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def list_products(page:int, size:int) -> list[dict]:
    """상품 여러 건 조회. page/size 가 잘못되면 ProductError("params_error") 다.

    거절 사유 자체는 repositories 가 이미 찍었다. 여기서 남기는 건 '그래서 어떻게 했나' 다 —
    같은 예외를 두 층이 다 찍으면 트레이스백이 두 번 남아 에러가 하나인지 둘인지 못 가린다.
    """
    try:
        products = product_repo.find_page(page,size)
    except QueryError as e:
        kind_msg = CLIENT_FAULT.get(e.reason)
        if kind_msg is None:
            raise                       # 서버 버그 -> 500 + 트레이스백
        logging.getLogger().info(f"List products -> ProductError({kind_msg[0]}), page: {page}, size: {size}")
        raise ProductError(*kind_msg) from e

    if not products:
        # 빈 목록은 에러가 아니다. 마지막 페이지 다음이면 정상이라 판단은 부르는 쪽 몫이다
        logging.getLogger().info(f"List products 결과 없음, page: {page}, size: {size}")    

    return products

def get_product(product_id:int) -> dict:
    """상품 한 건 조회"""
    product = product_repo.find_by_id(product_id)
    if not product:
        raise ProductError("not_found",f"product_id {product_id}상품이 없다.")
    return product

def create_product(values:dict) -> dict:
    """등록하고, 등록된 걸 다시 조회해서 돌려준다."""
    product_id = product_repo.insert(values)
    return product_repo.find_by_id(product_id)

def update_product(product_id:int, values:dict) -> int:
    """
    수정 한 후, 수정된 행 갯수를 반환
    업데이트된 행이 없다면 0을 반환
    """
    if not values:                      # PATCH 빈 바디. 안 막으면 'SET  WHERE' 라는 깨진 SQL 이 나간다
        raise ProductError("params_error", "조건 입력이 잘못되었습니다.")
    try:
        updated_row = product_repo.update_product(product_id, values)
    except QueryError as e:
        kind_msg = CLIENT_FAULT.get(e.reason)
        if kind_msg is None:
            raise                       # 서버 버그 -> 500 + 트레이스백
        raise ProductError(*kind_msg) from e

    logging.getLogger().debug(f"Try Update product table, updated_row: {updated_row}, where: {product_id},  update_cols: {values.keys()}")

    return updated_row

def update_after_select_product(product_id:int, values:dict) -> tuple[int, dict]:
    """수정하고 다시 조회해서 돌려준다. 존재 여부는 선조회가 아니라 고친 행 수로 안다."""
    if not values:                      # PATCH 빈 바디. 안 막으면 'SET  WHERE' 라는 깨진 SQL 이 나간다
            raise ProductError("params_error","조건 입력이 잘못되었습니다.")
    updated_row = update_product(product_id, values)

    logging.getLogger().debug("update after select to product table")

    if updated_row == 0:
        raise ProductError("not_found",f"{product_id}상품이 없다.")

    return (updated_row, product_repo.find_by_id(product_id))

# def delete_product(product_id:int) -> None:
#     """구매 이력이 있으면 ProductError로 막는다. 이력 검사는 지우기 전이어야 해서 순서를 못 바꾼다."""
#     used = purchase_repo.count_for_product(product_id)
#     if used : 
#         raise ProductError("conflict", f"구매 이력이 {used}건 있어 지울 수 없다")

#     if product_repo.delete(product_id) == 0:
#         raise ProductError("not_found",f"{product_id}상품이 없다.")
