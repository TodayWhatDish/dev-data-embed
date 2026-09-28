from app.core.db import new_session
from app.repositories.products import find_nutritions

if __name__ == "__main__":
    db = new_session()
    got = find_nutritions(db, [1,2])
    print(got)
    assert set(got) <= {1,2}
    assert all("crude_protein_pct" in v for v in got.values())
    assert find_nutritions(db, []) == {}
    print("ok")