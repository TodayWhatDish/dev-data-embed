# Last Updated: 2026-08-25
"""
data/seed/*.csv 생성기 — 16테이블 스키마용 합성 개체 데이터.

    data/master/*.csv  (손으로 채운 마스터)
            │
            ▼
    gen_seed.py  ──> data/seed/*.csv  ──[load_csv.py]──> user.db

**마스터는 읽기만 한다.** allergen_id / breed_id / ingredient_id 가 바뀌면 손으로 넣은
ingredient_allergens 매핑이 통째로 깨지므로, 생성기가 마스터를 다시 쓰는 일은 없다.
합성분만 시드 고정으로 언제든 재생성한다.

CSV 규약
  - 파일 1개 = 테이블 1개. 헤더는 DDL 의 컬럼명·순서 그대로.
  - 다중값 컬럼을 만들지 않는다(옛 pet_products.ingredients 의 '|' 구분). 연결 테이블 행으로 푼다.
  - NULL 은 빈 칸. 로더가 '' -> None 으로 바꾼다.
  - UTF-8, BOM 없음. 옛 data/*.csv 4종에는 BOM 이 붙어 있으니 섞지 않는다.
  - 줄바꿈은 LF 고정. 재생성 시 diff 가 개행 차이로 오염되지 않게 한다.

DB 가 막지 못해 이 생성기가 책임지는 것 (docu/schema/ 에 "앱이 막는다"로 적힌 것들)
  1) pet_allergies 펼침 — 카테고리를 고르면 하위를 전부 넣고 고른 카테고리 행도 남긴다.
  2) 축종 정합성 — 개 pet 에 고양이 breed 를 붙여도 FK 는 통과한다. 여기서 막는다.
  3) UNIQUE — users.email, (auth_provider, auth_uid). breeds 는 마스터라 이미 유일.
  4) 판정 3분법이 실제로 관측되도록 분포를 섞는다 —
     ingredients_verified = 0 인 제품과 product_animal_category 0행 제품을 일부러 남긴다.
     전부 1 / 전부 1행이면 v_product_safety 의 None(판정불가) 분기가 한 번도 안 나온다.

실행: py src/make_data/gen_seed.py   (repo root 에서)
"""

import csv
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT / 'data' / 'master'
SEED_DIR = ROOT / 'data' / 'seed'
sys.path.insert(0, str(ROOT / 'src'))
from petcalc import age_months

# 시드를 고정한다. 재실행해도 같은 데이터가 나와야 벤치·평가가 비교 가능하다.
SEED = 20260812

N_USERS = 300
N_PRODUCTS = 200
N_ADDITIONAL_PURCHASES = 600

# 데이터의 '오늘'. date.today() 를 쓰면 재실행할 때마다 값이 흔들린다.
TODAY = date(2026, 8, 25)
SERVICE_OPEN = date(2023, 1, 1)
# 모든 타임스탬프의 상한. 이 시각보다 뒤인 값은 만들지 않는다.
NOW = datetime(2026, 8, 25, 23, 59, 59)

rng = random.Random(SEED)


# ---------------------------------------------------------------------------
# 잡다한 도구

def pick(weighted):
    """[(값, 가중치), ...] 에서 하나 고른다."""
    vals = [v for v, _ in weighted]
    wts = [w for _, w in weighted]
    return rng.choices(vals, weights=wts, k=1)[0]


def rdate(start, end):
    """start ~ end 사이 날짜 하나. 뒤집힌 구간이 들어와도 죽지 않게 막는다."""
    span = (end - start).days
    return start if span <= 0 else start + timedelta(days=rng.randint(0, span))


def as_dt(x, end_of_day=False):
    """date 를 datetime 으로 올린다. datetime 이면 그대로."""
    if isinstance(x, datetime):
        return x
    return datetime.combine(x, time.max if end_of_day else time.min)


def rdt(start, end):
    """start ~ end 사이 **datetime** 하나.

    옛 rdate() + dt() 조합은 날짜를 뽑은 뒤 시:분:초를 따로 무작위로 붙였다.
    그래서 시작과 끝이 같은 날이면 09:00 가입 -> 03:00 로그인 같은 역전이 생겼다
    (실측 10건). 날짜가 아니라 초 단위로 뽑으면 그 구멍이 아예 없어진다.

    뒤집힌 구간(end < start)은 start 로 눕힌다 — 호출부가 max() 로 하한을 거는 것을
    잊어도 최소한 순서가 깨지지는 않게 한다.
    """
    start, end = as_dt(start), as_dt(end, end_of_day=True)
    if end < start:
        return start
    return start + timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))


def dt(x):
    """datetime/date -> ISO-8601 문자열. SQLite 의 datetime() 이 파싱할 수 있어야 한다."""
    return as_dt(x).strftime('%Y-%m-%d %H:%M:%S')


def write_csv(name, header, rows):
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    path = SEED_DIR / f'{name}.csv'
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        for r in rows:
            w.writerow(['' if v is None else v for v in r])
    print(f'  {name + ".csv":34} {len(rows):>6}행')
    return len(rows)


def read_master(name):
    with (MASTER_DIR / f'{name}.csv').open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 마스터 로드 — 여기서 만든 ID 만 참조한다

allergen_rows = read_master('allergen')
breed_rows = read_master('breed')
ingredient_rows = read_master('ingredient')
ing_allergen_rows = read_master('ingredient_allergen')

# 알러지원 트리. 펼침(하위 재귀)은 앱이 하는 일이고, 이 생성기가 그 앱 역할을 한다.
ALLERGEN_CHILDREN = {}
ALLERGEN_NAME = {}
for r in allergen_rows:
    aid = int(r['allergen_id'])
    ALLERGEN_NAME[aid] = r['name_ko']
    ALLERGEN_CHILDREN.setdefault(aid, [])
    if r['parent_id']:
        ALLERGEN_CHILDREN.setdefault(int(r['parent_id']), []).append(aid)

