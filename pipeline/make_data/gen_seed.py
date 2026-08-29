# Last updated: 2026-08-28

"""data/seed/*.csv 를 만든다. 16테이블 스키마용 합성 데이터.

    data/master/*.csv --[gen_seed]--> data/seed/*.csv --[load_csv]--> pet_reco.db
    data/review.csv (선택) ┘

    마스터는 읽기만 한다. allergen_id / breed_id / ingredient_id 가 바뀌면
    손으로 넣은 ingredient_allergen 매핑이 통째로 깨진다.

    data/review.csv 는 **있으면 쓰고 없으면 건너뛴다.** 있으면 그 후기 본문을
    review.body 로 그대로 옮기고(임베딩 대상이라 템플릿으로 덮으면 신호가 사라진다),
    없으면 구매·후기 전량을 합성한다. 어느 쪽이든 시드가 같으면 결과가 같다.

    CSV 규약 : 파일 1개 = 테이블 1개, 헤더는 DDL 컬럼 순서대로,
               NULL 은 빈 칸, UTF-8 BOM 없음, 줄바꿈 LF.

    DB 가 못 막아 여기서 지키는 것
      - pet_allergy 펼침 : 카테고리를 고르면 하위를 전부 넣는다.
      - 축종 정합성 : 개에게 고양이 품종이 붙는 것을 막는다(FK 는 통과시킨다).
      - UNIQUE : user.email, (auth_provider, auth_uid).
      - 판정 3분법 : ingredients_verified=0 과 축종 0행 제품을 일부러 남긴다.
        전부 채우면 v_product_safety 의 '판정불가' 분기가 관측되지 않는다.

    실행 : py -m pipeline.make_data.gen_seed   (repo root 에서)
"""

import csv
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# -m 없이 파일 경로로 실행해도(IDE 의 Run 버튼 포함) app 을 찾게 한다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.petcalc import age_months      # noqa: E402

MASTER_DIR = ROOT / 'data' / 'master'
SEED_DIR = ROOT / 'data' / 'seed'
SOURCE_REVIEWS = ROOT / 'data' / 'review.csv'      # 선택 입력

SEED = 20260812        # 고정. 재실행해도 같아야 벤치·평가 비교가 성립한다.
N_USERS = 300
N_PRODUCTS = 200
N_EXTRA_PURCHASES = 600      # 원본이 있을 때 덧붙이는 양
N_SOLO_PURCHASES = 2000      # 원본이 없을 때 전량 합성하는 양

TODAY = date(2026, 8, 25)               # date.today() 는 실행마다 값이 흔들린다
SERVICE_OPEN = date(2023, 1, 1)
NOW = datetime(2026, 8, 25, 23, 59, 59)  # 모든 타임스탬프의 상한

rng = random.Random(SEED)


# ---------------------------------------------------------------------------
# 도구

def pick(weighted):
    """[(값, 가중치), ...] 에서 하나."""
    return rng.choices([v for v, _ in weighted], weights=[w for _, w in weighted])[0]


def as_dt(x, end_of_day=False):
    """date -> datetime. datetime 이면 그대로."""
    return x if isinstance(x, datetime) else datetime.combine(
        x, time.max if end_of_day else time.min)


def rdt(start, end):
    """start~end 사이 datetime 하나.

    날짜를 뽑고 시각을 따로 붙이면 같은 날일 때 09시 가입 -> 03시 로그인이 나온다.
    초 단위로 뽑아 그 구멍을 없앤다. 뒤집힌 구간은 start 로 눕힌다.
    """
    start, end = as_dt(start), as_dt(end, end_of_day=True)
    if end < start:
        return start
    return start + timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))


def rdate(start, end):
    """start~end 사이 날짜 하나."""
    span = (end - start).days
    return start if span <= 0 else start + timedelta(days=rng.randint(0, span))


