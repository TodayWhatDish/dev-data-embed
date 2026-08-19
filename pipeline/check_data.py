# Last updated: 2026-08-17
# pet_reco.db 에 적재된 더미데이터가 서로 앞뒤가 맞는지 검사하는 스크립트
#
# 이 검사가 필요한 이유는, 데이터가 어긋나도 파이프라인이 에러를 내지 않기 때문이다.
# FK 조인은 pet_id / product_id 로 조용히 성립하고, build_index.py 는 읽은 값을 그대로
# 문장으로 만들어 인코딩한다. 그래서 "소형견 39kg 셰퍼드" 같은 문장이 아무 경고 없이
# 벡터가 되고, 그 벡터가 RAG 근거로 LLM에 넘어가 모순된 답의 재료가 된다.
# 검색 결과를 눈으로 보기 전까지는 아무도 모른다.
#
# search.py 의 check_freshness() 가 "색인이 데이터보다 낡았는가"를 보는 것과 짝이다.
# 이쪽은 그 앞 단계, "데이터 자체가 말이 되는가"를 본다.
#
# 실행 위치는 load_db.py 다음, build_index.py 앞이다.
#   python src/load_db.py
#   python src/check_data.py    # <- 여기
#   python src/build_index.py
#
# sentence_transformers 를 import 하지 않으므로 torch 없이 돈다(load_db.py 와 동일).
# 그래서 search.py 의 fmt_purchase_id() 를 재사용하지 않고 아래에 다시 적었다.
# 그 파일을 import 하면 검사 한 번에 torch 로딩 6.5초를 치르게 된다.
import sqlite3
import sys
from collections import defaultdict

from app.config import DB_PATH,INDEX_FILTER

# 검사 결과의 심각도.
#   ERROR - 이 상태로 색인하면 잘못된 근거가 만들어진다. 고치기 전에는 진행하면 안 된다.
#   WARN  - 알고는 있어야 하지만 색인을 막을 정도는 아니다. 설계 미확정이거나 소수 사례.
# 전부 ERROR 로 두면 데이터를 손보는 중에 파이프라인이 통째로 막혀서 아무것도 못 하게 된다.
ERROR = 'ERROR'
WARN = 'WARN'

# 체급 경계(kg). 실제 데이터 분포가 소형 2.0~7.0 / 중형 8.1~19.8 / 대형 21.0~39.8 이라
# 7~8, 20~21 구간이 비어 있다. 경계를 8 과 20 으로 잡으면 어느 쪽도 억울하지 않다.
SIZE_BANDS = {
    '소형': (0.0, 8.0),
    '중형': (8.0, 20.0),
    '대형': (20.0, 999.0),
}

# 나이대 경계(년). 데이터가 퍼피 0.3~0.9 / 성견 1.0~6.9 / 시니어 8.1~13.9 로
# 7~8 구간이 비어 있다. 경계는 1.0 과 7.0 으로 잡는다.
AGE_BANDS = {
    '퍼피': (0.0, 1.0),
    '성견': (1.0, 7.0),
    '시니어': (7.0, 99.0),
}

# 견종별 기대 체급. 체중↔체급 검사만으로는 "체중과 체급은 서로 맞는데 견종이 엉뚱한" 경우
# (예: 25kg 로 적힌 치와와)를 못 잡아서 따로 둔다.
# 여기 없는 견종이 나오면 ERROR 가 아니라 WARN 이다. 데이터가 새 견종을 들여왔을 뿐인데
# 검사가 실패하면, 표를 갱신하기 귀찮아서 검사 자체를 꺼버리게 된다.
BREED_SIZE = {
    '말티즈': '소형', '포메라니안': '소형', '비숑프리제': '소형', '시츄': '소형',
    '치와와': '소형', '요크셔테리어': '소형', '토이푸들': '소형', '푸들': '소형',
    '미니어처닥스훈트': '소형',
    '비글': '중형', '시바견': '중형', '웰시코기': '중형', '보더콜리': '중형',
    '코커스패니얼': '중형', '코카스파니얼': '중형', '프렌치불독': '중형',
    '골든리트리버': '대형', '래브라도리트리버': '대형', '진돗개': '대형',
    '셰퍼드': '대형', '도베르만': '대형', '허스키': '대형',
}

