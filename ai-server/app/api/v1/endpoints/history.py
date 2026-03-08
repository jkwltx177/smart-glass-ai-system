"""
분석 이력(History) API

RAG 요청 및 분석 이력을 조회합니다.
"""

from fastapi import APIRouter
from typing import List

from app.schemas.api_models import HistoryLogItem, HistoryListResponse

router = APIRouter()

# DUMMY 데이터: 실제 개발 시 DB 또는 로그에서 조회
DUMMY_HISTORY = [
    {"id": "REQ-9402", "timestamp": "2026-03-06 14:22:10", "type": "Multimodal", "status": "Success", "latency": "1.2s"},
    {"id": "REQ-9401", "timestamp": "2026-03-06 13:05:45", "type": "Audio Only", "status": "Success", "latency": "0.8s"},

]


@router.get("/", response_model=HistoryListResponse)
async def get_analysis_history():
    """
    분석 이력 목록을 조회합니다.
    현재는 DUMMY 데이터를 반환하며, 추후 DB 연동 시 실제 데이터로 교체합니다.
    """
    items = [HistoryLogItem(**item) for item in DUMMY_HISTORY]
    return HistoryListResponse(
        items=items,
        total=len(items),
    )