def dt(x):
    """ISO-8601 문자열. SQLite datetime() 이 파싱할 수 있어야 한다."""
    return as_dt(x).strftime('%Y-%m-%d %H:%M:%S')


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(name, header, rows):
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with (SEED_DIR / f'{name}.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(['' if v is None else v for v in r] for r in rows)
    print(f'  {name + ".csv":30} {len(rows):>6}행')


# ---------------------------------------------------------------------------
# 마스터 — 여기 있는 ID 만 참조한다

allergen_rows = read_csv(MASTER_DIR / 'allergen.csv')
breed_rows = read_csv(MASTER_DIR / 'breed.csv')
ingredient_rows = read_csv(MASTER_DIR / 'ingredient.csv')
ing_allergen_rows = read_csv(MASTER_DIR / 'ingredient_allergen.csv')

# 알러지원 트리. 펼침은 원래 앱이 하는 일이고 이 생성기가 그 역할을 대신한다.
ALLERGEN_CHILDREN, ALLERGEN_NAME, ALLERGEN_PARENT = {}, {}, {}
for r in allergen_rows:
    aid = int(r['allergen_id'])
    ALLERGEN_NAME[aid] = r['name_ko']
    ALLERGEN_CHILDREN.setdefault(aid, [])
    if r['parent_id']:
        ALLERGEN_PARENT[aid] = int(r['parent_id'])
        ALLERGEN_CHILDREN.setdefault(int(r['parent_id']), []).append(aid)

ALLERGEN_LEAVES = [a for a in ALLERGEN_NAME if not ALLERGEN_CHILDREN[a]]
ALLERGEN_NODES = [a for a in ALLERGEN_NAME if ALLERGEN_CHILDREN[a]]

BREEDS_BY_CATEGORY = {1: [], 2: []}
BREED_NAME = {}
for r in breed_rows:
    BREEDS_BY_CATEGORY[int(r['animal_category_id'])].append(int(r['breed_id']))
    BREED_NAME[int(r['breed_id'])] = r['name_ko']

INGREDIENT_NAME = {int(r['ingredient_id']): r['name_ko'] for r in ingredient_rows}


def descendants(aid):
    """aid 자신 + 모든 하위. pet_allergy 에 그대로 들어갈 집합."""
    out, stack = set(), [aid]
    while stack:
        cur = stack.pop()
        if cur not in out:
            out.add(cur)
            stack.extend(ALLERGEN_CHILDREN.get(cur, ()))
    return out


# ---------------------------------------------------------------------------
# 값 풀 — 옛 data/*.csv 4종에서 실측한 분포를 재료로 쓴다

# 품종 -> (최소체중, 최대체중, size). size 1 초소형 ~ 5 초대형.
BREED_BODY = {
    '말티즈': (2, 4, 1), '포메라니안': (2, 4, 1), '치와와': (1.5, 3, 1), '요크셔테리어': (2, 3.5, 1),
    '비숑프리제': (4, 7, 2), '푸들': (3, 8, 2), '시츄': (4, 8, 2), '닥스훈트': (4, 9, 2),
    '미니어처슈나우저': (5, 9, 2), '웰시코기': (10, 14, 3), '시바견': (8, 12, 3),
    '진돗개': (15, 23, 3), '비글': (9, 14, 3), '코카스파니엘': (10, 15, 3),
    '보더콜리': (14, 20, 3), '프렌치불독': (9, 13, 3), '골든리트리버': (25, 34, 4),
    '래브라도리트리버': (25, 36, 4), '시베리안허스키': (16, 27, 4), '저먼셰퍼드': (22, 40, 4),
    '사모예드': (16, 30, 4), '삽살개': (16, 26, 4), '풍산개': (17, 28, 4),
    '코리안숏헤어': (3, 5, 2), '러시안블루': (3, 5.5, 2), '페르시안': (3, 5.5, 2),
    '샴': (2.5, 4.5, 1), '스코티시폴드': (2.5, 6, 2), '브리티시숏헤어': (4, 8, 2),
    '먼치킨': (2, 4, 1), '노르웨이숲': (5, 9, 3), '벵갈': (4, 7, 2),
    '아메리칸숏헤어': (3.5, 7, 2), '터키시앙고라': (2.5, 5, 1), '랙돌': (5, 9, 3),
    '아비시니안': (3, 5, 2),
}
DEFAULT_BODY = {1: (4, 20, 3), 2: (3, 6, 2)}      # 품종 미상 개체

# 품종 행 수가 곧 뜻이다. 0행 = 모른다(잡종) / 1행 = 순혈 / 2행 이상 = 믹스.
# 고양이 0행이 낮은 것은 '코숏'이라는 포괄 명칭이 있어 길에서 온 아이도 이름이 붙기 때문.
BREED_COUNT_DIST = {1: [(0, 8), (1, 70), (2, 20), (3, 2)],
                    2: [(0, 4), (1, 86), (2, 10), (3, 0)]}

# 균등하면 코숏이 아비시니안과 같은 빈도로 나온다. 개는 근거 자료가 없어 균등(기본 1).
BREED_WEIGHT = {'코리안숏헤어': 45, '러시안블루': 8, '스코티시폴드': 8, '페르시안': 6,
                '먼치킨': 6, '브리티시숏헤어': 5, '샴': 4, '노르웨이숲': 4,
                '아메리칸숏헤어': 4, '랙돌': 4, '벵갈': 3, '터키시앙고라': 2, '아비시니안': 1}

SURNAMES = list('김이박최정강조윤장임한오서신권황안송류전')
GIVEN = ['우미', '민환', '지훈', '서연', '도윤', '하은', '지우', '현우', '수아', '준서',
         '예린', '건우', '다인', '시우', '유진', '태현', '보람', '승민', '지아', '재원',
         '나연', '동현', '민준', '가온', '윤슬', '해린', '주원', '민서', '채원', '영호']
PET_NAMES = ['초코', '보리', '코코', '별이', '두부', '모카', '까미', '루비', '뽀삐', '콩이',
             '마루', '단추', '설이', '망고', '나비', '호두', '떡볶이', '구름', '레오', '밤비',
             '쿠키', '베리', '달이', '순이', '가을', '토리', '삐삐', '봄이', '슈슈', '아톰',
             '먼지', '치즈', '감자', '방울', '탄이', '유리', '똘이', '해피', '라떼', '몽이']

REGIONS = [('서울', 97), ('경기', 58), ('인천', 23), ('충남', 19), ('부산', 16), ('경남', 12),
           ('대구', 10), ('광주', 10), ('경북', 9), ('전북', 9), ('대전', 7), ('전남', 7),
           ('울산', 6), ('충북', 6), ('강원', 5), ('제주', 3), ('세종', 3)]
AUTH_PROVIDERS = [('local', 55), ('google', 25), ('kakao', 15), ('apple', 3), ('firebase', 2)]
EMAIL_DOMAINS = ['naver.com', 'gmail.com', 'daum.net', 'kakao.com']

BRANDS = ['멍푸드', '펫키친', '바크앤조이', '네이처독', '도그밀', '헬시포',
          '퍼피랩', '와일드포', '스노우독', '그레인프리랩', '캣테이블', '냥푸드']
CAT_BRANDS, DOG_BRANDS = BRANDS[-2:], BRANDS[:-2]

CATEGORY_LABEL = {1: '사료', 2: '간식', 3: '덴탈껌', 4: '트릿', 5: '수제간식'}
PURPOSE_NAME = {1: '관절', 2: '다이어트', 3: '피부', 4: '치아', 5: '신장', 6: '소화'}
SIZE_LABEL = {1: '초소형', 2: '소형', 3: '중형', 4: '대형', 5: '초대형'}
STAGE_LABEL = {'all': '전 연령', 'puppy': '유아기', 'senior': '노령기', 'adult': '성년기'}

# 원료를 역할별로 나눈다. 아무거나 뽑으면 '탈지분유 + 대구살 + 옥수수전분' 이 나온다.
# 46~50 은 복합 원료(하나가 알러지원 여럿) — ingredient_allergen 이 다대다인 이유.
# 51~57 은 알러지원은 있는데 그것을 가리키는 원료가 없어 필터가 0개를 거르던 자리를 메운 것.
ING_PROTEIN = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 47, 48, 51, 55]
ING_CARB = [23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 46, 49, 53, 54]
ING_SUPPLEMENT = [4, 13, 17, 18, 19, 20, 21, 22, 37, 38, 39, 40, 41, 42, 43, 44, 50, 52]
ING_ADDITIVE = [56, 57]      # 착색료·소르빈산칼륨
ING_CAT_ONLY = [45]          # 타우린