ALLERGEN_LEAVES = [a for a in ALLERGEN_NAME if not ALLERGEN_CHILDREN.get(a)]
ALLERGEN_NODES = [a for a in ALLERGEN_NAME if ALLERGEN_CHILDREN.get(a)]


def descendants(aid):
    """aid 자신 + 모든 하위. pet_allergies 에 그대로 들어갈 집합이다."""
    out, stack = set(), [aid]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(ALLERGEN_CHILDREN.get(cur, ()))
    return out


# 축종별 품종 — 개 pet 에 고양이 품종이 붙는 것을 여기서 막는다.
BREEDS_BY_CATEGORY = {1: [], 2: []}
BREED_NAME = {}
for r in breed_rows:
    bid, cat = int(r['breed_id']), int(r['animal_category_id'])
    BREEDS_BY_CATEGORY[cat].append(bid)
    BREED_NAME[bid] = r['name_ko']

INGREDIENT_NAME = {int(r['ingredient_id']): r['name_ko'] for r in ingredient_rows}


# 품종별 (최소체중, 최대체중, size 코드). size 1 초소형 ~ 5 초대형.
# 체중과 size 는 서로 다른 질문에 답하므로(docu/schema/pet_schema.md) 굳이 일치시키지 않는다 —
# 아래 gen_pets() 가 일부 개체의 size 를 한 칸 흔든다.
BREED_BODY = {
    '말티즈': (2.0, 4.0, 1), '포메라니안': (2.0, 4.0, 1), '비숑프리제': (4.0, 7.0, 2),
    '푸들': (3.0, 8.0, 2), '시츄': (4.0, 8.0, 2), '치와와': (1.5, 3.0, 1),
    '웰시코기': (10.0, 14.0, 3), '시바견': (8.0, 12.0, 3), '진돗개': (15.0, 23.0, 3),
    '비글': (9.0, 14.0, 3), '코카스파니엘': (10.0, 15.0, 3), '골든리트리버': (25.0, 34.0, 4),
    '래브라도리트리버': (25.0, 36.0, 4), '보더콜리': (14.0, 20.0, 3),
    '요크셔테리어': (2.0, 3.5, 1), '닥스훈트': (4.0, 9.0, 2), '미니어처슈나우저': (5.0, 9.0, 2),
    '프렌치불독': (9.0, 13.0, 3), '시베리안허스키': (16.0, 27.0, 4), '저먼셰퍼드': (22.0, 40.0, 4),
    '사모예드': (16.0, 30.0, 4), '삽살개': (16.0, 26.0, 4), '풍산개': (17.0, 28.0, 4),
    '코리안숏헤어': (3.0, 5.0, 2), '러시안블루': (3.0, 5.5, 2), '페르시안': (3.0, 5.5, 2),
    '샴': (2.5, 4.5, 1), '스코티시폴드': (2.5, 6.0, 2), '브리티시숏헤어': (4.0, 8.0, 2),
    '먼치킨': (2.0, 4.0, 1), '노르웨이숲': (5.0, 9.0, 3), '벵갈': (4.0, 7.0, 2),
    '아메리칸숏헤어': (3.5, 7.0, 2), '터키시앙고라': (2.5, 5.0, 1), '랙돌': (5.0, 9.0, 3),
    '아비시니안': (3.0, 5.0, 2),
}
# 품종을 모르는 개체(pet_breeds 0행)의 기본 체중 범위.
DEFAULT_BODY = {1: (4.0, 20.0, 3), 2: (3.0, 6.0, 2)}


# 축종별 '품종을 몇 개 아는가' 분포. 행 수가 곧 뜻이다(pet_schema.md) —
# 0행 = 모른다(잡종 포함) / 1행 = 순혈 / 2행 이상 = 믹스.
#
# 고양이 쪽 0행을 개보다 낮게 잡는다. '코리안숏헤어'라는 포괄 명칭이 있어서
# 길에서 온 아이도 보호자는 코숏이라고 적는다 — 개의 '잡종'과 달리 이름이 있다.
# 같은 이유로 고양이는 믹스 개념도 개만큼 쓰이지 않는다.
BREED_COUNT_DIST = {
    1: [(0, 8), (1, 70), (2, 20), (3, 2)],    # 개
    2: [(0, 4), (1, 86), (2, 10), (3, 0)],    # 고양이
}

# 품종별 등장 가중치. 여기 없는 품종은 1 로 본다(= 개는 전부 균등).
#
# 균등하게 뽑으면 코리안숏헤어가 아비시니안과 같은 빈도로 나온다. 국내 반려묘 구성으로는
# 코숏이 압도적이어야 하는데, 실제로 브리티시숏헤어(12)보다 적게(8) 나오고 있었다.
# 개 쪽은 근거로 쓸 자료가 없어 균등으로 둔다 — 임의 가중치를 넣느니 균등인 편이 낫다.
BREED_WEIGHT = {
    '코리안숏헤어': 45, '러시안블루': 8, '스코티시폴드': 8, '페르시안': 6,
    '먼치킨': 6, '브리티시숏헤어': 5, '샴': 4, '노르웨이숲': 4,
    '아메리칸숏헤어': 4, '랙돌': 4, '벵갈': 3, '터키시앙고라': 2, '아비시니안': 1,
}


