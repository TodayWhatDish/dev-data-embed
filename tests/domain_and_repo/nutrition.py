from app.repositories.products import find_nutritions

if __name__ == "__main__":
    got = find_nutritions([1,2])
    print(got)
    assert set(got) <= {1,2}
    assert all("crude_protein_pct" in v for v in got.values())
    assert find_nutritions([]) == {}
    print("ok")