# 분류별 보증성분표가 있을 확률. 사료는 표시가 법적 의무라 결측이 거의 없어야 한다.
NUTRITION_RATE = {1: 0.98, 2: 0.70, 3: 0.55, 4: 0.65, 5: 0.60}

FOOD_FORM_KCAL = {'건식': (330, 430), '습식': (70, 120), '동결건조': (400, 500),
                  '생식': (120, 200), '공용': (300, 400)}

# 제형 -> (중량 하한g, 상한g, 100g당 단가 하한원, 상한원).
# 가격을 중량과 따로 뽑으면 100g당 단가가 46배까지 벌어진다. 중량 먼저, 단가는 곱한다.
FOOD_SPEC = {'건식': (400, 15000, 500, 1500), '습식': (80, 2000, 900, 2500),
             '동결건조': (200, 1200, 4000, 12000), '생식': (300, 2000, 1500, 4000),
             '공용': (400, 5000, 600, 1800)}
TREAT_SPEC = {'건식': (50, 500, 2000, 6000), '습식': (40, 300, 2500, 7000),
              '동결건조': (30, 300, 5000, 15000), '생식': (50, 400, 3000, 8000),
              '공용': (50, 500, 2000, 6000)}


def pick_breeds(category, n):
    """가중치를 반영해 서로 다른 품종 n 개(비복원). 같은 품종이 두 번 들어가면 복합 PK 가 막는다."""
    pool = list(BREEDS_BY_CATEGORY[category])
    wts = [BREED_WEIGHT.get(BREED_NAME[b], 1) for b in pool]
    out = []
    for _ in range(min(n, len(pool))):
        i = pool.index(rng.choices(pool, weights=wts)[0])
        out.append(pool.pop(i))
        wts.pop(i)
    return out


# ---------------------------------------------------------------------------

def gen_users():
    rows, emails, auth_keys, uids, phones = [], set(), set(), [], []
    for uid in range(1, N_USERS + 1):
        provider = pick(AUTH_PROVIDERS)

        # (auth_provider, auth_uid) 복합 UNIQUE 인 이유는 "같은 uid 라도 제공자가 다르면
        # 다른 계정"이라서다. 그 쌍이 없으면 복합으로 만든 이유가 시험되지 않는다.
        shareable = [u for u in uids if (provider, u) not in auth_keys]
        if shareable and rng.random() < 0.04:
            auth_uid = rng.choice(shareable)
        else:
            while (auth_uid := f'{rng.randrange(16 ** 12):012x}') in uids:
                pass
            uids.append(auth_uid)
        auth_keys.add((provider, auth_uid))

        while (email := f'user{rng.randint(1000, 99999)}@{rng.choice(EMAIL_DOMAINS)}') in emails:
            pass
        emails.add(email)

        created = rdt(SERVICE_OPEN, TODAY - timedelta(days=14))

        # last_login_at 은 '휴면'의 원천이라 오래된 값도 섞어야 그 판정을 시험할 수 있다.
        bucket = pick([('never', 5), ('dormant', 15), ('recent', 80)])
        if bucket == 'never':
            last_login = None
        elif bucket == 'dormant':
            last_login = rdt(created, TODAY - timedelta(days=180))
        else:
            last_login = rdt(max(created, as_dt(TODAY - timedelta(days=90))), NOW)

        # 탈퇴는 행 삭제가 아니라 시각 기록. 탈퇴 뒤에는 로그인할 수 없어 그 이후로만 잡는다.
        withdrawn = rdt(last_login or created, NOW) if rng.random() < 0.04 else None
        updated = rdt(max(x for x in (created, last_login, withdrawn) if x), NOW)

        # phone 에 UNIQUE 를 안 거는 근거(가족 공유·번호 재할당)가 데이터에도 있어야 한다.
        if phones and rng.random() < 0.05:
            phone = rng.choice(phones)
        else:
            phone = f'010-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}'
            phones.append(phone)

        rows.append((uid, provider, auth_uid, email,
                     rng.choice(SURNAMES) + rng.choice(GIVEN), phone, pick(REGIONS),
                     dt(last_login) if last_login else None,
                     dt(withdrawn) if withdrawn else None, dt(created), dt(updated)))
    return rows


