# Last Updated : 2026-08-31

"""검색 엔드포인트. app/query.py의 CLI와 같은 흐름(build_profile -> build_where -> search)을
   HTTP 요청으로 노출한다.
"""

from fastapi import APIRouter, Request

from app.api.schemas import SearchHit, SearchRequest, SearchResponse
from app.features.profile import build_profile
from app.features.retrieve import build_where, fmt_purchase_id
from pipeline.vector_db import search

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search_reviews(payload: SearchRequest, request: Request) -> SearchResponse:
    con = request.app.state.con

    profile = build_profile(payload.model_dump(exclude={"query", "top_k"}))
    where, params = build_where(profile)
    hits = search(con, payload.query, where=where, params=params, top_k=payload.top_k)

    return SearchResponse(
        hits=[
            SearchHit(
                purchase_id=fmt_purchase_id(pid),
                score=round(score, 3),
                text=doc.removeprefix("passage: "),
            )
            for pid, score, doc in hits
        ]
    )
