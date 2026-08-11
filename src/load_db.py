# Last updated: 2026-08-11
# CSV(구매/리뷰 더미 데이터)를 읽어 SQLite DB의 purchases 테이블로 적재하는 스크립트
import csv
import sqlite3
from pathlib import Path

DATA_DIR = Path('data')

con = sqlite3.connect('selectory.db')
cur = con.cursor()

def infer_column_type(values):
    """빈 문자열을 제외한 값이 전부 정수/실수로 읽히면 그 타입, 아니면 TEXT."""
    seen = [v for v in values if v != '']
    if seen and all(v.lstrip('-').isdigit() for v in seen):
        return 'INTEGER'
    try:
        if seen:
            [float(v) for v in seen]
            return 'REAL'
    except ValueError:
        pass
    return 'TEXT'


def _self_check():
    assert infer_column_type(['1', '2', '']) == 'INTEGER'
    assert infer_column_type(['1.5', '2']) == 'REAL'
    assert infer_column_type(['abc', '1']) == 'TEXT'
    assert infer_column_type(['010-1234-5678']) == 'TEXT'


_self_check()


def load_csv(path):
    table = path.stem
    with open(path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return

    cols = list(rows[0])
    types = [infer_column_type([row[c] for row in rows]) for c in cols]
    # 각 CSV의 첫 컬럼은 관례상 *_id 이므로 그대로 PRIMARY KEY로 사용
    col_defs = ', '.join(
        f'"{c}" {t}' + (' PRIMARY KEY' if i == 0 else '')
        for i, (c, t) in enumerate(zip(cols, types))
    )

    cur.execute(f'DROP TABLE IF EXISTS "{table}"')
    cur.execute(f'CREATE TABLE "{table}" ({col_defs})')

    marks = ','.join(['?'] * len(cols))
    values = [tuple(row[c] for c in cols) for row in rows]
    cur.executemany(f'INSERT INTO "{table}" VALUES ({marks})', values)
    print(f'{table}: {len(rows)} rows')


for csv_path in sorted(DATA_DIR.glob('*.csv')):
    load_csv(csv_path)

con.commit()
con.close()