def gen_pets(users):
    pets, pet_breeds, pet_allergies = [], [], []
    pet_id = 0
    for u in users:
        uid, user_created = u[0], datetime.fromisoformat(u[9])

        # 펫 등록은 로그인해야 할 수 있다. 한 번도 로그인 안 했으면 펫이 있을 수 없고,
        # 등록·수정 시각은 '마지막' 로그인보다 뒤일 수 없다. 탈퇴 뒤에도 등록할 수 없다.
        if u[7] is None:
            continue
        last_login = datetime.fromisoformat(u[7])
        ceiling = min(last_login, datetime.fromisoformat(u[8])) if u[8] else last_login
        if ceiling < user_created:
            continue
        if rng.random() < 0.06:      # 가입만 하고 펫을 안 올린 유저
            continue

        used_names = set()
        for _ in range(pick([(1, 70), (2, 24), (3, 6)])):
            pet_id += 1
            category = pick([(1, 80), (2, 20)])      # 개 / 고양이
            chosen = pick_breeds(category, pick(BREED_COUNT_DIST[category]))
            pet_breeds.extend((pet_id, bid) for bid in chosen)

            age_years = pick([(0, 8), (1, 12), (2, 12), (3, 11), (4, 10), (5, 9), (6, 8), (7, 7),
                              (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 2), (14, 1), (15, 1)])
            birth = TODAY - timedelta(days=age_years * 365 + rng.randint(0, 364))
            # 마지막 로그인 뒤에 태어난 아이는 이 유저가 등록했을 수 없다.
            if as_dt(birth) > ceiling:
                birth = rdate(max(user_created.date(), ceiling.date() - timedelta(days=365 * 15)),
                              ceiling.date())

            lo, hi, size = BREED_BODY[BREED_NAME[chosen[0]]] if chosen else DEFAULT_BODY[category]
            weight = rng.uniform(lo, hi)
            # 성장기 개체는 품종 표준에 못 미친다. 안 깎으면 '생후 5개월 시바견 11kg' 이 나온다.
            months = (TODAY - birth).days / 30.4
            if months < 12:
                weight *= 0.25 + 0.75 * months / 12
            # 품종 표준이 아니라 눈앞의 개체를 입력받는다 — 20% 는 한 칸 다르게 고른다.
            if rng.random() < 0.20:
                size = min(5, max(1, size + rng.choice([-1, 1])))

            # 등록 시각의 하한이 둘이다 — 태어난 뒤, 그리고 주인이 가입한 뒤.
            created = rdt(max(user_created, as_dt(birth)), ceiling)
            # 사망·파양. 불리언이 아니라 시각이라 '언제' 떠났는지가 남는다.
            inactive = rdt(created, ceiling) if rng.random() < 0.03 else None
            updated = rdt(inactive or created, ceiling)

            name = rng.choice([n for n in PET_NAMES if n not in used_names] or PET_NAMES)
            used_names.add(name)

            pets.append((
                pet_id, uid, category, name, pick([('M', 49), ('F', 49), (None, 2)]),
                birth.isoformat(),
                round(weight, 1) if rng.random() > 0.05 else None,      # 미입력 개체도 있다
                size,
                pick([(1, 5), (2, 12), (3, 45), (4, 28), (5, 10)]),     # BCS 5점 척도
                pick([(1, 65), (0, 35)]),
                dt(inactive) if inactive else None, dt(created), dt(updated),
            ))

            # 알러지: 고른 것의 하위를 전부 펼치고 고른 행도 남긴다. 옛 실측으로 53% 가 '없음'.
            if rng.random() < 0.47:
                picked = set()
                for _ in range(pick([(1, 80), (2, 20)])):
                    # 리프만 고르면 '가금류 알러지' 같은 등록 입도가 데이터에 안 나타난다.
                    picked.add(rng.choice(
                        ALLERGEN_LEAVES if rng.random() < 0.75 else ALLERGEN_NODES))
                expanded = set().union(*(descendants(a) for a in picked))
                pet_allergies.extend((pet_id, a) for a in sorted(expanded))

    return pets, pet_breeds, pet_allergies


