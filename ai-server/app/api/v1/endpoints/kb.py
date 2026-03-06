from fastapi import APIRouter

router = APIRouter()

@router.post("/ingest")
async def ingest_knowledge(type: str = "manual"):
    return {"source_id": "kb_doc_001", "chunk_count": 156}

@router.get("/status")
async def check_kb_status():
    return {"indexing_progress": "100%", "last_updated": "2024-10-25"}
