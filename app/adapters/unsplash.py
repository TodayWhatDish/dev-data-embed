"""Unsplash 사진 정보 조회. 키는 서버 .env에만 둔다."""

from functools import lru_cache

import requests

from app.core.config import UNSPLASH_ACCESS_KEY


# ponytail: 만료 없는 캐시 - 고정 사진 한 장이라 충분하다. 저작자 정보가 바뀌어도 재시작 전까진 옛 값.
# 사진을 바꿔 쓰게 되면 TTL 캐시로. 실패(예외)는 캐시되지 않아 다음 요청이 다시 시도한다.
@lru_cache(maxsize=8)
def fetch_photo(photo_id: str) -> dict:
    """사진 URL + 저작자 크레딧. 연결 실패나 비정상 응답이면 requests.RequestException."""
    res = requests.get(
        f"https://api.unsplash.com/photos/{photo_id}",
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
        timeout=5,
    )
    res.raise_for_status()
    photo = res.json()
    return {
        "url": photo["urls"]["regular"],
        "credit_name": photo["user"]["name"],
        "credit_link": photo["user"]["links"]["html"],
    }