def pick_breeds(category, n):
    """가중치를 반영해 **서로 다른** 품종 n 개를 고른다(비복원 추출).

    rng.sample() 은 가중치를 못 받고 rng.choices() 는 중복을 허용한다.
    믹스는 같은 품종이 두 번 들어가면 안 되므로(복합 PK 가 막는다) 하나씩 뽑고 뺀다.
    """
    pool = list(BREEDS_BY_CATEGORY[category])
    wts = [BREED_WEIGHT.get(BREED_NAME[b], 1) for b in pool]
    out = []
    for _ in range(min(n, len(pool))):
        b = rng.choices(pool, weights=wts, k=1)[0]
        i = pool.index(b)
        pool.pop(i)
        wts.pop(i)
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# 값 풀 — 옛 data/*.csv 4종에서 실측한 분포를 재료로 쓴다

SURNAMES = ['김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
            '한', '오', '서', '신', '권', '황', '안', '송', '류', '전']
GIVEN = ['우미', '민환', '지훈', '서연', '도윤', '하은', '지우', '현우', '수아', '준서',
         '예린', '건우', '다인', '시우', '유진', '태현', '보람', '승민', '지아', '재원',
         '나연', '동현', '민준', '가온', '윤슬', '해린', '주원', '민서', '채원', '영호']

# 옛 pet_customers.csv 의 시/도 분포(서울 97 / 경기 58 / 인천 23 ...)를 그대로 옮겼다.
REGIONS = [('서울', 97), ('경기', 58), ('인천', 23), ('충남', 19), ('부산', 16),
           ('경남', 12), ('대구', 10), ('광주', 10), ('경북', 9), ('전북', 9),
           ('대전', 7), ('전남', 7), ('울산', 6), ('충북', 6), ('강원', 5),
           ('제주', 3), ('세종', 3)]

AUTH_PROVIDERS = [('local', 55), ('google', 25), ('kakao', 15), ('apple', 3), ('firebase', 2)]

EMAIL_DOMAINS = ['naver.com', 'gmail.com', 'daum.net', 'kakao.com']

PET_NAMES = ['초코', '보리', '코코', '별이', '두부', '모카', '까미', '루비', '뽀삐', '콩이',
             '마루', '단추', '설이', '망고', '나비', '호두', '떡볶이', '구름', '레오', '밤비',
             '쿠키', '베리', '달이', '순이', '가을', '토리', '삐삐', '봄이', '슈슈', '아톰',
             '먼지', '치즈', '감자', '방울', '탄이', '유리', '똘이', '해피', '라떼', '몽이']

BRANDS = ['멍푸드', '펫키친', '바크앤조이', '네이처독', '도그밀', '헬시포',
          '퍼피랩', '와일드포', '스노우독', '그레인프리랩', '캣테이블', '냥푸드']
CAT_BRANDS = BRANDS[-2:]
DOG_BRANDS = BRANDS[:-2]

# product_category 시드(product_schema.py)에 있는 ID 만 쓴다.
# 1 사료 / 2 간식 / 3 덴탈껌 / 4 트릿 / 5 수제간식
CATEGORY_LABEL = {1: '사료', 2: '간식', 3: '덴탈껌', 4: '트릿', 5: '수제간식'}
# feeding_purposes 시드: 1 관절 / 2 다이어트 / 3 피부 / 4 치아 / 5 신장 / 6 소화
PURPOSE_NAME = {1: '관절', 2: '다이어트', 3: '피부', 4: '치아', 5: '신장', 6: '소화'}

# 원료를 역할별로 나눠둔다. 아무거나 3~7개 뽑으면 '탈지분유 + 대구살 + 옥수수전분' 같은
# 실재하지 않는 조합이 나와서, 나중에 리뷰를 붙일 때 근거가 이상해진다.
#
# 뒤쪽 46~50 은 **복합 원료**다 — 하나가 알러지원을 여러 개 가리킨다.
# product_schema.md 가 ingredient_allergens 를 컬럼 하나가 아니라 다대다 테이블로 만든 이유가
# 이것이다("'베이커리 부산물'은 밀·계란·유제품이다. 컬럼이 하나면 밀만 적히고 계란과 유제품은
# 조용히 '안전'으로 통과한다"). 데이터에 복합 원료가 없으면 그 설계가 한 번도 시험되지 않는다.
# 51~57 은 '알러지원은 마스터에 있는데 그걸 가리키는 원료가 없던' 자리를 메운 것들이다.
# 게·땅콩·호밀·수수·인공색소는 실제 사료·간식에 흔한데 원료 목록에서 빠져 있어서,
# 보호자가 그 알러지를 골라도 걸러지는 제품이 0개였다 — 하드 필터가 무의미해진다.
ING_PROTEIN = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 47, 48, 51, 55]
ING_CARB = [23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 46, 49, 53, 54]
ING_SUPPLEMENT = [4, 13, 17, 18, 19, 20, 21, 22, 37, 38, 39, 40, 41, 42, 43, 44, 50, 52]
ING_ADDITIVE = [56, 57]  # 착색료·소르빈산칼륨 — 간식에 흔하다
ING_CAT_ONLY = [45]  # 타우린 — 고양이 사료의 필수 첨가

# 분류별 '보증성분표가 있을' 확률.
#
# 예전에는 분류를 안 보고 일괄 85% 였다. 그래서 사료 113개 중 14개가 성분표 없이 나왔는데,
# 사료관리법상 배합사료는 등록성분량(조단백·조지방·조섬유·조회분 등) 표시가 **의무**라
# 그런 사료는 유통될 수 없다. product_schema.md 도 결측의 방향을 명시해 뒀다 —
# "**사료는** 성분표가 있고 **간식은** 없는 경우가 흔하다."
# 결측 자체는 남겨야 한다(그게 이 표를 products 에서 분리한 이유다). 쏠리는 쪽만 바로잡는다.
NUTRITION_RATE = {
    1: 0.98,   # 사료 — 표시 의무. 빠지는 건 등록 누락 정도
    2: 0.70,   # 간식(대분류)
    3: 0.55,   # 덴탈껌 — 포장에 성분표가 없는 경우가 가장 흔하다
    4: 0.65,   # 트릿
    5: 0.60,   # 수제간식 — 소규모 제조라 표기가 자주 빠진다
}