# 리뷰 본문에서 "내 개가 이 체급이다"라고 스스로 밝히는 표현.
# '{}견용' 은 "소형견용 작은 사이즈로 찾다가", '{}견이라' 는 "대형견이라 그런지 사료값이" 꼴이다.
#
# 반면 '크기가 적당해서 소형견도 먹기 편해요' 류는 일부러 넣지 않았다. 대형견 주인이 상품을
# 일반적으로 평한 문장이지 자기 개가 소형견이라는 뜻이 아니고, 실제 리뷰에도 흔한 표현이다.
# (2026-08-17 작업에서 이 구분으로 30건을 고치고 26건을 남겨뒀다. docu/WORK.md 참고)
SELF_REF_PATTERNS = ['{}견용', '{}견이라']

SIZES = ('소형', '중형', '대형')


def fmt_purchase_id(pid):
    """정수 purchase_id 를 원래 표기로 되돌린다. 418 -> 'O00418'

    search.py 에 같은 함수가 있지만 import 하지 않는다. 파일 맨 위 주석 참고.
    """
    return f'O{pid:05d}'


def samples(rows, limit=3):
    """문제 사례 몇 개를 한 줄로 요약한다. 전부 찍으면 출력이 수백 줄이 된다."""
    shown = ', '.join(str(r) for r in rows[:limit])
    return shown + (f' ... (외 {len(rows) - limit}건)' if len(rows) > limit else '')


# --------------------------------------------------------------------------
# 검사 1. 참조 무결성
# --------------------------------------------------------------------------

def check_foreign_keys(con):
    """FK 로 쓰이는 ID가 상대 테이블에 실제로 있는지 본다.

    SQLite 는 PRAGMA foreign_keys 를 켜지 않으면 FK 를 강제하지 않고,
    load_db.py 는 켜지 않는다(CSV 적재 순서에 얽매이지 않으려는 선택).
    그래서 없는 ID를 가리켜도 적재가 성공한다.
    """
    found = []
    pairs = [
        ('pet_purchases', 'pet_id', 'pet_profiles', 'pet_id'),
        ('pet_purchases', 'product_id', 'pet_products', 'product_id'),
        ('pet_purchases', 'customer_id', 'pet_customers', 'customer_id'),
        ('pet_profiles', 'customer_id', 'pet_customers', 'customer_id'),
    ]
    for table, col, ref_table, ref_col in pairs:
        n = con.execute(f"""
            SELECT COUNT(*) FROM {table} AS t
            WHERE t.{col} IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM {ref_table} AS r WHERE r.{ref_col} = t.{col})
        """).fetchone()[0]
        if n:
            found.append((ERROR, f'{table}.{col} -> {ref_table}.{ref_col} 참조 실패 {n}건'))
    return '참조 무결성', found


# --------------------------------------------------------------------------
# 검사 2. 테이블 간 값 일치 (비정규화된 컬럼)
# --------------------------------------------------------------------------

