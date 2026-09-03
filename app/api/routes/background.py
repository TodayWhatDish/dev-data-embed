# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""고객 페이지 배경 이미지용 Unsplash 프록시.

    Access Key는 서버 .env에만 두고, 프론트는 이 엔드포인트만 부른다
    (정적 페이지라 키를 프론트 JS에 두면 그대로 git에 커밋되고 view-source로도 노출된다).
"""

import requests
from fastapi import APIRouter, HTTPException

from app.core.config import UNSPLASH_ACCESS_KEY

router = APIRouter()

# 배경 사진을 이 한 장으로 고정한다 (요청받은 사진: unsplash.com/photos/ouo1hbizWwo)
FIXED_PHOTO_ID = "ouo1hbizWwo"


@router.get("/background")
def background() -> dict:
    """고정된 배경 이미지 URL + 저작자 정보를 돌려준다.

    저작자 크레딧은 Unsplash API 가이드라인상 필수라 photographer 이름/링크를 같이 내려준다.
    """
    if not UNSPLASH_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="UNSPLASH_ACCESS_KEY가 설정되지 않았습니다.")

    try:
        res = requests.get(
            f"https://api.unsplash.com/photos/{FIXED_PHOTO_ID}",
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=5,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Unsplash에 연결할 수 없습니다.") from exc

    if not res.ok:
        raise HTTPException(status_code=502, detail="Unsplash 요청에 실패했습니다.")

    photo = res.json()
    return {
        "url": photo["urls"]["regular"],
        "credit_name": photo["user"]["name"],
        "credit_link": photo["user"]["links"]["html"],
    }