SIZE_LABEL = {1: '초소형', 2: '소형', 3: '중형', 4: '대형', 5: '초대형'}
STAGE_LABEL = {'all': '전 연령', 'puppy': '유아기', 'senior': '노령기', 'adult': '성년기'}

FOOD_FORM_KCAL = {'건식': (330, 430), '습식': (70, 120), '동결건조': (400, 500),
                  '생식': (120, 200), '공용': (300, 400)}

# 제형별 (중량 하한g, 상한g, 100g당 단가 하한원, 상한원).
#
# **가격을 중량과 따로 뽑으면 안 된다.** 옛 pet_products.csv 의 범위(사료 15,000~89,000원 /
# 400~5,000g)를 그대로 베꼈더니 500g 짜리가 81,000원(100g당 16,200원)이고 4.7kg 짜리가
# 16,900원(100g당 360원)인 데이터가 나왔다 — 46배 차이다. schema/README.md 가
# "100g당 가격은 price_krw / weight_g 에서 나온다"고 파생값으로 못박아둔 이상,
# 그 파생값이 무의미하면 안 된다. 그래서 **중량을 먼저 뽑고 단가를 곱해** 가격을 만든다.
FOOD_SPEC = {
    '건식':     (400, 15000,  500,  1500),   # 대용량 포대가 이쪽에 있다
    '습식':     (80,   2000,  900,  2500),   # 파우치·캔이라 작고 100g당은 비싸다
    '동결건조': (200,   1200, 4000, 12000),
    '생식':     (300,   2000, 1500,  4000),
    '공용':     (400,   5000,  600,  1800),
}
TREAT_SPEC = {
    '건식':     (50, 500, 2000,  6000),
    '습식':     (40, 300, 2500,  7000),
    '동결건조': (30, 300, 5000, 15000),
    '생식':     (50, 400, 3000,  8000),
    '공용':     (50, 500, 2000,  6000),
}


# ---------------------------------------------------------------------------
# users

def gen_users():
    rows, emails, auth_keys, seen_uids, phones = [], set(), set(), [], []
    for uid in range(1, N_USERS + 1):
        provider = pick(AUTH_PROVIDERS)

        # uq_user_auth 가 단일이 아니라 (auth_provider, auth_uid) 복합 UNIQUE 인 이유는
        # "같은 uid 라도 제공자가 다르면 다른 계정"이기 때문이다(user_schema.md).
        # 데이터에 그 쌍이 하나도 없으면 복합으로 만든 이유가 시험되지 않으므로,
        # 소수는 이미 쓰인 uid 를 **다른 제공자로** 재사용한다.
        shareable = [u for u in seen_uids if (provider, u) not in auth_keys]
        if shareable and rng.random() < 0.04:
            auth_uid = rng.choice(shareable)
        else:
            while True:
                auth_uid = f'{rng.randrange(16 ** 12):012x}'
                if (provider, auth_uid) not in auth_keys:
                    break
            seen_uids.append(auth_uid)
        auth_keys.add((provider, auth_uid))

        while True:
            email = f'user{rng.randint(1000, 99999)}@{rng.choice(EMAIL_DOMAINS)}'
            if email not in emails:
                emails.add(email)
                break

        created = rdt(SERVICE_OPEN, TODAY - timedelta(days=14))

        # last_login_at 은 상태 컬럼이 아니라 '휴면'의 원천이다(docu/schema/user_schema.md).
        # 휴면 판정을 시험할 수 있도록 오래된 값도 섞는다.
        bucket = pick([('never', 5), ('dormant', 15), ('recent', 80)])
        if bucket == 'never':
            last_login = None
        elif bucket == 'dormant':
            # 마지막 로그인이 180일보다 오래됐다 = 현행 기준의 휴면
            last_login = rdt(created, TODAY - timedelta(days=180))
        else:
            last_login = rdt(max(created, as_dt(TODAY - timedelta(days=90))), NOW)

        # 탈퇴는 행 삭제가 아니라 시각 기록이다. NULL = 활성.
        # **탈퇴한 뒤에는 로그인할 수 없다** — 그래서 마지막 로그인 이후로만 잡는다.
        # 예전에는 created 기준으로 따로 뽑아서 '탈퇴 8개월 뒤 로그인' 같은 행이 나왔다(실측 7건).
        withdrawn = rdt(last_login or created, NOW) if rng.random() < 0.04 else None

        # updated_at 은 '마지막 수정 시각'이라 위 사건 전부보다 뒤여야 한다.
        updated = rdt(max(x for x in (created, last_login, withdrawn) if x), NOW)

        # phone 에 UNIQUE 를 걸지 않는 이유가 "가족 공유, 통신사 번호 재할당, 탈퇴 후 재가입
        # 때문에 실제로 유일하지 않다"(user_schema.md)이므로, 데이터에도 중복 번호가 있어야 한다.
        # 전부 유일하면 UNIQUE 를 걸어도 통과해버려서 그 판단이 시험되지 않는다.
        if phones and rng.random() < 0.05:
            phone = rng.choice(phones)
        else:
            phone = f'010-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}'
            phones.append(phone)

        rows.append((uid, provider, auth_uid, email,
                     rng.choice(SURNAMES) + rng.choice(GIVEN),
                     phone, pick(REGIONS),
                     dt(last_login) if last_login else None,
                     dt(withdrawn) if withdrawn else None,
                     dt(created), dt(updated)))
    return rows


# ---------------------------------------------------------------------------
# pets / pet_breeds / pet_allergies