def gen_products():
    products, p_animals, nutrition, purposes, p_ings = [], [], [], [], []
    seq = {}
    for pid in range(1, N_PRODUCTS + 1):
        cat = pick([(1, 55), (2, 5), (3, 13), (4, 14), (5, 13)])
        is_food = cat == 1
        label = CATEGORY_LABEL[cat]

        # 축종 0행 = 아무에게도 안 뜬다. '모르는 것을 안전으로 치지 않는다'를 관측하려고 남긴다.
        animals = pick([((1,), 68), ((2,), 20), ((1, 2), 9), ((), 3)])
        p_animals.extend((pid, a) for a in animals)

        brand = rng.choice(CAT_BRANDS if animals == (2,) else DOG_BRANDS)
        form = pick([('건식', 60), ('습식', 25), ('동결건조', 5), ('생식', 5), ('공용', 5)] if is_food
                    else [('건식', 35), ('동결건조', 30), ('습식', 10), ('생식', 5), ('공용', 20)])

        # 브랜드+분류별 일련번호. 없으면 옛 데이터처럼 200개 중 125개가 동명이품이 된다.
        seq[(brand, label)] = seq.get((brand, label), 0) + 1
        name = f'{brand} {label} {seq[(brand, label)]:02d}호'

        # 대상 연령·체구. '전체'라는 마법값 대신 범위의 양 끝으로 표현한다.
        stage = pick([('all', 50), ('puppy', 15), ('senior', 15), ('adult', 20)])
        age_min, age_max = {'all': (0, 1200), 'puppy': (0, 12),
                            'senior': (84, 1200), 'adult': (12, 1200)}[stage]
        # min == max 인 제품이 없으면 '소형견 전용' 표기가 데이터에 존재하지 않게 된다.
        band = pick([('all', 62), ('small', 14), ('large', 14), ('one', 10)])
        if band == 'one':
            size_min = size_max = rng.randint(1, 5)
        else:
            size_min, size_max = {'all': (1, 5), 'small': (1, 2), 'large': (4, 5)}[band]

        lo_g, hi_g, lo_unit, hi_unit = (FOOD_SPEC if is_food else TREAT_SPEC)[form]
        weight_g = round(rng.uniform(lo_g, hi_g) / 10) * 10
        # 대용량일수록 100g당 단가가 떨어진다. 없으면 15kg 포대가 비현실적으로 비싸진다.
        unit = rng.uniform(lo_unit, hi_unit) * (1 - 0.35 * min(1.0, weight_g / 5000))
        price_krw = round(weight_g / 100 * unit / 100) * 100

        chosen_purposes = {4} if cat == 3 else set()      # 덴탈껌은 치아 목적이 확정
        chosen_purposes |= set(rng.sample([1, 2, 3, 5, 6], pick([(0, 30), (1, 50), (2, 20)])))
        purposes.extend((pid, p) for p in sorted(chosen_purposes))

        # description 이 주원료를 인용하므로 제품 행보다 먼저 뽑는다.
        ings = set(rng.sample(ING_PROTEIN, rng.randint(1, 3)))
        if is_food:
            ings |= set(rng.sample(ING_CARB, rng.randint(1, 3)))
        ings |= set(rng.sample(ING_SUPPLEMENT, rng.randint(0, 2)))
        if rng.random() < (0.10 if is_food else 0.35):      # 첨가물은 간식 쪽에 흔하다
            ings.add(rng.choice(ING_ADDITIVE))
        if 2 in animals and rng.random() < 0.7:
            ings |= set(ING_CAT_ONLY)
        p_ings.extend((pid, i) for i in sorted(ings))

        # description 은 후기 없는 신규 제품의 임베딩 대상이다. 상투 문구만 넣으면 제품끼리
        # 구분되지 않으므로 다른 표에 흩어진 사실을 한 문장에 모은다.
        animal_txt = {(): '대상 축종 미등록', (1,): '개 전용',
                      (2,): '고양이 전용', (1, 2): '개·고양이 공용'}[animals]
        size_txt = (f'{SIZE_LABEL[size_min]} 전용' if size_min == size_max else
                    '전 체구' if (size_min, size_max) == (1, 5) else
                    f'{SIZE_LABEL[size_min]}~{SIZE_LABEL[size_max]}')
        purpose_txt = ('/'.join(PURPOSE_NAME[p] for p in sorted(chosen_purposes)) + ' 관리'
                       if chosen_purposes else '일상 급여')
        description = (f'{animal_txt} {form} {label}. {size_txt}, {STAGE_LABEL[stage]} 대상. '
                       f'{"·".join(INGREDIENT_NAME[i] for i in sorted(ings)[:3])} 배합. '
                       f'{purpose_txt} 목적.')

        kcal_lo, kcal_hi = FOOD_FORM_KCAL[form]
        created = rdt(SERVICE_OPEN, TODAY)
        products.append((
            pid, cat, brand, name, form, price_krw, weight_g,
            rng.randint(kcal_lo, kcal_hi) if rng.random() > 0.08 else None,
            size_min, size_max, age_min, age_max, description,
            pick([(1, 78), (0, 22)]),      # ingredients_verified. 0 이면 판정불가
            pick([(1, 93), (0, 7)]),       # is_active
            dt(created), dt(rdt(created, NOW)),      # 수정은 등록 이후다
        ))

        # 영양성분(1:1). 결측률은 분류마다 다르다 — 사료는 표시 의무가 있어 거의 전부 있다.
        if rng.random() < NUTRITION_RATE[cat]:
            wet = form == '습식'
            maybe = lambda lo, hi: round(rng.uniform(lo, hi), 1) if rng.random() < 0.6 else None
            protein = round(rng.uniform(8, 12) if wet else rng.uniform(22, 34), 1)
            fat = round(rng.uniform(2, 6) if wet else rng.uniform(8, 18), 1)
            fiber = round(rng.uniform(0.5, 1.5) if wet else rng.uniform(2, 5), 1)
            ash = round(rng.uniform(1, 3) if wet else rng.uniform(5, 9), 1)
            # 보증성분 5개의 합은 100%를 넘을 수 없다. 나머지는 탄수화물 몫이라 1%는 남긴다.
            moisture = min(round(rng.uniform(70, 82) if wet else rng.uniform(8, 12), 1),
                           round(99 - (protein + fat + fiber + ash), 1))
            nutrition.append((pid, protein, fat, fiber, ash, moisture,
                              maybe(0.6, 2.0), maybe(0.5, 1.6), maybe(0.1, 0.6)))

    return products, p_animals, nutrition, purposes, p_ings