def check_denormalized(con):
    """pet_purchases 에 복사돼 있는 반려견 정보가 pet_profiles 원본과 같은지 본다.

    pet_purchases 는 리뷰 작성 시점의 상태(breed/size_category/weight_kg/allergy)를
    일부러 비정규화해서 들고 있다. 프로필은 시간에 따라 변하지만 리뷰는 "그때 그 강아지"의
    이야기여야 하기 때문이다(src/src.md).

    다만 더미데이터는 시간 변화를 모사하지 않으므로 두 값이 같아야 정상이다.
    여기가 어긋나면 두 CSV가 서로 다른 생성 스크립트에서 나왔다는 뜻이고, 그때는
    pet_id 조인이 성립해도 내용상 남남이라 프로필 기반 추천의 전제가 무너진다.
    """
    found = []

    n = con.execute("""
        SELECT COUNT(*) FROM pet_purchases p JOIN pet_profiles f ON f.pet_id = p.pet_id
        WHERE p.breed <> f.breed
    """).fetchone()[0]
    if n:
        rows = con.execute("""
            SELECT p.purchase_id, p.breed, f.breed FROM pet_purchases p
            JOIN pet_profiles f ON f.pet_id = p.pet_id WHERE p.breed <> f.breed LIMIT 3
        """).fetchall()
        found.append((ERROR, f'breed 불일치 {n}건 — ' + samples(
            [f'{fmt_purchase_id(r[0])} 구매={r[1]}/프로필={r[2]}' for r in rows])))

    n = con.execute("""
        SELECT COUNT(*) FROM pet_purchases p JOIN pet_profiles f ON f.pet_id = p.pet_id
        WHERE p.weight_kg <> f.weight_kg
    """).fetchone()[0]
    if n:
        found.append((ERROR, f'weight_kg 불일치 {n}건'))

    # allergy 는 문자열을 그대로 비교할 수 없다. pet_purchases 는 '닭고기 알레르기' 같은
    # 문구, pet_profiles 는 '닭고기' 같은 성분명이라 표기 체계가 다르다.
    # 그래서 "프로필의 알레르겐이 구매쪽 문구 안에 들어있는가"로 느슨하게 본다.
    n = con.execute("""
        SELECT COUNT(*) FROM pet_purchases p JOIN pet_profiles f ON f.pet_id = p.pet_id
        WHERE CASE
            WHEN f.allergies IS NULL OR f.allergies = '없음' THEN p.allergy IS NOT NULL
            ELSE p.allergy IS NULL OR INSTR(p.allergy, f.allergies) = 0
        END
    """).fetchone()[0]
    if n:
        found.append((ERROR, f'allergy 불일치 {n}건 (프로필의 알레르겐이 구매쪽 문구에 없음)'))

    n = con.execute("""
        SELECT COUNT(*) FROM pet_purchases p JOIN pet_products r ON r.product_id = p.product_id
        WHERE p.category <> r.category
    """).fetchone()[0]
    if n:
        found.append((ERROR, f'category 불일치 {n}건 (구매 기록 vs 상품 마스터)'))

    return '테이블 간 값 일치', found


def check_vocabulary(con):
    """같은 개념을 두 테이블이 같은 낱말로 부르는지 본다.

    한쪽에만 있는 견종이 나오면 표기 흔들림(코카스파니얼/코커스패니얼)이거나
    아예 다른 견종 풀에서 뽑았다는 뜻이다. 어느 쪽이든 프로필↔구매 매칭이 깨진다.
    """
    found = []
    pu = {r[0] for r in con.execute('SELECT DISTINCT breed FROM pet_purchases WHERE breed IS NOT NULL')}
    pf = {r[0] for r in con.execute('SELECT DISTINCT breed FROM pet_profiles WHERE breed IS NOT NULL')}

    if pu - pf:
        found.append((ERROR, f'pet_purchases 에만 있는 견종 {len(pu - pf)}종: ' + ' '.join(sorted(pu - pf))))
    if pf - pu:
        found.append((ERROR, f'pet_profiles 에만 있는 견종 {len(pf - pu)}종: ' + ' '.join(sorted(pf - pu))))

    # 서로 비슷하게 쓰인 표현을 찾아 알려준다. SQL 필터로 값을 지정할 때 걸린다.
    # (임베딩 자체는 표현이 흔들려도 의미가 비슷하면 견디므로 WARN 이다.)
    #
    # 묶음마다 한 줄씩 찍으면 health_condition 하나로 30줄이 나와서 다른 검사 결과가 묻힌다.
    # 컬럼당 한 줄로 요약하고 가장 큰 묶음만 예시로 보여준다.
    for table, col in [('pet_purchases', 'health_condition'), ('pet_purchases', 'allergy')]:
        values = [r[0] for r in con.execute(
            f'SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL')]
        groups = defaultdict(list)
        for v in values:
            # 앞 3글자가 같으면 같은 뜻의 변형으로 본다.
            # '허리가 약함' / '허리가 약한 편' / '허리가 약한 편임' 을 한 묶음으로 잡는 정도의 거친 기준이다.
            groups[v[:3]].append(v)

        variants = sorted((v for v in groups.values() if len(v) > 1), key=len, reverse=True)
        if variants:
            found.append((WARN,
                          f'{table}.{col} 표기 흔들림 — {len(values)}종 중 {len(variants)}개 묶음이 '
                          f'같은 뜻의 변형으로 보입니다. 가장 큰 묶음({len(variants[0])}종): '
                          + ' / '.join(sorted(variants[0]))))

    return '어휘 일치', found


