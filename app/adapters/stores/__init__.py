# Last Updated : 2026-09-03

"""벡터 저장소를 만들어 주는 자리. 부르는 쪽은 어떤 구현인지 몰라도 된다."""


def get_store(con):
    """VectorStore 구현을 돌려준다. 순환 import 를 피하려고 함수 안에서 import 한다."""
    from app.adapters.stores.sqlite_store import SqliteVectorStore
    return SqliteVectorStore(con)
