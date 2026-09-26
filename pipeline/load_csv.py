# Last updated: 2026-09-22
"""
data/master + data/seed 의 CSV 를 Supabase(Postgres) 로 적재한다.

스키마의 단일 원천은 app/models/ 의 SQLAlchemy 모델이다(app/core/db.py 의 Base) —
여기서 DDL 을 다시 적지 않는다. pipeline/create_schema/*_schema.py 는 SQLite 전용
설계 문서(user.db, docs/schema/ 와 1:1)라서 안 쓴다. 다만 뷰(VIEWS)와 코드표 시드(SEEDS)는
app/models/ 에 대응하는 자리가 없으므로 거기서 그대로 재사용한다 — 값을 두 군데 적지 않는다.

**적재 순서를 손으로 적지 않는다.** Base.metadata.sorted_tables 가 이미 FK 기준으로
위상 정렬해서 돌려준다(SQLAlchemy 가 제공하는 기능 - 직접 구현하지 않는다).

CSV 규약은 pipeline/make_data/gen_seed.py 의 docstring 에 있다. 값 캐스팅은 하지 않는다
— NOT NULL/타입 위반은 DB 가 INSERT 시점에 걸러준다. 빈 칸 -> NULL 변환만 한다.

실행: python -m pipeline.load_csv          (스키마+뷰+시드 재생성 후 적재. 기존 테이블은 비워진다)
      python -m pipeline.load_csv --keep   (스키마는 그대로 두고 적재만)
"""

import csv
import re
import sys
from pathlib import Path

from sqlalchemy import insert, text

# app/models/* 를 전부 import 해야 클래스들이 Base.metadata 에 등록된다.
from app.models import common, pet, product, purchase, user  # noqa: F401
from app.core.config import MASTER_DIR, SEED_DIR
from app.core.db import Base, engine

sys.path.insert(0, str(Path(__file__).resolve().parent / "create_schema"))
import common_schema  # noqa: E402  (SEEDS 재사용용 - TABLES/INDEXES 는 app/models 가 대신한다)
import product_schema  # noqa: E402  (VIEWS/SEEDS 재사용용)

# 테이블 -> CSV 경로. **순서를 적지 않는다.** 적재 순서는 resolve_order() 가 FK 관계에서 계산한다.
SOURCES = {
    # --- 마스터: 사람이 채운다. 재생성하지 않는다 ---
    "allergen": MASTER_DIR / "allergen.csv",
    "breed": MASTER_DIR / "breed.csv",
    "ingredient": MASTER_DIR / "ingredient.csv",
    "ingredient_allergen": MASTER_DIR / "ingredient_allergen.csv",
    # --- 합성: gen_seed.py 가 시드 고정으로 뽑는다 ---
    "user": SEED_DIR / "user.csv",
    "pet": SEED_DIR / "pet.csv",
    "pet_breed": SEED_DIR / "pet_breed.csv",
    "pet_allergy": SEED_DIR / "pet_allergy.csv",
    "product": SEED_DIR / "product.csv",
    "product_animal_category": SEED_DIR / "product_animal_category.csv",
    "product_nutrition": SEED_DIR / "product_nutrition.csv",
    "product_feeding_purpose": SEED_DIR / "product_feeding_purpose.csv",
    "product_ingredient": SEED_DIR / "product_ingredient.csv",
    "purchase": SEED_DIR / "purchase.csv",
    "review": SEED_DIR / "review.csv",
}

# animal_category / product_category / feeding_purpose 는 여기 없다 — seed_lookup_tables() 가 넣는다.
# CSV 로 또 빼면 같은 값이 두 군데에 앉는다.


# ---------------------------------------------------------------------------
# 스키마 - app/models 가 단일 원천


def create_views(conn):
    for ddl in product_schema.VIEWS:
        conn.execute(text(ddl))


# product_schema.VIEWS가 CREATE VIEW로 만드는 뷰 이름. Base.metadata.drop_all()은 ORM 테이블만
# 알아서, 뷰가 테이블을 참조하는 채로 두면 DROP TABLE이 DependentObjectsStillExist로 막힌다 -
# drop_all보다 먼저 뷰부터 지운다. product_schema.py:212-218 순서(자식 뷰 먼저)와 맞춘다.
VIEW_NAMES = ("v_safe_products", "v_product_safety")