# ---------------------------------------------------------------------------
# purchase / review

SIZE_CODE = {'초소형': 1, '소형': 2, '중형': 3, '대형': 4, '초대형': 5}

# 후기 조각. 그 행의 실제 사실(급여목적·분류·제형·체구·나이·알러지·평점)로만 고른다.
# 옛 원본 후기를 그대로 쓰면 고양이에게 "꼬리를 흔들며", 소형견에게 "대형견이라"가 붙었다.
PURPOSE_REASON = {
    1: ['관절이 약해 보여 걱정이었어요', '산책 뒤에 다리를 아껴주고 싶었어요'],
    2: ['체중 관리가 필요하다고 해서요', '살이 붙어서 고민하다 골랐어요'],
    3: ['피부를 자꾸 긁어서 찾아봤어요', '털 상태가 계속 신경 쓰였어요'],
    4: ['치석이 껴서 알아보다 샀어요', '양치를 싫어해서 대신할 걸 찾았어요'],
    5: ['신장 수치가 걱정돼서요', '물을 잘 안 마시는 편이라 신경 쓰였어요'],
    6: ['속이 자주 안 좋아서 찾아봤어요', '소화가 편한 걸 고르고 싶었어요'],
}
CATEGORY_REASON = {
    1: ['주식을 바꿔볼까 해서 골랐어요', '먹던 사료가 안 맞는 것 같아 바꿔봤어요'],
    2: ['간식으로 하나 들여봤어요', '새로운 간식을 찾다가 골랐어요'],
    3: ['덴탈 관리용으로 골랐어요', '이빨 사이에 낀 게 신경 쓰여 샀어요'],
    4: ['훈련 보상용으로 샀어요', '작게 끊어 주기 좋아 보여 골랐어요'],
    5: ['수제라 믿음이 가서 골랐어요', '첨가물이 적은 걸 찾다가 샀어요'],
}
TASTE = {
    1: ['거의 입도 안 댔어요', '냄새만 맡고 돌아서네요'],
    2: ['처음엔 먹다가 금방 남기더라고요', '억지로 먹이는 느낌이라 아쉬워요'],
    3: ['주면 먹기는 하는데 열광하진 않아요', '그럭저럭 먹는 편이에요'],
    4: ['잘 먹어서 다행이에요', '그릇을 비우는 걸 보니 마음이 놓여요'],
    5: ['정신없이 먹어요', '봉지 소리만 나도 달려옵니다'],
}
FORM_NOTE = {
    '건식': ['알갱이가 단단해 오래 씹어요', '보관이 편한 점이 좋아요'],
    '습식': ['수분이 많아 물 대신 챙겨주기 좋아요', '부드러워서 잘 넘겨요'],
    '동결건조': ['바삭해서 손에 묻지 않아요', '가볍고 부스러기가 적어요'],
    '생식': ['해동해서 주는 게 조금 번거로워요', '신선한 느낌이 들어요'],
    '공용': ['둘 다 먹일 수 있어 편해요', '한 봉지로 같이 먹입니다'],
}
SIZE_NOTE = {1: '입이 작은 아이인데 알맞은 크기예요', 2: '작은 아이 입에도 부담이 없어요',
             3: '한 번에 먹기 딱 좋은 크기예요', 4: '덩치가 있어 양이 금방 줄어요',
             5: '큰 아이라 한 봉지가 며칠 못 갑니다'}
AGE_NOTE = {'퍼피': '아직 어려서 조금씩 나눠 급여하고 있어요',
            '성견': '한창때라 그런지 급여량이 넉넉히 필요해요',
            '시니어': '나이가 있어 부드러운 쪽을 신경 쓰게 되네요'}
CLOSING = {
    1: ['재구매는 어려울 것 같아요.', '다른 제품을 다시 찾아봐야겠어요.'],
    2: ['재구매는 조금 더 고민해보려고요.', '한 번 더 줘보고 결정하려 합니다.'],
    3: ['가격을 보고 재구매를 정하려고요.', '무난해서 당분간은 이걸로 갑니다.'],
    4: ['다음에도 살 것 같아요.', '떨어지면 다시 주문하려고요.'],
    5: ['바로 재구매했습니다.', '주변에도 추천하고 있어요.'],
}


def age_group(age_month):
    """구매 시점 개월 나이 -> 연령대. NULL 이면 None."""
    if age_month is None:
        return None
    return '퍼피' if age_month < 12 else '시니어' if age_month >= 84 else '성견'


def review_body(pet, product, rating, age_month, allergen, purposes):
    """후기 한 건을 그 구매의 사실만으로 조립한다.

    같은 행의 pet / product / rating 에서만 문장을 고르므로, 축종·체구·분류가
    본문과 어긋나지 않는다. 슬롯 조합이라 행마다 다른 문장이 나온다.
    """
    reason = (rng.choice(PURPOSE_REASON[rng.choice(sorted(purposes))]) if purposes
              else rng.choice(CATEGORY_REASON[product[1]]))
    parts = [f'{pet[3]}에게 주려고 {reason}.', f'{rng.choice(TASTE[rating])}.']

    if rng.random() < 0.55:
        parts.append(f'{rng.choice(FORM_NOTE[product[4]])}.')
    if rng.random() < 0.45:
        parts.append(f'{SIZE_NOTE[pet[7]]}.')
    stage = age_group(age_month)
    if stage and rng.random() < 0.35:
        parts.append(f'{AGE_NOTE[stage]}.')
    if allergen and rng.random() < 0.6:
        # 알러지는 배제 근거라 본문에도 남는다. 임베딩이 이 문장을 읽어야 한다.
        parts.append(rng.choice([
            f'{allergen} 알레르기가 있어 원료를 하나하나 확인하고 샀어요.',
            f'{allergen}이 들어간 걸 먹으면 긁어서 성분표부터 봤습니다.']))
    parts.append(rng.choice(CLOSING[rating]))
    return ' '.join(parts)


