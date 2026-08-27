# Last Updated: 2026-08-25
"""
[클로드 임시 코드]
SQL에서 계산하지 않고 어플리케이션에서 계산하고 저장하기 위해 생성.

반려동물 파생값 계산 — 나이.

DB 에서 하지 않는다. SQLite 로 개월 나이를 내려면 julianday 차이를 30.44(평균 일수)로
나눠야 하는데 근사값이라 **생일 근처에서 정확히 틀린다** — 2023-03-15 생 아이의
2027-03-15(만 4년) 나이가 47개월로 나온다. 하필 퍼피/성견/노견 경계가 걸리는 지점이다.

여기서는 달력으로 센다. 근사가 없다.

    py src/petcalc.py     # self-check
"""


def age_months(birth_date, at):
    """만 개월 나이. 생일 당일에 개월이 오른다.

    birth_date / at 은 'YYYY-MM-DD' 또는 'YYYY-MM-DD HH:MM:SS' 문자열.
    birth_date 가 없으면(미입력) None — 0 으로 뭉개면 '모름'이 '신생아'가 된다.
    """
    if not birth_date:
        return None
    b = _ymd(birth_date)
    a = _ymd(at)
    months = (a[0] - b[0]) * 12 + (a[1] - b[1])
    if a[2] < b[2]:          # 그 달의 생일이 아직 안 지났다
        months -= 1
    return max(months, 0)


def _ymd(s):
    d = s[:10]
    return int(d[:4]), int(d[5:7]), int(d[8:10])


def _demo():
    B = '2023-03-15'
    cases = [
        (B, '2023-03-15', 0),    # 태어난 날
        (B, '2023-04-14', 0),    # 생일 하루 전
        (B, '2023-04-15', 1),    # 생일 당일에 오른다
        (B, '2024-03-15', 12),
        (B, '2024-03-14', 11),
        (B, '2027-03-15', 48),   # SQL /30.44 는 여기서 47 을 준다
        (B, '2026-08-25', 41),
        ('2024-02-29', '2025-02-28', 11),   # 윤년생, 평년 2월 말일
        ('2024-02-29', '2025-03-01', 12),
        (B, '2023-03-14', 0),    # 생일 전(입력 오류) -> 음수 대신 0
        (None, '2026-01-01', None),
        ('', '2026-01-01', None),
        (B + ' 09:30:00', '2024-03-15 21:00:00', 12),   # 시각이 붙어도 같다
    ]
    for birth, at, want in cases:
        got = age_months(birth, at)
        assert got == want, f'age_months({birth!r}, {at!r}) = {got}, want {want}'
    print(f'ok - {len(cases)}개 경계 케이스 통과')


if __name__ == '__main__':
    _demo()
