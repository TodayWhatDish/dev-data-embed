"""IP별 요청 제한(api/deps.rate_limit)이 한도에서 429 를 주고, 시간이 지나면 풀리는지 본다. DB 안 씀.

    py -m tests.api.rate_limit
"""

from unittest import mock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api import deps

if __name__ == "__main__":
    app = FastAPI()
    clock = [100.0]

    @app.get("/x", dependencies=[Depends(deps.rate_limit(3, 60))])
    def x():
        return "ok"

    with mock.patch.object(deps.time, "monotonic", lambda: clock[0]):
        c = TestClient(app)
        codes = [c.get("/x").status_code for _ in range(4)]
        print("한도 3회, 4번 호출:", codes)
        assert codes == [200, 200, 200, 429]
        assert c.get("/x").headers["retry-after"] == "60"

        clock[0] += 60  # 창이 지나면 다시 허용
        assert c.get("/x").status_code == 200
    print("ok")