def from_source(pets, products, animals_of, allergen_of, purpose_of):
    """data/review.csv 를 purchase / review 두 테이블로 나눈다. 파일이 없으면 빈 결과.

    원본에서 가져오는 것은 **구조뿐**이다 — 언제 몇 개 샀고 별점·holdout 이 무엇인지.
    펫 ID 를 이 시드에 맞게 보정하는 순간 원본의 펫↔제품 짝이 끊어지므로,
    제품과 체구도 보정된 펫에 맞춰 다시 잡는다. 본문은 review_body() 가 새로 쓴다.
    """
    if not SOURCE_REVIEWS.exists():
        print(f'  {SOURCE_REVIEWS.name} 없음 — 구매·후기를 전량 합성한다')
        return [], []

    pet_by_id = {p[0]: p for p in pets}
    product_by_id = {p[0]: p for p in products}
    pets_by_user = {}
    for p in pets:
        pets_by_user.setdefault(p[1], []).append(p)

    # 축종이 어긋났을 때 갈아탈 후보. 같은 분류를 우선 찾아 후기의 구매 동기가 안 틀어지게 한다.
    by_animal, by_animal_cat = {}, {}
    for p in products:
        for a in animals_of.get(p[0], ()):
            by_animal.setdefault(a, []).append(p)
            by_animal_cat.setdefault((a, p[1]), []).append(p)

    purchases, reviews, remapped, swapped = [], [], 0, 0
    for src in read_csv(SOURCE_REVIEWS):
        purchase_id = int(src['purchase_id'][1:])
        pet_id = int(src['pet_id'][1:])
        # 원본 pet_id 는 이 시드의 펫 수보다 크다. 같은 고객의 펫으로, 없으면 체구가
        # 가장 가까운 펫으로 옮겨 붙인다. FK 가 성립해야 적재가 된다.
        if pet_id not in pet_by_id:
            same_user = pets_by_user.get(int(src['customer_id'][1:]))
            want = SIZE_CODE[src['size_category']]
            pet_id = (min(same_user, key=lambda r: r[0])[0] if same_user else
                      min(pets, key=lambda r: (abs(r[7] - want), r[0]))[0])
            remapped += 1

        pet = pet_by_id[pet_id]
        product = product_by_id[int(src['product_id'][1:])]
        # 이 아이에게 줄 수 없는 제품이면 같은 분류 안에서 바꾼다. 축종 0행 제품은
        # 그대로 둔다 — '모르는 것을 안전으로 치지 않는다'를 관측할 표본이라서다.
        target = animals_of.get(product[0])
        if target and pet[2] not in target:
            product = rng.choice(by_animal_cat.get((pet[2], product[1]))
                                 or by_animal[pet[2]])
            swapped += 1

        # 구매는 아이 등록과 제품 등록 둘 다보다 뒤여야 한다. 하한을 넘는 원본 날짜는
        # 살리되 시각을 그 날 안에서 뽑고, 하한보다 이르면 경계값으로 누르지 않고
        # 유효 구간에서 다시 뽑는다. 누르면 여러 건이 같은 초에 겹쳐
        # '같은 아이가 같은 제품을 같은 순간에 두 번 산' 행이 생긴다(실측 18쌍).
        floor = max(datetime.fromisoformat(pet[11]), datetime.fromisoformat(product[15]))
        day = datetime.strptime(src['purchased_at'], '%Y-%m-%d').date()
        day_end = min(as_dt(day, end_of_day=True), NOW)
        bought = rdt(max(as_dt(day), floor), day_end) if day_end >= floor else rdt(floor, NOW)

        age_month = age_months(pet[5], bought.isoformat())
        rating = int(src['rating'])
        # 체구도 보정된 펫의 것을 쓴다. 원본 값을 그대로 두면 소형견 구매행에 '대형'이 남는다.
        purchases.append((purchase_id, pet_id, product[0], int(src['quantity']),
                          product[5], age_month, pet[7], dt(bought)))
        reviews.append((purchase_id, rating,
                        review_body(pet, product, rating, age_month,
                                    allergen_of.get(pet_id), purpose_of.get(product[0])),
                        int(src['is_holdout']), dt(bought)))

    print(f'  {SOURCE_REVIEWS.name} {len(purchases)}건 연결 (펫 보정 {remapped}건, 축종 안 맞아 제품 교체 {swapped}건)')
    return purchases, reviews


