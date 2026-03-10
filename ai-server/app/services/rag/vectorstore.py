import logging
import os
import textwrap
from typing import List, Optional

import pandas as pd
import torch
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import CFG, EMBED_MODEL
from .utils import ensure_two_sentences


rag_log = logging.getLogger("rag")


def build_expanded_text(
    row: pd.Series,
    id_col: Optional[str],
    title_col: Optional[str],
    text_cols: List[str],
):
    title_val = (row[title_col] if title_col and title_col in row else None) or ""
    base_texts = []
    for col in text_cols:
        value = row.get(col, None)
        if isinstance(value, str):
            base_texts.append(value)

    base = " ".join([t.strip() for t in base_texts if t])
    oo = str(title_val).strip() or (base.split()[0] if base else "항목")
    two = ensure_two_sentences(base if base else f"{oo}에 대한 설명이 데이터베이스에 포함되어 있다.")

    expanded = (
        f"[정의] {oo}는 무엇인가? {two}\n"
        f"[역할] {oo}의 역할은 무엇인가? {ensure_two_sentences(base)}\n"
        f"[설명] {oo}를 설명하라: {ensure_two_sentences(base)}\n"
        f"[키워드] {oo}, 정의, 역할, 설명, 개요, 특징, 장점, 한계"
    )
    meta = {"OO": oo}
    return "passage: " + expanded + "\n\n" + base, meta


def to_documents(
    df: pd.DataFrame,
    id_col: Optional[str],
    title_col: Optional[str],
    text_cols: List[str],
) -> List[Document]:
    docs: List[Document] = []
    for _, row in df.iterrows():
        page_content, meta_extra = build_expanded_text(row, id_col, title_col, text_cols)
        meta = meta_extra.copy()

        if id_col and id_col in row:
            meta["id"] = int(row[id_col]) if pd.notna(row[id_col]) else None
        if title_col and title_col in row:
            meta["title"] = str(row[title_col])

        for col in text_cols:
            value = row.get(col, None)
            if isinstance(value, str):
                meta[col] = value[:3000]

        docs.append(Document(page_content=page_content, metadata=meta))
    return docs


def split_documents(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CFG.chunk_size,
        chunk_overlap=CFG.chunk_overlap,
        separators=["\n\n", "\n", "。", ". ", ".", "? ", "?", "! ", "!", " "],
    )
    chunks = splitter.split_documents(docs)
    print("청크 수:", len(chunks))
    return chunks


def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cuda" if torch.cuda.is_available() else "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
    )


def build_and_save_faiss(chunks: List[Document], save_dir: str, emb) -> FAISS:
    os.makedirs(save_dir, exist_ok=True)
    vs = FAISS.from_documents(chunks, emb)
    vs.save_local(save_dir)
    print("FAISS 저장:", save_dir)
    return vs


def load_faiss(save_dir: str, emb) -> FAISS:
    return FAISS.load_local(save_dir, emb, allow_dangerous_deserialization=True)


def format_query_for_bge(q: str) -> str:
    return f"query: {q.strip()}"


def similarity_search_with_margin(
    vs: FAISS,
    query: str,
    k: int,
    margin: float,
    sim_floor: float = 0.35,
) -> list[tuple]:
    q = format_query_for_bge(query)
    pairs = vs.similarity_search_with_score(q, k=k)
    if not pairs:
        return []

    metric_type = getattr(getattr(vs, "index", None), "metric_type", None)
    try:
        import faiss

        is_ip = metric_type == faiss.METRIC_INNER_PRODUCT
    except Exception:
        is_ip = False

    if is_ip:
        pairs.sort(key=lambda x: float(x[1]), reverse=True)
        raw = [float(score) for _, score in pairs]
        hi = max(1.0, max(raw))
        lo = min(-1.0, min(raw))
        sims = [(r - lo) / (hi - lo + 1e-9) for r in raw]
    else:
        pairs.sort(key=lambda x: float(x[1]))
        dists = [float(dist) for _, dist in pairs]
        sims = [1.0 / (1.0 + dist) for dist in dists]

    docs = [doc for doc, _ in pairs]
    best = sims[0]
    cut = max(best - margin, best * (1.0 - margin))
    kept = [(doc, score) for doc, score in zip(docs, sims) if score >= cut and score >= sim_floor]

    rag_log.debug(
        "retrieval metric=%s best=%.3f cut=%.3f floor=%.2f sims=%s kept=%d",
        "IP" if is_ip else "L2",
        best,
        cut,
        sim_floor,
        [round(x, 3) for x in sims[: min(5, len(sims))]],
        len(kept),
    )
    return kept[:k]


def build_marked_context(docs_with_scores: List[tuple]) -> str:
    buf = ["<CONTEXT>"]
    total_chars = 0

    for i, (doc, score) in enumerate(docs_with_scores, start=1):
        meta, text = (doc.metadata or {}), (doc.page_content or "")
        remain = max(CFG.max_context_chars - total_chars, 0)
        if remain <= 0:
            break

        snippet = textwrap.shorten(text.replace("\n", " "), width=min(900, remain), placeholder="…")
        total_chars += len(snippet)
        buf.append(
            f"《S{i}》 [id={meta.get('id', '')}] [title={meta.get('title', '')}] [OO={meta.get('OO', '')}] score={score:.4f}\n"
            f"{snippet}\n"
        )

    buf.append("</CONTEXT>")
    return "\n".join(buf)
