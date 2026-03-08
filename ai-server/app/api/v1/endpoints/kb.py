from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.rag.rag_pipeline import Document, FAISSStore, FAISS_INDEX_DIR
from app.services.pipeline import workflow as pipeline_workflow


router = APIRouter()


def _build_manual_documents(db: Session) -> List[Document]:
    rows = db.execute(
        text(
            """
            SELECT doc_id, title, category, source, related_dtc_code, content, created_at
            FROM manual_docs
            ORDER BY doc_id ASC
            """
        )
    ).mappings().all()

    documents: List[Document] = []
    for row in rows:
        dtc = row.get("related_dtc_code") or "N/A"
        body = (
            f"[Manual] {row['title']}\n"
            f"Category: {row['category']}\n"
            f"Source: {row['source']}\n"
            f"DTC: {dtc}\n"
            f"Content: {row['content']}"
        )
        documents.append(
            Document(
                doc_id=f"manual-{row['doc_id']}",
                content=body,
                metadata={
                    "table": "manual_docs",
                    "doc_id": int(row["doc_id"]),
                    "title": row["title"],
                    "category": row["category"],
                    "related_dtc_code": row.get("related_dtc_code"),
                    "created_at": str(row.get("created_at")),
                },
            )
        )
    return documents


def _build_case_documents(db: Session) -> List[Document]:
    rows = db.execute(
        text(
            """
            SELECT case_id, dtc_code, symptom, root_cause, action_steps, result_summary, reference_doc_id, created_at
            FROM case_db
            ORDER BY case_id ASC
            """
        )
    ).mappings().all()

    documents: List[Document] = []
    for row in rows:
        body = (
            f"[Case] #{row['case_id']} DTC={row['dtc_code']}\n"
            f"Symptom: {row['symptom']}\n"
            f"RootCause: {row['root_cause']}\n"
            f"ActionSteps: {row['action_steps']}\n"
            f"ResultSummary: {row.get('result_summary') or 'N/A'}"
        )
        documents.append(
            Document(
                doc_id=f"case-{row['case_id']}",
                content=body,
                metadata={
                    "table": "case_db",
                    "case_id": int(row["case_id"]),
                    "dtc_code": row["dtc_code"],
                    "reference_doc_id": row.get("reference_doc_id"),
                    "created_at": str(row.get("created_at")),
                },
            )
        )
    return documents


def _chunk_documents(documents: List[Document], chunk_size: int, chunk_overlap: int) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunked: List[Document] = []
    for source_doc in documents:
        chunks = splitter.split_text(source_doc.content)
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            meta = dict(source_doc.metadata)
            meta["chunk_index"] = idx
            meta["chunk_total"] = total
            meta["source_doc_id"] = source_doc.doc_id
            chunked.append(
                Document(
                    doc_id=f"{source_doc.doc_id}#chunk-{idx}",
                    content=chunk,
                    metadata=meta,
                )
            )
    return chunked


@router.post("/ingest")
async def ingest_knowledge(
    source: str = "all",
    chunk_size: int = 600,
    chunk_overlap: int = 120,
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """
    DB(manual_docs, case_db)에서 문서를 읽고 청킹 후 FAISS 인덱스를 갱신한다.
    source: all | manual | case
    """
    source_normalized = source.lower().strip()
    use_manual = source_normalized in {"all", "manual"}
    use_case = source_normalized in {"all", "case"}

    base_docs: List[Document] = []
    manual_count = 0
    case_count = 0

    if use_manual:
        manual_docs = _build_manual_documents(db)
        manual_count = len(manual_docs)
        base_docs.extend(manual_docs)
    if use_case:
        case_docs = _build_case_documents(db)
        case_count = len(case_docs)
        base_docs.extend(case_docs)

    chunk_docs = _chunk_documents(base_docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if dry_run:
        return {
            "status": "dry_run",
            "source": source_normalized,
            "manual_docs": manual_count,
            "case_docs": case_count,
            "source_docs": len(base_docs),
            "chunk_count": len(chunk_docs),
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }

    store = FAISSStore(index_dir=str(FAISS_INDEX_DIR))
    added = store.add_documents(chunk_docs)
    store.save()

    # RAG 파이프라인이 즉시 최신 인덱스를 사용하도록 전역 store 교체
    pipeline_workflow.faiss_store = store

    return {
        "status": "ok",
        "source": source_normalized,
        "manual_docs": manual_count,
        "case_docs": case_count,
        "source_docs": len(base_docs),
        "chunk_count": len(chunk_docs),
        "indexed_docs": added,
        "vector_store_docs": store.total_docs,
        "index_dir": str(FAISS_INDEX_DIR),
        "updated_at": datetime.utcnow().isoformat(),
    }


@router.get("/status")
async def check_kb_status():
    store = FAISSStore(index_dir=str(FAISS_INDEX_DIR))
    loaded = store.load()
    docs_path = Path(FAISS_INDEX_DIR) / "documents.json"
    index_path = Path(FAISS_INDEX_DIR) / "index.faiss"

    last_updated = None
    if docs_path.exists():
        last_updated = datetime.fromtimestamp(docs_path.stat().st_mtime).isoformat()

    return {
        "loaded": loaded,
        "index_dir": str(FAISS_INDEX_DIR),
        "vector_docs": store.total_docs if loaded else 0,
        "documents_file_exists": docs_path.exists(),
        "index_file_exists": index_path.exists(),
        "last_updated": last_updated,
    }