# --------------------------------------------------------------------------
# 검사 3. 행 내부 정합성
# --------------------------------------------------------------------------

def check_size_weight(con):
    """체급과 체중이 서로 맞는지 본다. 물리적으로 모순이면 리뷰 전체를 믿을 수 없다."""
    found = []
    rows = con.execute("""
        SELECT purchase_id, breed, size_category, weight_kg FROM pet_purchases
        WHERE size_category IS NOT NULL AND weight_kg IS NOT NULL
    """).fetchall()

    bad = []
    unknown_size = set()
    for pid, breed, size, weight in rows:
        band = SIZE_BANDS.get(size)
        if band is None:
            unknown_size.add(size)
            continue
        low, high = band
        if not (low <= weight < high):
            bad.append(f'{fmt_purchase_id(pid)} {breed} {size}견 {weight}kg')

    if bad:
        found.append((ERROR, f'체급↔체중 모순 {len(bad)}건 — ' + samples(bad)))
    if unknown_size:
        found.append((ERROR, f'정의되지 않은 size_category: {" ".join(sorted(unknown_size))}'))
    return '체급 ↔ 체중', found


def check_breed_size(con):
    """견종과 체급이 서로 맞는지 본다. 체중↔체급이 둘 다 맞아도 견종이 엉뚱할 수 있다."""
    found = []
    bad, unknown = [], set()
    for pid, breed, size in con.execute(
            'SELECT purchase_id, breed, size_category FROM pet_purchases WHERE breed IS NOT NULL'):
        expected = BREED_SIZE.get(breed)
        if expected is None:
            unknown.add(breed)
        elif expected != size:
            bad.append(f'{fmt_purchase_id(pid)} {breed}={size}견(기대 {expected})')

    if bad:
        found.append((ERROR, f'견종↔체급 모순 {len(bad)}건 — ' + samples(bad)))
    if unknown:
        # BREED_SIZE 표에 없는 견종. 데이터가 늘었을 뿐일 수 있으므로 막지 않는다.
        found.append((WARN, f'BREED_SIZE 표에 없는 견종 {len(unknown)}종: ' + ' '.join(sorted(unknown))
                            + ' — check_data.py 의 표를 갱신하세요'))
    return '견종 ↔ 체급', found


def check_age_group(con):
    """나이대와 나이(년)가 서로 맞는지 본다."""
    found = []
    bad, unknown = [], set()
    for pid, group, years in con.execute("""
            SELECT purchase_id, age_group, age_years FROM pet_purchases
            WHERE age_group IS NOT NULL AND age_years IS NOT NULL"""):
        band = AGE_BANDS.get(group)
        if band is None:
            unknown.add(group)
            continue
        low, high = band
        if not (low <= years < high):
            bad.append(f'{fmt_purchase_id(pid)} {group} {years}세')

    if bad:
        found.append((ERROR, f'나이대↔나이 모순 {len(bad)}건 — ' + samples(bad)))
    if unknown:
        found.append((ERROR, f'정의되지 않은 age_group: {" ".join(sorted(unknown))}'))
    return '나이대 ↔ 나이', found


