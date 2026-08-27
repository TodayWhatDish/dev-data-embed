---
name: pet-reco
description: "Runs the pet-reco data pipeline (load_db.py -> check_data.py -> prepare.py -> build_index.py) and the query CLI. Use when asked to rebuild pet_reco.db, re-embed reviews, regenerate chunk_vectors, or debug why the pipeline order/output looks wrong."
---

# /pet-reco

## Usage

```
/pet-reco   # 전체 파이프라인을 순서대로 실행
```

## Steps

1. `python pipeline/load_db.py` 실행 — `data/*.csv`를 `pet_reco.db`로 적재.
2. `python pipeline/check_data.py` 실행. 정합성 문제가 출력되면 **조용히 넘어가지 말고** 결과를 그대로 사용자에게 보여준 뒤 계속할지 물어본다 (이 검사 자체가 "파이프라인이 에러 없이 조용히 깨질 수 있다"는 문제 때문에 존재함).
3. `python pipeline/prepare.py` 실행 — 리뷰를 임베딩용 문서로 조립하고 토큰 한도로 자른다. 벡터는 아직 안 만든다.
4. `python pipeline/build_index.py` 실행 — 인코딩에 수십 초 걸릴 수 있음, 오래 걸려도 정상이라고 안내할 것.
5. 사용자가 검색 결과를 확인하고 싶어하면 `python pipeline/query.py`로 대화형 CLI를 띄운다 (필수 단계 아님, 원할 때만).

각 단계는 앞 단계의 산출물을 읽으므로 순서를 건너뛰지 않는다.
