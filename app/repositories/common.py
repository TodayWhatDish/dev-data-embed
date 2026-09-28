# Last Updated : 2026-09-13

"""여러 도메인이 같이 쓰는 마스터 테이블에 닿는 자리."""

from sqlalchemy.orm import Session

from app.core.db import as_dict
from app.models.common import Allergen, AnimalCategory


def get_allergens(db: Session):
    """알레르겐 전부. allergen_id 순으로 준다.

    정렬을 거는 이유 — 도메인이 이 목록으로 부모/자식 트리를 세운다. 순서가 부를 때마다
    달라지면 같은 트리를 두 번 만들었을 때 자식 순서가 어긋난다.
    allergen_id 가 PK 라 값이 안 겹치고, 그래서 이 키 하나로 순서가 하나로 확정된다.
    """
    rows = db.query(Allergen).order_by(Allergen.allergen_id.asc()).all()
    return [as_dict(row) for row in rows]


def get_animal_categories(db: Session):
    rows = db.query(AnimalCategory).all()
    return [as_dict(row) for row in rows]
