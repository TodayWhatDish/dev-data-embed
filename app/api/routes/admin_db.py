# Last Updated : 2026-09-11

"""로컬 pet_reco.db 를 배포 서버 디스크로 올리는 일회성 관리자 엔드포인트.
SSH/Docker Command 로 파일을 옮길 방법이 막혀서, 이미 있는 HTTPS 인그레스로 우회한다.
용도가 끝나면 이 파일과 main.py 등록 줄을 지운다."""

from fastapi import APIRouter, Depends, Request

from app.core.auth import get_current_admin
from app.core.config import DATA_DIR, DB_PATH

router = APIRouter()


@router.post("/admin/db/pet-reco", dependencies=[Depends(get_current_admin)])
async def upload_pet_reco_db(request: Request) -> dict:
    """raw body(바이트)를 그대로 받아 DB_PATH에 쓴다. 업로드 도중 죽어도 기존 DB가 깨지지 않도록
    임시 파일에 먼저 쓰고 os.replace로 한 번에 바꿔치기한다.
    커넥션은 스레드당 캐시돼 있어(app/core/db.py) 교체 후에도 기존 커넥션은 옛 파일을 계속 본다 -
    적용하려면 서비스 재시작이 필요하다."""
    tmp_path = DATA_DIR / f"{DB_PATH.name}.upload"
    body = await request.body()
    tmp_path.write_bytes(body)
    tmp_path.replace(DB_PATH)
    return {"bytes_written": len(body)}