def gen_pets(users):
    pets, pet_breeds, pet_allergies = [], [], []
    pet_id = 0
    for u in users:
        uid, user_created = u[0], datetime.fromisoformat(u[9])

        # 펫 등록은 **앱에 로그인해야** 할 수 있다. 그래서 두 가지가 따라온다.
        #
        #   1) last_login_at 이 NULL(한 번도 로그인 안 함)이면 펫이 있을 수 없다.
        #      예전에는 그런 유저 14명 전원이 펫을 갖고 있었다.
        #   2) 등록·수정 시각은 **마지막 로그인보다 뒤일 수 없다.**
        #      last_login_at 은 '마지막' 로그인이므로 그 뒤의 앱 활동은 정의상 없다.
        #      예전에는 96건이 그 뒤에 찍혀 있었다.
        if u[7] is None:
            continue
        last_login = datetime.fromisoformat(u[7])
        # 탈퇴한 뒤에도 등록할 수 없다.
        ceiling = min(last_login, datetime.fromisoformat(u[8])) if u[8] else last_login
        if ceiling < user_created:
            continue

        # 가입만 하고 아직 펫을 안 올린 유저도 있다. 예전에는 300명 전원이 펫을 갖고 있었는데,
        # 그러면 '펫 0마리 유저'라는 상태가 데이터에 존재하지 않게 된다.
        if rng.random() < 0.06:
            continue

        used_names = set()
        for _ in range(pick([(1, 70), (2, 24), (3, 6)])):
            pet_id += 1
            category = pick([(1, 80), (2, 20)])   # 개 / 고양이

            # 품종 수가 곧 행 수다. 0행 = 모른다(잡종 포함), 2행 이상 = 믹스.
            # 축종마다 분포가 다르고, 품종 자체도 가중치를 받는다 — 위 BREED_COUNT_DIST /
            # BREED_WEIGHT 참고. 예전에는 둘 다 균등이라 코숏이 아비시니안만큼만 나왔다.
            n_breeds = pick(BREED_COUNT_DIST[category])
            chosen = pick_breeds(category, n_breeds)
            for bid in chosen:
                pet_breeds.append((pet_id, bid))

            age_years = pick([(0, 8), (1, 12), (2, 12), (3, 11), (4, 10), (5, 9), (6, 8),
                              (7, 7), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 2),
                              (14, 1), (15, 1)])
            birth = TODAY - timedelta(days=age_years * 365 + rng.randint(0, 364))
            # 마지막 로그인 뒤에 태어난 아이는 이 유저가 등록했을 수 없다.
            # 휴면 유저에게 갓난 강아지가 붙는 것을 막는다 — 나이를 구간에 맞춰 올린다.
            if as_dt(birth) > ceiling:
                birth = rdate(max(user_created.date(), ceiling.date() - timedelta(days=365 * 15)),
                              ceiling.date())

            lo, hi, size = (BREED_BODY[BREED_NAME[chosen[0]]] if chosen
                            else DEFAULT_BODY[category])
            weight = rng.uniform(lo, hi)
            # 성장기 개체는 품종 표준 체중에 아직 못 미친다. 안 깎으면
            # '생후 5개월 시바견 11kg' 같은 행이 나와서 급여량·칼로리 계산의 근거가 이상해진다.
            months = (TODAY - birth).days / 30.4
            if months < 12:
                weight *= 0.25 + 0.75 * months / 12
            weight = round(weight, 1)
            # 품종 표준이 아니라 눈앞의 개체를 입력받는다 — 20% 는 보호자가 한 칸 다르게 고른다.
            if rng.random() < 0.20:
                size = min(5, max(1, size + rng.choice([-1, 1])))

            # 등록 시각의 하한이 두 개다 — (1) 태어난 뒤 (2) 주인이 가입한 뒤.
            # 늦은 쪽을 쓴다. 예전에는 주인 가입일만 봐서 '태어나기 2년 전에 등록'된
            # 개체가 45마리 나왔다.
            created = rdt(max(user_created, as_dt(birth)), ceiling)
            # 사망·파양 등. 불리언이 아니라 시각이라 '언제' 떠났는지가 남는다.
            # 활동종료 기록도 앱에서 남기는 것이라 마지막 로그인 이후일 수 없다.
            inactive = rdt(created, ceiling) if rng.random() < 0.03 else None
            updated = rdt(inactive or created, ceiling)

            # 한 집에 같은 이름 두 마리는 없다. 이름 풀이 40개라 그냥 뽑으면 실제로 겹쳤다.
            avail = [n for n in PET_NAMES if n not in used_names] or PET_NAMES
            pet_name = rng.choice(avail)
            used_names.add(pet_name)

            pets.append((
                pet_id, uid, category, pet_name,
                pick([('M', 49), ('F', 49), (None, 2)]),
                birth.isoformat(),
                weight if rng.random() > 0.05 else None,   # 미입력 개체도 있다
                size,
                pick([(1, 5), (2, 12), (3, 45), (4, 28), (5, 10)]),   # BCS 5점 척도
                pick([(1, 65), (0, 35)]),
                dt(inactive) if inactive else None, dt(created), dt(updated),
            ))

            # --- 알러지: 카테고리를 고르면 하위를 전부 펼치고 고른 행도 남긴다 ---
            # 옛 pet_profiles.csv 실측으로 53% 가 '없음'이었다.
            if rng.random() < 0.47:
                picked = set()
                for _ in range(pick([(1, 80), (2, 20)])):
                    # 리프만 고르면 '가금류 알러지' 같은 등록 입도가 데이터에 안 나타난다.
                    pool = ALLERGEN_LEAVES if rng.random() < 0.75 else ALLERGEN_NODES
                    picked.add(rng.choice(pool))
                expanded = set()
                for a in picked:
                    expanded |= descendants(a)
                for a in sorted(expanded):
                    pet_allergies.append((pet_id, a))

    return pets, pet_breeds, pet_allergies