def drop_views(conn):
    for name in VIEW_NAMES:
        conn.execute(text(f"DROP VIEW IF EXISTS {name}"))


SEED_SQL = re.compile(r"INSERT INTO (\w+)\(([^)]+)\)")


def seed_lookup_tables(conn):
    """
    # Summary
    * animal_category / product_category / feeding_purpose 코드표를 채운다
    # info
    * *_schema.py 의 SEEDS 를 그대로 쓴다
    # params
    * conn: 쓸 DB 커넥션
    # examples
    * conn -> *_schema.py 의 SEEDS INSERT 문에서 테이블·컬럼명을 뽑아 ORM insert 로 실행
    * -> animal_category / product_category / feeding_purpose 가 채워짐
    """
    for sql, rows in common_schema.SEEDS + product_schema.SEEDS:
        m = SEED_SQL.match(sql)
        table_name, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
        table = Base.metadata.tables[table_name]
        conn.execute(insert(table), [dict(zip(cols, row)) for row in rows])


# ---------------------------------------------------------------------------
# 순서 계산 — 무엇을 먼저 INSERT 해야 하는가


def topo_sort(items, key_of, deps_of, what):
    """
    # Summary
    * 의존 대상이 먼저 오도록 정렬한다(위상 정렬)
    # info
    * 테이블 순서 자체는 SQLAlchemy 가 계산해주지만,
      한 테이블 안의 자기참조 행 순서(allergen.parent_id)는 이걸로 직접 푼다
    # params
    * items: 정렬할 항목들
    * key_of: 항목 -> 그 항목의 키
    * deps_of: 항목 -> 먼저 와야 하는 키 집합
    * what: 순환 에러 메시지에 붙일 이름
    # examples
    * [c(부모 b), a(부모 없음), b(부모 a)] -> 의존이 풀린 것부터 차례로 꺼냄
    * -> [a, b, c]. 순환이 있으면 RuntimeError
    """
    pending = list(range(len(items)))
    done, out = set(), []
    while pending:
        ready = [i for i in pending if deps_of(items[i]) <= done]
        if not ready:
            stuck = ", ".join(str(key_of(items[i])) for i in pending[:5])
            raise RuntimeError(
                f"{what}: 순환하거나 없는 대상을 가리킨다 -> {stuck}" + (" ..." if len(pending) > 5 else "")
            )
        done |= {key_of(items[i]) for i in ready}
        out.extend(items[i] for i in ready)
        ready_set = set(ready)
        pending = [i for i in pending if i not in ready_set]
    return out


def resolve_order(names):
    """
    # Summary
    * names 의 테이블을 적재 순서대로 돌려준다
    # info
    * Base.metadata.sorted_tables 가 FK 기준으로 이미 위상 정렬해서 돌려준다
    # params
    * names: 적재할 테이블 이름 집합
    # examples
    * {'review', 'user', 'pet'} -> sorted_tables 순서로 거름
    * -> ['user', 'pet', 'review']
    """
    return [t.name for t in Base.metadata.sorted_tables if t.name in names]


def self_fk_column(table):
    """
    # Summary
    * 이 테이블 자신을 참조하는 FK 컬럼명. 없으면 None
    # params
    * table: SQLAlchemy Table
    # examples
    * allergen 테이블 -> 컬럼의 FK 중 자기 자신을 가리키는 것 찾기
    * -> 'parent_id'. 없는 테이블이면 None
    """
    for col in table.columns:
        for fk in col.foreign_keys:
            if fk.column.table.name == table.name:
                return col.name
    return None


def order_rows_parents_first(rows, pk, fk):
    """
    # Summary
    * 자기참조 테이블(allergen)의 행을 부모부터 나오도록 정렬한다
    # params
    * rows: CSV 에서 읽은 행들
    * pk: 기본키 컬럼명
    * fk: 부모를 가리키는 컬럼명
    # examples
    * allergen 행들, pk='allergen_id', fk='parent_id' -> topo_sort 로 정렬
    * -> 부모 행이 자식 행보다 앞에 오는 목록
    """
    return topo_sort(rows, lambda r: r[pk], lambda r: {r[fk]} if r[fk] else set(), f"{fk} 행 순서")


# ---------------------------------------------------------------------------