def gen_purchases(pets, products, p_animals, pet_allergies, purposes):
    """원본을 먼저 옮기고, 모자란 만큼 시드끼리 이어 붙여 합성한다."""
    # 후기가 인용할 사실. 알러지는 펼쳐 저장돼 있어 그대로 쓰면 한 아이가 29개까지 나온다.
    # 보호자가 실제로 고른 최상위(부모가 함께 선택되지 않은 것)만 남겨 하나 뽑는다.
    by_pet = {}
    for pid, aid in pet_allergies:
        by_pet.setdefault(pid, set()).add(aid)
    allergen_of = {}
    for pid, owned in by_pet.items():
        top = [a for a in owned if ALLERGEN_PARENT.get(a) not in owned]
        allergen_of[pid] = ALLERGEN_NAME[min(top)]
    purpose_of = {}
    for pid, fp in purposes:
        purpose_of.setdefault(pid, set()).add(fp)

    animals_of = {}
    for pid, a in p_animals:
        animals_of.setdefault(pid, set()).add(a)

    purchases, reviews = from_source(pets, products, animals_of, allergen_of, purpose_of)

    live_pets = [p for p in pets if p[10] is None]           # inactive_at NULL
    live_products = [p for p in products if p[14] == 1]      # is_active

    n = N_EXTRA_PURCHASES if purchases else N_SOLO_PURCHASES
    next_id = max((r[0] for r in purchases), default=0) + 1
    for purchase_id in range(next_id, next_id + n):
        pet = rng.choice(live_pets)
        # 축종이 맞는 제품만 산다. 후보가 없으면(축종 0행뿐) 아무거나 — FK 는 통과한다.
        cands = [p for p in live_products if pet[2] in animals_of.get(p[0], ())]
        product = rng.choice(cands or live_products)
        bought = rdt(max(datetime.fromisoformat(pet[11]),
                         datetime.fromisoformat(product[15])), NOW)
        rating = pick([(1, 8), (2, 10), (3, 20), (4, 32), (5, 30)])

        age_month = age_months(pet[5], bought.isoformat())   # SQL 은 생일 근처가 틀린다
        purchases.append((
            purchase_id, pet[0], product[0], rng.randint(1, 5),
            product[5],                                     # 그때 가격
            age_month, pet[7], dt(bought),
        ))
        reviews.append((
            purchase_id, rating,
            review_body(pet, product, rating, age_month,
                        allergen_of.get(pet[0]), purpose_of.get(product[0])),
            1 if rng.random() < 0.10 else 0,                # is_holdout. 색인에서 뺀다
            dt(min(NOW, bought + timedelta(days=rng.randint(1, 14)))),
        ))

    print(f'  합성 구매·후기 {n}건 추가')
    return purchases, reviews


# ---------------------------------------------------------------------------

def main():
    print(f'seed={SEED}  today={TODAY}')
    print(f'\n[master] (읽기만 함) allergen {len(allergen_rows)} / breed {len(breed_rows)} / '
          f'ingredient {len(ingredient_rows)} / ingredient_allergen {len(ing_allergen_rows)}')

    users = gen_users()
    pets, pet_breeds, pet_allergies = gen_pets(users)
    products, p_animals, nutrition, purposes, p_ings = gen_products()
    purchases, reviews = gen_purchases(pets, products, p_animals, pet_allergies, purposes)

    print('\n[seed]')
    write_csv('user', ['user_id', 'auth_provider', 'auth_uid', 'email', 'name', 'phone', 'region',
                       'last_login_at', 'withdrawn_at', 'created_at', 'updated_at'], users)
    write_csv('pet', ['pet_id', 'user_id', 'animal_category_id', 'name', 'gender', 'birth_date',
                      'weight_kg', 'size', 'body_type', 'neutered', 'inactive_at',
                      'created_at', 'updated_at'], pets)
    write_csv('pet_breed', ['pet_id', 'breed_id'], pet_breeds)
    write_csv('pet_allergy', ['pet_id', 'allergen_id'], pet_allergies)
    write_csv('product', ['product_id', 'product_category_id', 'brand', 'name', 'food_form',
                          'price_krw', 'weight_g', 'kcal_per_100g', 'target_size_min',
                          'target_size_max', 'target_age_min_month', 'target_age_max_month',
                          'description', 'ingredients_verified', 'is_active',
                          'created_at', 'updated_at'], products)
    write_csv('product_animal_category', ['product_id', 'animal_category_id'], p_animals)
    write_csv('product_nutrition', ['product_id', 'crude_protein_pct', 'crude_fat_pct',
                                    'crude_fiber_pct', 'crude_ash_pct', 'moisture_pct',
                                    'calcium_pct', 'phosphorus_pct', 'sodium_pct'], nutrition)
    write_csv('product_feeding_purpose', ['product_id', 'feeding_purpose_id'], purposes)
    write_csv('product_ingredient', ['product_id', 'ingredient_id'], p_ings)
    write_csv('purchase', ['purchase_id', 'pet_id', 'product_id', 'quantity', 'unit_price_krw',
                           'age_month_at_purchase', 'size_at_purchase', 'purchased_at'], purchases)
    write_csv('review', ['purchase_id', 'rating', 'body', 'is_holdout', 'reviewed_at'], reviews)

    # 여기가 무너지면 판정 3분법을 시험할 수 없다.
    allergic = len({p for p, _ in pet_allergies})
    print(f'\n펫 {len(pets)}마리 중 알러지 {allergic}마리 (펼친 행 {len(pet_allergies)}개)')
    print(f'제품 {N_PRODUCTS}개 중 verified=0 {sum(1 for p in products if p[13] == 0)}개 / '
          f'축종 0행 {N_PRODUCTS - len({p for p, _ in p_animals})}개')


if __name__ == '__main__':
    main()