# ---------------------------------------------------------------------------
# products + 딸린 4테이블

def gen_products():
    products, p_animals, nutrition, purposes, p_ings = [], [], [], [], []
    seq = {}

    for pid in range(1, N_PRODUCTS + 1):
        cat = pick([(1, 55), (2, 5), (3, 13), (4, 14), (5, 13)])
        is_food = cat == 1
        label = CATEGORY_LABEL[cat]

        # 이 제품을 어느 축종에게 줄 수 있는가. 0행 = 아무에게도 안 뜬다 —
        # '모르는 것을 안전으로 처리하지 않는다'가 실제로 관측되도록 일부러 남긴다.
        animals = pick([((1,), 68), ((2,), 20), ((1, 2), 9), ((), 3)])
        for a in animals:
            p_animals.append((pid, a))
        cat_only = animals == (2,)

        brand = rng.choice(CAT_BRANDS if cat_only else DOG_BRANDS)
        form = pick([('건식', 60), ('습식', 25), ('동결건조', 5), ('생식', 5), ('공용', 5)]
                    if is_food else
                    [('건식', 35), ('동결건조', 30), ('습식', 10), ('생식', 5), ('공용', 20)])

        # 옛 pet_products.csv 는 200개 중 125개가 동명이품이었다(DATAINFO §3).
        # 브랜드+분류별 일련번호를 붙여서 이름만으로도 구분되게 한다.
        seq[(brand, label)] = seq.get((brand, label), 0) + 1
        name = f'{brand} {label} {seq[(brand, label)]:02d}호'

        # 대상 연령(월). '전체'라는 마법값 대신 범위의 양 끝으로 표현한다.
        stage = pick([('all', 50), ('puppy', 15), ('senior', 15), ('adult', 20)])
        age_min, age_max = {'all': (0, 1200), 'puppy': (0, 12),
                            'senior': (84, 1200), 'adult': (12, 1200)}[stage]

        # 대상 체구. 좁게 잡는 제품이 있어야 size 필터가 실제로 걸린다.
        # 'one' 은 product_schema.md 의 예시("소형견 전용 = min 2, max 2")를 그대로 만든다 —
        # min == max 인 제품이 하나도 없으면 그 표기가 데이터에 존재하지 않는 것이 된다.
        band = pick([('all', 62), ('small', 14), ('large', 14), ('one', 10)])
        if band == 'one':
            size_min = size_max = rng.randint(1, 5)
        else:
            size_min, size_max = {'all': (1, 5), 'small': (1, 2), 'large': (4, 5)}[band]

        kcal_lo, kcal_hi = FOOD_FORM_KCAL[form]

        # 중량을 먼저 정하고, 100g당 단가를 곱해 가격을 만든다.
        lo_g, hi_g, lo_unit, hi_unit = (FOOD_SPEC if is_food else TREAT_SPEC)[form]
        weight_g = round(rng.uniform(lo_g, hi_g) / 10) * 10
        unit = rng.uniform(lo_unit, hi_unit)
        # 대용량일수록 100g당 단가가 떨어진다. 없으면 15kg 포대가 비현실적으로 비싸진다.
        unit *= 1 - 0.35 * min(1.0, weight_g / 5000)
        price_krw = round(weight_g / 100 * unit / 100) * 100

        p_created = rdt(SERVICE_OPEN, TODAY)

        chosen_purposes = {4} if cat == 3 else set()   # 덴탈껌은 치아 목적이 확정이다
        chosen_purposes |= set(rng.sample([1, 2, 3, 5, 6], pick([(0, 30), (1, 50), (2, 20)])))
        for p in sorted(chosen_purposes):
            purposes.append((pid, p))

        # --- 원료 --- (description 이 주원료를 인용하므로 제품 행보다 먼저 뽑는다)
        chosen_ings = set(rng.sample(ING_PROTEIN, rng.randint(1, 3)))
        if is_food:
            chosen_ings |= set(rng.sample(ING_CARB, rng.randint(1, 3)))
        chosen_ings |= set(rng.sample(ING_SUPPLEMENT, rng.randint(0, 2)))
        # 첨가물은 간식 쪽에 흔하다. 사료에도 아주 없지는 않다.
        if rng.random() < (0.10 if is_food else 0.35):
            chosen_ings.add(rng.choice(ING_ADDITIVE))
        if 2 in animals and rng.random() < 0.7:
            chosen_ings |= set(ING_CAT_ONLY)
        for i in sorted(chosen_ings):
            p_ings.append((pid, i))

        # --- description ---
        # products.description 은 '후기 없는 신규 제품(콜드스타트)의 임베딩 대상'이다
        # (product_schema.md). 상투 문구만 넣으면 벡터가 제품들끼리 구분되지 않으므로,
        # 다른 표에 흩어져 있는 사실(축종·체구·연령·주원료·목적)을 한 문장으로 모은다.
        animal_txt = {(): '대상 축종 미등록', (1,): '개 전용',
                      (2,): '고양이 전용', (1, 2): '개·고양이 공용'}[animals]
        if size_min == size_max:
            size_txt = f'{SIZE_LABEL[size_min]} 전용'
        elif (size_min, size_max) == (1, 5):
            size_txt = '전 체구'
        else:
            size_txt = f'{SIZE_LABEL[size_min]}~{SIZE_LABEL[size_max]}'
        main_ings = '·'.join(INGREDIENT_NAME[i] for i in sorted(chosen_ings)[:3])
        purpose_txt = ('/'.join(PURPOSE_NAME[p] for p in sorted(chosen_purposes)) + ' 관리'
                       if chosen_purposes else '일상 급여')
        description = (f'{animal_txt} {form} {label}. {size_txt}, {STAGE_LABEL[stage]} 대상. '
                       f'{main_ings} 배합. {purpose_txt} 목적.')

        products.append((
            pid, cat, brand, name, form,
            price_krw, weight_g,
            rng.randint(kcal_lo, kcal_hi) if rng.random() > 0.08 else None,
            size_min, size_max, age_min, age_max,
            description,
            # 원료표를 다 옮겨 적었는가. 0 이면 v_product_safety 가 판정불가로 본다.
            pick([(1, 78), (0, 22)]),
            pick([(1, 93), (0, 7)]),
            # 수정은 등록 **이후**다. 예전에는 둘을 따로 뽑아서 103개(절반 이상)가
            # '3년 전에 수정됨'으로 나왔다.
            dt(p_created), dt(rdt(p_created, NOW)),
        ))

        # --- 영양성분 (1:1, 없는 제품도 있다) ---
        # 결측률은 분류마다 다르다. 사료는 표시 의무가 있어 거의 전부 있고, 간식은 자주 빠진다.
        if rng.random() < NUTRITION_RATE[cat]:
            wet = form == '습식'

            def maybe(lo, hi, p=0.6):
                return round(rng.uniform(lo, hi), 1) if rng.random() < p else None

            protein = round(rng.uniform(8, 12) if wet else rng.uniform(22, 34), 1)
            fat = round(rng.uniform(2, 6) if wet else rng.uniform(8, 18), 1)
            fiber = round(rng.uniform(0.5, 1.5) if wet else rng.uniform(2, 5), 1)
            ash = round(rng.uniform(1, 3) if wet else rng.uniform(5, 9), 1)
            moisture = round(rng.uniform(70, 82) if wet else rng.uniform(8, 12), 1)

            # 보증성분 5개의 합은 100% 를 넘을 수 없다 — 나머지는 탄수화물(가용무질소물) 몫이라
            # 최소 1% 는 남긴다. 습식은 수분이 80% 대라 그냥 뽑으면 합이 104% 까지 나온다.
            # 사료 쪽 결측을 줄이자 성분표가 늘면서 이 잠복 결함이 드러났다.
            moisture = min(moisture, round(99 - (protein + fat + fiber + ash), 1))

            nutrition.append((pid, protein, fat, fiber, ash, moisture,
                              maybe(0.6, 2.0), maybe(0.5, 1.6), maybe(0.1, 0.6)))

    return products, p_animals, nutrition, purposes, p_ings