def load_table(conn, table_name, path):
    if not path.exists():
        raise FileNotFoundError(f"{path} 가 없다. python -m pipeline.make_data.gen_seed 를 먼저 돌린다.")

    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    table = Base.metadata.tables[table_name]
    cols = {c.name: (not c.nullable, c.default is not None or c.server_default is not None) for c in table.columns}

    # --- 헤더 검증 --- CSV 컬럼이 스키마와 어긋나면 조용히 깨지는 대신 여기서 막는다.
    unknown = [c for c in header if c not in cols]
    if unknown:
        raise ValueError(f"{path.name}: {table_name} 에 없는 컬럼 {unknown}")
    missing = [
        c for c, (notnull, has_default) in cols.items() if c not in header and notnull and not has_default
    ]
    if missing:
        raise ValueError(f"{path.name}: NOT NULL 인데 CSV 에 없는 컬럼 {missing}")

    # 자기참조 테이블은 행 순서도 맞춰야 한다.
    fk = self_fk_column(table)
    if fk:
        pk = list(table.primary_key.columns)[0].name
        rows = order_rows_parents_first(rows, pk, fk)

    # 빈 칸 -> NULL 이 유일한 변환이다. 숫자 캐스팅은 DB 가 INSERT 시점에 검증한다.
    dict_rows = [{c: (r[c] if r[c] != "" else None) for c in header} for r in rows]
    conn.execute(insert(table), dict_rows)

    omitted = [c for c in cols if c not in header]
    note = f"   (기본값에 맡긴 컬럼: {', '.join(omitted)})" if omitted else ""
    print(f"  {table_name:30} {len(rows):>6}행{note}")
    return len(rows)


def verify(conn):
    """
    # Summary
    * 적재 후 검사. 여기를 통과해야 데이터가 쓸 수 있는 상태다
    # info
    * FK 위반은 Postgres 가 INSERT 시점에 즉시 거부하므로(SQLite 의 사후 PRAGMA 검사와 다르다)
      여기서는 데이터 분포만 본다
    # params
    * conn: 읽을 DB 커넥션
    # examples
    * conn -> v_product_safety 판정별 개수, Safe 후보가 0개인 활성 펫 수를 셈
    * -> 화면 출력만. 판정이 3종류 미만이거나 후보 없는 펫이 10% 넘으면 [경고]
    """
    verdicts = dict(conn.execute(text("SELECT verdict, count(*) FROM v_product_safety GROUP BY verdict")).all())
    print(
        "v_product_safety 전체: "
        + " / ".join(f"{v} {verdicts.get(v, 0)}쌍" for v in ("Safe", "None", "WARN"))
    )
    if len(verdicts) < 3:
        print(f"[경고] verdict 가 {len(verdicts)}종류뿐이다. 3분법을 시험할 수 없는 데이터다.")

    starved = conn.execute(text("""
        SELECT count(*) FROM pet pt
         WHERE pt.inactive_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM v_safe_products v WHERE v.pet_id = pt.pet_id)
    """)).scalar()
    active = conn.execute(text("SELECT count(*) FROM pet WHERE inactive_at IS NULL")).scalar()
    print(f"활성 펫 {active}마리 중 Safe 후보 0개인 펫 {starved}마리")
    if active and starved > active * 0.1:
        print("[경고] 후보가 비는 펫이 너무 많다. 알러지를 상위 노드로 너무 자주 고르고 있다.")


def main():
    keep = "--keep" in sys.argv

    with engine.begin() as conn:
        if keep:
            print("기존 스키마 유지")
        else:
            print("스키마 재생성 (Supabase)")
            drop_views(conn)
            Base.metadata.drop_all(conn)
            Base.metadata.create_all(conn)
            create_views(conn)
            seed_lookup_tables(conn)

        order = resolve_order(set(SOURCES))
        print("\n[적재 순서] FK 관계에서 계산 — 손으로 적은 목록이 아니다")
        for i, t in enumerate(order, 1):
            print(f"  {i:>2}. {t}")

        print("\n[적재]")
        total = 0
        for table_name in order:
            total += load_table(conn, table_name, SOURCES[table_name])
        print(f"  {'합계':30} {total:>6}행")

        verify(conn)


if __name__ == "__main__":
    main()
