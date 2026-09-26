# Last updated: 2026-09-08
"""계층 의존 방향을 강제한다. import 문만 읽으므로 DB 도 모델도 안 띄운다.

핵심은 두 줄이다 -
  * 도메인은 순수 규칙만 안다 (domain -> 바깥 계층 app.core 등 · DB 드라이버 금지)
  * repositories 는 SELECT 만 한다 (repositories -> domain/services 금지)

사람 눈으로만 지키다 보면 급할 때 도메인에서 repo 를 한 번 부르고 그게 굳는다.
그러면 도메인 자체검증에 DB 가 필요해지고, 그 시점엔 이미 되돌리기 비싸다.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

DOMAIN_EXEMPT = {"domain_init.py"}
# candidates()가 con 없이 단독 호출될 때(CLI/eval)의 fallback 하나만 예외
SERVICES_PIPELINE_EXEMPT = {"searching.py"}

RULES = [
    (
        "domain",
        ("app.repositories", "app.core", "app.adapters", "app.services", "app.api", "pipeline", "sqlalchemy", "psycopg"),
        DOMAIN_EXEMPT,
    ),
    ("repositories", ("app.domain", "app.services"), set()),
    ("core", ("app.repositories", "app.adapters", "app.services", "app.api", "pipeline", "fastapi"), set()),
    ("adapters", ("app.services", "app.api", "pipeline"), set()),
    ("services", ("app.api", "pipeline"), SERVICES_PIPELINE_EXEMPT),
    ("api", ("pipeline", "app.repositories"), set()),
]


def imports_of(path: Path) -> list[str]:
    """그 파일이 끌어오는 모듈 이름들. from X import y 는 X 만 본다"""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def cases():
    for layer, banned, exempt in RULES:
        for path in sorted((APP / layer).rglob("*.py")):
            if path.name not in exempt:
                yield pytest.param(path, banned, id=f"{layer}/{path.name}")


@pytest.mark.parametrize("path, banned", list(cases()))
def test_layer_imports(path, banned):
    hit = [m for m in imports_of(path) if m.startswith(banned)]
    assert not hit, f"{path.name} 이 {hit} 를 끌어온다"