def check_product_form(con):
    """상품의 하위 분류와 급여 형태가 맞는지 본다. '건식사료'인데 target_food_form='습식'인 경우.

    덴탈껌·트릿·실버사료에 건식/습식/공용이 섞이는 것은 정상이다(실제로 두 형태가 다 나온다).
    이름이 형태를 직접 지정하는 건식사료/습식사료만 본다.
    """
    found = []
    rows = con.execute("""
        SELECT product_id, sub_category, target_food_form FROM pet_products
        WHERE (sub_category = '건식사료' AND target_food_form NOT IN ('건식', '공용'))
           OR (sub_category = '습식사료' AND target_food_form NOT IN ('습식', '공용'))
    """).fetchall()
    if rows:
        found.append((ERROR, f'상품 형태 모순 {len(rows)}건 — ' + samples(
            [f'F{r[0]:04d} {r[1]}인데 {r[2]}' for r in rows])))
    return '상품 분류 ↔ 급여 형태', found


# --------------------------------------------------------------------------
# 검사 4. 리뷰 본문 정합성
# --------------------------------------------------------------------------

def check_review_size_mention(con):
    """리뷰 본문이 스스로 밝힌 체급과 행의 size_category 가 맞는지 본다.

    이게 어긋나면 build_doc() 이 만든 문장 하나가 자기모순이 된다.
    ("대형견 성견 진돗개 ... 후기: 소형견용 작은 사이즈로 찾다가 발견했어요.")
    LLM에 근거로 넘어가면 그대로 모순된 답이 나오고, 프롬프트로는 못 막는다.
    """
    found = []
    bad = []
    for pid, size, review in con.execute("""
            SELECT purchase_id, size_category, review FROM pet_purchases
            WHERE review IS NOT NULL AND TRIM(review) <> ''"""):
        for mentioned in SIZES:
            if mentioned == size:
                continue
            for pattern in SELF_REF_PATTERNS:
                if pattern.format(mentioned) in review:
                    bad.append(f'{fmt_purchase_id(pid)} {size}견 행에 "{pattern.format(mentioned)}"')

    if bad:
        found.append((ERROR, f'리뷰 본문↔체급 모순 {len(bad)}건 — ' + samples(bad)))
    return '리뷰 본문 ↔ 체급', found


# --------------------------------------------------------------------------
# 검사 5. 추천 신호 (DATAINFO.md 4.1)
# --------------------------------------------------------------------------

def collides(allergy, ingredients):
    """이 구매가 알레르기 충돌인지 본다.

    allergy 는 '닭고기 알레르기' 같은 문구, ingredients 는 '닭고기|고구마' 같은 목록이라
    "성분명이 알레르기 문구 안에 들어있는가"로 판정한다.
    """
    if not allergy or not ingredients:
        return False
    return any(item in allergy for item in ingredients.split('|'))