# ---------------------------------------------------------------------------
# purchases / reviews — 기존 후기 원본을 정규화된 두 테이블로 분리

def gen_purchases_reviews(pets, products, p_animals):
    """원본 후기를 분리하고, 현재 시드와 연결된 새 구매·후기를 추가한다."""
    pet_by_id = {row[0]: row for row in pets}
    pets_by_user = {}
    for pet in pets:
        pets_by_user.setdefault(pet[1], []).append(pet)
    product_by_id = {row[0]: row for row in products}
    product_animals = {}
    for product_id, animal_category_id in p_animals:
        product_animals.setdefault(product_id, set()).add(animal_category_id)
    size_code = {'소형': 2, '중형': 3, '대형': 4}
    purchases, reviews = [], []
    remapped = 0
    fallback = 0
    review_templates = {
        1: ['잘 먹지 않아서 아쉬워요. 다음에는 다른 제품을 찾아보려고요.',
            '기대했는데 우리 아이와는 잘 맞지 않았어요.'],
        2: ['조금 아쉬웠어요. 먹기는 하지만 재구매는 고민됩니다.',
            '반응이 보통이고 특별한 장점은 못 느꼈어요.'],
        3: ['무난하게 먹이고 있어요. 크게 나쁘지는 않아요.',
            '기호성은 보통이고 가격 대비 괜찮은 편이에요.'],
        4: ['잘 먹고 속도 편해 보여서 만족해요.',
            '꾸준히 먹이고 있어요. 다음에도 구매할 것 같아요.'],
        5: ['정말 잘 먹어요. 다음에도 재구매할 예정입니다.',
            '밥 시간마다 기다릴 정도로 좋아해요. 아주 만족합니다.'],
    }

    def make_review_body(purchase_id, pet, product, purchased_at, quantity, rating):
        details = [
            '첫 급여라 걱정했는데 적응이 빨랐어요.',
            '포장 상태도 괜찮고 급여하기 편했어요.',
            '며칠 동안 상태를 지켜보니 특별한 문제는 없었어요.',
            '기대했던 것보다 기호성이 괜찮았어요.',
            '다음 주문 때도 비슷한 제품을 비교해볼 생각이에요.',
        ]
        return (f'{pet[3]}에게 {product[3]}을 급여해봤어요. '
                f'{rng.choice(review_templates[rating])} '
                f'{rng.choice(details)} {purchased_at:%Y년 %m월}에 {quantity}개 주문했어요. '
                f'후기 번호는 {purchase_id}번입니다.')

    with (ROOT / 'data' / 'review.csv').open(encoding='utf-8', newline='') as f:
        for source in csv.DictReader(f):
            purchase_id = int(source['purchase_id'][1:])
            source_pet_id = int(source['pet_id'][1:])
            pet_id = source_pet_id
            if pet_id not in pet_by_id:
                user_id = int(source['customer_id'][1:])
                candidates = pets_by_user.get(user_id, [])
                if candidates:
                    pet_id = min(candidates, key=lambda row: int(row[0]))[0]
                else:
                    wanted_size = size_code[source['size_category']]
                    pet_id = min(pets, key=lambda row: (abs(int(row[7]) - wanted_size),
                                                        int(row[0])))[0]
                    fallback += 1
                remapped += 1
            product_id = int(source['product_id'][1:])
            pet = pet_by_id[pet_id]
            product = product_by_id[product_id]

            source_time = datetime.strptime(source['purchased_at'], '%Y-%m-%d')
            pet_created = datetime.fromisoformat(pet[11])
            product_created = datetime.fromisoformat(product[15])
            purchased_at = max(source_time, pet_created, product_created)
            reviewed_at = purchased_at

            purchases.append((
                purchase_id, pet_id, product_id, int(source['quantity']),
                product[5], age_months(pet[5], purchased_at.isoformat()),
                size_code[source['size_category']], dt(purchased_at),
            ))
            reviews.append((
                purchase_id, int(source['rating']),
                make_review_body(purchase_id, pet, product, purchased_at,
                                 int(source['quantity']), int(source['rating'])),
                int(source['is_holdout']), dt(reviewed_at),
            ))

    eligible_pets = [row for row in pets if row[10] is None]
    eligible_products = [row for row in products if row[14] == 1]
    next_purchase_id = max(row[0] for row in purchases) + 1
    for _ in range(N_ADDITIONAL_PURCHASES):
        pet = rng.choice(eligible_pets)
        category = pet[2]
        candidates = [row for row in eligible_products
                      if category in product_animals.get(row[0], set())]
        product = rng.choice(candidates or eligible_products)
        lower_bound = max(datetime.fromisoformat(pet[11]),
                          datetime.fromisoformat(product[15]))
        purchased_at = rdt(lower_bound, NOW)
        rating = pick([(1, 8), (2, 10), (3, 20), (4, 32), (5, 30)])
        reviewed_at = min(NOW, purchased_at + timedelta(days=rng.randint(1, 14)))
        purchase_id = next_purchase_id
        next_purchase_id += 1
        purchases.append((
            purchase_id, pet[0], product[0], rng.randint(1, 5), product[5],
            age_months(pet[5], purchased_at.isoformat()), pet[7], dt(purchased_at),
        ))
        reviews.append((
            purchase_id, rating,
            make_review_body(purchase_id, pet, product, purchased_at,
                             purchases[-1][3], rating),
            1 if rng.random() < 0.10 else 0, dt(reviewed_at),
        ))

    if remapped:
        print(f'  reviews 펫 ID 보정 {remapped}건 (고객 펫 연결 실패 최후 보정 {fallback}건)')
    print(f'  신규 구매·후기 더미 {N_ADDITIONAL_PURCHASES}건 추가')
    return purchases, reviews


