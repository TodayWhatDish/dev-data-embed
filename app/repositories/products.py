import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import QueryError, as_dict, as_query_error, commit
from app.models.product import (
    FeedingPurpose,
    Ingredient,
    IngredientAllergen,
    Product,
    ProductAnimalCategory,
    ProductCategory,
    ProductFeedingPurpose,
    ProductIngredient,
    ProductNutrition,
)

# 단일 테이블 CRUD 는 ORM(db.query/add)으로 간다. 조인·집계는 ORM 이 못 만들어서 아래에도
# fetch/fetch_tuples 로 짠 SQL 이 남아 있었는데, products 쪽엔 그런 자리가 없어 전부 ORM 이다.

# def get_product_detail_info():
#     fetch_tuples(db, """
#     SELECT *
#     FROM product
#     JOIN
#     """)
#     pass

# # 벡터 디비 매핑을 위한 product의 모든 정보가 필요하다.

# def product_category_hierachy():
#     fetch_tuples(db, """
#     """
#           )
#     pass


def get_product_categories(db: Session):
    rows = db.query(ProductCategory).all()
    return [as_dict(row) for row in rows]


def get_feeding_purposes(db: Session):
    rows = db.query(FeedingPurpose).all()
    return [as_dict(row) for row in rows]


def get_ingredients(db: Session):
    rows = db.query(Ingredient).all()
    return [as_dict(row) for row in rows]


# 아래는 임베딩 문장 재료. 이름은 마스터 캐시에 있으니 관계 테이블에서 id 만 긁어온다.
# 1:N 이라 조인하지 않고 전량 스캔 -> domain 에서 product_id 로 묶는다 (합쳐서 1500행 남짓)


def get_products(db: Session):
    rows = db.query(Product).filter_by(is_active=1).all()
    return [as_dict(row) for row in rows]


def get_product_animal_category_ids(db: Session):
    rows = db.query(ProductAnimalCategory).all()
    return [as_dict(row) for row in rows]


def get_product_feeding_purpose_ids(db: Session):
    rows = db.query(ProductFeedingPurpose).all()
    return [as_dict(row) for row in rows]


def get_product_ingredient_ids(db: Session):
    rows = db.query(ProductIngredient).all()
    return [as_dict(row) for row in rows]


def get_product_nutritions(db: Session):
    rows = db.query(ProductNutrition).all()
    return [as_dict(row) for row in rows]


def find_by_id(db: Session, product_id: int) -> dict | None:
    """상품 한 건 조회. 없으면 None (예외가 아니다 — 부른 쪽이 404 를 정한다)"""
    row = db.query(Product).filter_by(product_id=product_id).first()
    return as_dict(row) if row else None


def find_page(db: Session, page: int, size: int) -> list[dict]:
    """상품 여러 건 조회

    정렬을 걸어 둔다. ORDER BY 가 없으면 sqlite 가 순서를 보장하지 않는데, OFFSET 은
    '앞에서 몇 개' 를 건너뛰는 거라 페이지를 넘기는 사이 같은 상품이 두 번 나오거나 빠진다.
    product_id 는 PK 라 값이 안 겹쳐서 이것만으로 순서가 하나로 확정된다.

    size 가 0 이하이거나 page 가 음수면 QueryError('bad_range') 다. 예전엔 LIMIT 0 이 빈 목록,
    음수 OFFSET 이 0 으로 조용히 해석돼서 잘못된 요청이 티가 안 났다.
    """
    offset = page * size
    if size < 1:
        err = QueryError("bad_range", "product", f"size={size}")
    elif offset < 0:
        err = QueryError("bad_range", "product", f"offset={offset}")
    else:
        err = None

    if err:
        logging.getLogger().warning(
            f"Reject find_page: reason={err.reason}, page={page}, size={size}, "
            f"offset={offset}, detail={err.detail}"
        )
        raise err

    rows = (
        db
        .query(Product)
        .order_by(Product.product_id.asc())
        .limit(size)
        .offset(offset)
        .all()
    )
    products = [as_dict(row) for row in rows]

    logging.getLogger().debug(f"Find page product, page: {page}, size: {size}, rows: {len(products)}")
    return products


def _check_columns(table: str, model, values: dict) -> None:
    """컬럼 이름은 관리자 PATCH 로 자유 입력이 들어오는 자리라 모델 컬럼인지 미리 본다.

    ORM 은 테이블 이름을 동적으로 안 받으니 unknown_table 은 더 이상 있을 수 없는 사유다.
    """
    unknown = values.keys() - {c.name for c in model.__table__.columns}
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))


def insert(db: Session, values: dict) -> int:
    """상품 한 건을 등록하고 새로 생긴 product_id를 돌려준다.

    거절당하면 QueryError 가 올라온다. 사유를 아는 건 commit(db, ) 인데 무엇을 넣으려 했는지
    아는 건 여기라, 로그는 여기서 찍고 예외는 그대로 위로 넘긴다.
    """
    try:
        if not values:
            raise QueryError("no_values", "product")
        _check_columns("product", Product, values)

        product = Product(**values)
        db.add(product)
        commit(db, "product")
    except QueryError as e:
        logging.getLogger().warning(
            f"Reject insert product: reason={e.reason}, cols={list(values.keys())}, detail={e.detail}"
        )
        raise  # 인자 없는 raise 여야 원래 트레이스백이 안 날아간다

    logging.getLogger().debug(f"Insert product, product_id: {product.product_id}, cols: {list(values.keys())}")
    return product.product_id


def update_product(db: Session, product_id: int, values: dict) -> int:
    """상품 한 건을 수정하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다.

    거절당하면 QueryError 가 올라온다. 사유를 아는 건 commit(db, ) 인데 어느 테이블 몇 번인지
    아는 건 여기라, 로그는 여기서 찍고 예외는 그대로 위로 넘긴다.
    """
    try:
        if not values:
            raise QueryError("no_values", "product")
        _check_columns("product", Product, values)

        try:
            # Query.update() 는 flush 를 기다리지 않고 그 자리에서 UPDATE 를 실행한다 -
            # CHECK 위반이 여기서 바로 터진다 (commit(db, ) 이 잡는 자리가 아니다)
            rowcount = db.query(Product).filter_by(product_id=product_id).update(
                values, synchronize_session=False
            )
        except IntegrityError as e:
            db.rollback()
            raise as_query_error(e, "product") from e
        commit(db, "product")
        return rowcount
    except QueryError as e:
        logging.getLogger().warning(
            f"Reject update product: reason={e.reason}, product_id={product_id}, detail={e.detail}"
        )
        raise  # 인자 없는 raise 여야 원래 트레이스백이 안 날아간다


def inactive_product(db: Session, product_id: int) -> int:
    """상품 한 건을 비활성화(is_active=0)하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다.

    행을 지우지 않는다 — 구매 이력이 product_id 를 참조하고 있어서 DELETE 는 constraint_fk 로
    막히거나 이력을 끊는다. 조회 쪽은 get_products / v_safe_products 가 is_active = 1 로 거른다.
    """
    return update_product(db, product_id, {"is_active": 0})


def get_ingredient_allergen_ids(db: Session):
    rows = db.query(IngredientAllergen).all()
    return [as_dict(row) for row in rows]