def check_allergy_matchable(con):
    """알레르기 값이 애초에 성분과 매칭될 수 있는 낱말인지 본다.

    '특정 단백질 민감' 이나 '피부 알레르기 체질' 같은 값은 어떤 성분명과도 겹치지 않는다.
    이런 값이 섞여 있으면 알레르기 안전 판정이 조용히 "충돌 없음"으로 넘어간다.
    GOAL.md 가 내세운 "알러지 안전 여부"가 걸려 있는 자리라 그냥 두면 안 된다.
    """
    found = []
    pool = set()
    for (ing,) in con.execute('SELECT ingredients FROM pet_products WHERE ingredients IS NOT NULL'):
        pool.update(ing.split('|'))

    dead = []
    for allergy, n in con.execute("""
            SELECT allergy, COUNT(*) FROM pet_purchases
            WHERE allergy IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""):
        if not any(item in allergy for item in pool):
            dead.append(f'{allergy}({n}건)')

    if dead:
        found.append((ERROR, f'어떤 성분과도 매칭될 수 없는 알레르기 값 {len(dead)}종: ' + ', '.join(dead)))
    return '알레르기 매칭 가능성', found


def check_rating_signal(con):
    """별점이 "조건이 얼마나 맞았는가"의 결과인지 본다 (DATAINFO.md 4.1).

    DATAINFO.md 는 별점을 추천 로직의 핵심 재료라고 못박고, 알레르기 충돌 시 평균 1.82,
    목적·형태 완전 매칭 시 4.48 이라고 적어뒀다. 이 신호가 실제로 데이터에 들어있지 않으면
    별점을 근거로 삼는 추천 로직 전체가 근거를 잃는다.

    통계 검정까지는 하지 않는다. 명세가 2점 넘게 벌어진다고 했으므로 평균 차이 1.0 을
    기준으로 "신호가 있다/없다" 정도만 거칠게 판정한다.
    """
    found = []
    rows = con.execute("""
        SELECT p.allergy, r.ingredients, p.rating FROM pet_purchases p
        JOIN pet_products r ON r.product_id = p.product_id WHERE p.rating IS NOT NULL
    """).fetchall()

    hit = [rating for allergy, ing, rating in rows if collides(allergy, ing)]
    base = [rating for allergy, ing, rating in rows if not collides(allergy, ing)]

    if len(hit) < 30:
        # 표본이 이만큼도 안 되면 평균을 비교할 수 없다. 매칭 자체가 안 되고 있다는 신호이기도 하다.
        found.append((ERROR, f'알레르기 충돌이 {len(hit)}건뿐이라 신호를 측정할 수 없음 '
                             f'(전체 {len(rows)}건) — 알레르기 값과 성분명의 표기 체계를 확인하세요'))
    else:
        avg_hit, avg_base = sum(hit) / len(hit), sum(base) / len(base)
        line = f'알레르기 충돌 {len(hit)}건 평균 {avg_hit:.2f} / 그 외 {len(base)}건 평균 {avg_base:.2f}'
        if avg_base - avg_hit < 1.0:
            found.append((ERROR, f'{line} — 충돌 시 별점이 떨어지지 않음 '
                                 f'(DATAINFO.md 4.1 명세: 1.82 vs 3.78)'))
        else:
            found.append((WARN, f'{line} — 신호 확인됨'))

    # 목적·형태 매칭 신호. 프로필 쪽 컬럼을 봐야 해서 pet_profiles 를 조인한다.
    # 위 check_denormalized 가 실패하는 동안에는 이 수치도 믿을 수 없다.
    matched, unmatched = [], []
    for purpose, form, target_purpose, target_form, rating in con.execute("""
            SELECT f.feeding_purpose, f.food_form_preference,
                   r.target_feeding_purpose, r.target_food_form, p.rating
            FROM pet_purchases p
            JOIN pet_profiles f ON f.pet_id = p.pet_id
            JOIN pet_products r ON r.product_id = p.product_id
            WHERE p.rating IS NOT NULL"""):
        ok_purpose = target_purpose == '공용' or target_purpose == purpose
        ok_form = target_form == '공용' or form == '혼합' or target_form == form
        (matched if ok_purpose and ok_form else unmatched).append(rating)

    if matched and unmatched:
        avg_m, avg_u = sum(matched) / len(matched), sum(unmatched) / len(unmatched)
        line = f'목적·형태 매칭 {len(matched)}건 평균 {avg_m:.2f} / 비매칭 {len(unmatched)}건 평균 {avg_u:.2f}'
        if avg_m - avg_u < 0.5:
            found.append((ERROR, f'{line} — 매칭돼도 별점이 오르지 않음 '
                                 f'(DATAINFO.md 4.1 명세: 4.48 vs 3.78)'))
        else:
            found.append((WARN, f'{line} — 신호 확인됨'))

    return '별점 신호 (DATAINFO.md 4.1)', found


# --------------------------------------------------------------------------
# 검사 6. 색인 대상 상태
# --------------------------------------------------------------------------

def check_index_target(con):
    """build_index.py 가 실제로 무엇을 색인하게 되는지 확인한다."""
    found = []
    total = con.execute('SELECT COUNT(*) FROM pet_purchases').fetchone()[0]
    target = con.execute(f'SELECT COUNT(*) FROM pet_purchases AS p WHERE {INDEX_FILTER}').fetchone()[0]
    found.append((WARN, f'전체 {total}건 중 색인 대상 {target}건'))

    if target == 0:
        found.append((ERROR, '색인 대상이 0건입니다. INDEX_FILTER 조건을 확인하세요.'))

    # is_holdout 은 DATAINFO.md 상 "반려견별 가장 최근 구매 1건만 1" 이어야 한다.
    # 다만 현재 전량 0 인 것은 평가 설계가 아직 정해지지 않아서지 데이터가 깨진 게 아니다.
    # 여기서 ERROR 를 내면 "고쳐야 할 손상"으로 오해하게 되므로 WARN 으로 알리기만 한다.
    holdout = con.execute('SELECT COUNT(*) FROM pet_purchases WHERE is_holdout = 1').fetchone()[0]
    if holdout == 0:
        found.append((WARN, 'is_holdout 이 전량 0 입니다. 평가셋이 없어 추천 성능을 수치로 잴 수 없습니다 '
                            '(평가 설계 미확정 — 데이터 손상이 아닙니다).'))
    else:
        pets = con.execute('SELECT COUNT(DISTINCT pet_id) FROM pet_purchases').fetchone()[0]
        if holdout != pets:
            found.append((WARN, f'is_holdout={holdout}건 인데 반려견은 {pets}마리입니다. '
                                'DATAINFO.md 명세는 반려견별 1건입니다.'))

    empty = con.execute("""
        SELECT COUNT(*) FROM pet_purchases WHERE review IS NULL OR TRIM(review) = ''
    """).fetchone()[0]
    if empty:
        found.append((WARN, f'빈 리뷰 {empty}건 (색인에서 제외됨)'))

    return '색인 대상', found


CHECKS = [
    check_foreign_keys,
    check_denormalized,
    check_vocabulary,
    check_size_weight,
    check_breed_size,
    check_age_group,
    check_product_form,
    check_review_size_mention,
    check_allergy_matchable,
    check_rating_signal,
    check_index_target,
]


def main():
    # Windows 콘솔 기본 코드페이지에서 한글이 깨져 나오는 것을 막는다.
    # 검사 결과를 사람이 읽어야 하는데 깨지면 스크립트 자체가 쓸모없어진다.
    sys.stdout.reconfigure(encoding='utf-8')

    con = sqlite3.connect(DB_PATH)
    errors = 0
    warnings = 0

    for check in CHECKS:
        title, found = check(con)
        if not found:
            print(f'  [OK]    {title}')
            continue
        # 묶음 안에 ERROR 가 하나라도 있으면 FAIL, WARN 만 있으면 WARN 으로 표시한다.
        print(f'  [{"FAIL" if any(l == ERROR for l, _ in found) else "WARN"}]  {title}')
        for level, message in found:
            print(f'    {level:5s} {message}')
            if level == ERROR:
                errors += 1
            else:
                warnings += 1

    con.close()

    print()
    print(f'ERROR {errors}건 / WARN {warnings}건')
    if errors:
        print('데이터를 고친 뒤 다시 실행하세요. 이 상태로 색인하면 잘못된 근거가 만들어집니다.')
        return 1
    print('색인을 진행해도 됩니다: python src/build_index.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
