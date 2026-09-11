#!/bin/sh
# 컨테이너 시작 스크립트.
#
# render.yaml의 persistent disk가 /app/data에 마운트되면서 두 가지 문제가 있었다:
#   1. 마운트가 이미지에 구워둔 data/master, data/seed를 통째로 가린다 (Dockerfile 참고).
#   2. 디스크가 비어있으면 pet_reco.db 자체가 없어 앱이 부팅도 못 하고 죽는다.
# 둘 다 여기서 한 번에 해결한다. 디스크는 영속적이라 이 초기화는 디스크가 비어있는
# 최초 1회(또는 디스크를 새로 붙였을 때)만 실제로 돈다 - 그다음 재시작부턴 통과만 한다.
set -e

[ -d data/master ] || cp -r _seed/master data/master
[ -d data/seed ] || cp -r _seed/seed data/seed

if [ ! -f data/pet_reco.db ]; then
    echo "[entrypoint] pet_reco.db 없음 - 파이프라인으로 새로 만든다"
    python -m pipeline.load_csv
    python -m pipeline.chunk
    python -m pipeline.embed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