# ---------------------------------------------------------------------------

def main():
    print(f'seed={SEED}  today={TODAY}')
    print('\n[master] (읽기만 함)')
    print(f'  allergen {len(allergen_rows)}행 / breed {len(breed_rows)}행 / '
          f'ingredient {len(ingredient_rows)}행 / ingredient_allergen {len(ing_allergen_rows)}행')

    users = gen_users()
    pets, pet_breeds, pet_allergies = gen_pets(users)
    products, p_animals, nutrition, purposes, p_ings = gen_products()
    purchases, reviews = gen_purchases_reviews(pets, products, p_animals)

    print('\n[seed]')
    write_csv('user', ['user_id', 'auth_provider', 'auth_uid', 'email', 'name', 'phone',
                        'region', 'last_login_at', 'withdrawn_at', 'created_at', 'updated_at'],
              users)
    write_csv('pet', ['pet_id', 'user_id', 'animal_category_id', 'name', 'gender', 'birth_date',
                       'weight_kg', 'size', 'body_type', 'neutered', 'inactive_at',
                       'created_at', 'updated_at'], pets)
    write_csv('pet_breed', ['pet_id', 'breed_id'], pet_breeds)
    write_csv('pet_allergy', ['pet_id', 'allergen_id'], pet_allergies)
    write_csv('product', ['product_id', 'product_category_id', 'brand', 'name', 'food_form',
                           'price_krw', 'weight_g', 'kcal_per_100g',
                           'target_size_min', 'target_size_max',
                           'target_age_min_month', 'target_age_max_month',
                           'description', 'ingredients_verified', 'is_active',
                           'created_at', 'updated_at'], products)
    write_csv('product_animal_category', ['product_id', 'animal_category_id'], p_animals)
    write_csv('product_nutrition', ['product_id', 'crude_protein_pct', 'crude_fat_pct',
                                    'crude_fiber_pct', 'crude_ash_pct', 'moisture_pct',
                                    'calcium_pct', 'phosphorus_pct', 'sodium_pct'], nutrition)
    write_csv('product_feeding_purposes', ['product_id', 'feeding_purpose_id'], purposes)
    write_csv('product_ingredients', ['product_id', 'ingredient_id'], p_ings)
    write_csv('purchases', ['purchase_id', 'pet_id', 'product_id', 'quantity',
                            'unit_price_krw', 'age_month_at_purchase',
                            'size_at_purchase', 'purchased_at'], purchases)
    write_csv('reviews', ['purchase_id', 'rating', 'body', 'is_holdout', 'reviewed_at'], reviews)

    # 분포가 의도대로 나왔는지 — 여기가 무너지면 판정 3분법을 시험할 수 없다.
    no_animal = N_PRODUCTS - len({p for p, _ in p_animals})
    unverified = sum(1 for p in products if p[13] == 0)
    allergic = len({p for p, _ in pet_allergies})
    print(f'\n펫 {len(pets)}마리 중 알러지 등록 {allergic}마리 '
          f'(펼친 행 {len(pet_allergies)}개, 마리당 평균 {len(pet_allergies) / max(allergic, 1):.1f})')
    print(f'제품 {N_PRODUCTS}개 중 ingredients_verified=0 {unverified}개 / '
          f'축종 0행 {no_animal}개, 둘 다 0이면 판정불가 분기가 안 나온다')


if __name__ == '__main__':
    main()
