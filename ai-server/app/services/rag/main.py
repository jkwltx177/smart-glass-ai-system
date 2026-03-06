import os
import time
import logging
import asyncio
import traceback
import inspect
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.exc import SQLAlchemyError

from langchain_community.vectorstores import FAISS

from .config import CFG, FAISS_ROOT, SCHEMA_TABLE
from .models import IngestRequest, IngestResponse, QueryRequest, QueryResponse
from .database import get_engine, fetch_table, infer_schema, ensure_connection, make_async_engine
from .vectorstore import to_documents, split_documents, get_embeddings, build_and_save_faiss, load_faiss
from .llm import get_qwen, answer_question

log = logging.getLogger("perf")
logger = logging.getLogger(__name__)

VECTORSTORE_CACHE = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = await get_engine()
    if engine is None:
        raise RuntimeError("Failed to initialize DB engine")
    app.state.DB_ENGINE = engine

    app.state.QWEN = None
    app.state.QWEN_ERROR = None
    try:
        tok, mdl = get_qwen()
        app.state.QWEN = (tok, mdl)
        try:
            mdl.eval()
        except Exception:
            pass
        print(f"✅ Qwen ready (device={getattr(mdl, 'device', 'unknown')}, dtype={getattr(mdl, 'dtype', 'unknown')})")
    except Exception:
        app.state.QWEN_ERROR = traceback.format_exc()
        print("⚠️ Qwen init failed:
", app.state.QWEN_ERROR)

    app.state.EMB = None
    app.state.EMB_ERROR = None
    try:
        emb = await get_embeddings() if inspect.iscoroutinefunction(get_embeddings) else get_embeddings()
        if emb is None:
            raise RuntimeError("get_embeddings() returned None")
        if not (hasattr(emb, "embed_query") or hasattr(emb, "encode")):
            raise RuntimeError("embedding client has no expected methods")
        app.state.EMB = emb
        print("✅ Embeddings client ready")
    except Exception:
        app.state.EMB_ERROR = traceback.format_exc()
        print("⚠️ Embeddings init failed:
", app.state.EMB_ERROR)

    _id, _title, _texts, _all = await infer_schema(engine, SCHEMA_TABLE)
    app.state.SCHEMA_INFO = {
        "id_col": _id, "title_col": _title, "text_cols": _texts, "all_cols": _all
    }

    try:
        df = await fetch_table(engine, SCHEMA_TABLE, limit=5)
        app.state.SAMPLE_DF_HEAD = df.head() if df is not None else None
    except Exception:
        app.state.SAMPLE_DF_HEAD = None
        raise

    try:
        yield
    finally:
        eng = getattr(app.state, "DB_ENGINE", None)
        if eng is not None:
            res = getattr(eng, "dispose", lambda: None)()
            if inspect.isawaitable(res):
                await res
        print("🧹 Shutdown cleanup done")


app = FastAPI(
    title="RAG 기반 Open Weight LLM API Server",
    description="내부 정보 기반 벡터화 + LLM 질의 응답, Async RAG API (MariaDB→FAISS→Qwen)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8002",
        "file://",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/schema/preview")
async def schema_preview(req: Request):
    head = getattr(req.app.state, "SAMPLE_DF_HEAD", None)
    return {
        "schema": getattr(req.app.state, "SCHEMA_INFO", None),
        "head": head.to_dict(orient="records") if head is not None else None,
    }

@app.get("/health")
async def health(req: Request):
    resp = {
        "engine_ready": getattr(req.app.state, "DB_ENGINE", None) is not None,
        "emb_ready":    getattr(req.app.state, "EMB", None) is not None,
    }
    err = getattr(req.app.state, "EMB_ERROR", None)
    if err is not None:
        resp["emb_error"] = err
    return resp

@app.get("/db-tables", summary="내부 DB 테이블 목록 조회", tags=["내부 정보"])
async def list_tables(simulate: bool = Query(False, description="True=SQLite 시뮬레이션, False=MariaDB")):
    try:
        engine = make_async_engine(simulate=simulate)
        await ensure_connection(engine, simulate)

        async with engine.connect() as conn:
            def _list_all(sync_conn):
                insp = sa_inspect(sync_conn)
                tables = insp.get_table_names()
                views  = getattr(insp, "get_view_names", lambda: [])()
                return tables, views

            tables, views = await conn.run_sync(_list_all)

        return {
            "ok": True,
            "simulate": simulate,
            "backend": "sqlite+aiosqlite" if simulate else "mysql+aiomysql",
            "tables": tables,
            "views": views,
        }
    except HTTPException:
        raise
    except SQLAlchemyError as se:
        logger.exception("SQLAlchemy error while listing tables")
        raise HTTPException(status_code=500, detail=f"DB 오류: {se}")
    except Exception as e:
        logger.exception("Unhandled error while listing tables")
        raise HTTPException(status_code=500, detail=f"DB 테이블 조회 실패: {e}")

@app.post("/ingest", response_model=IngestResponse)
async def ingest_table_api(req: IngestRequest, request: Request):
    try:
        engine = make_async_engine(simulate=req.simulate)
        await ensure_connection(engine, req.simulate)
        _id, _title, _texts, all_cols = await infer_schema(engine, req.table, req.id_col, req.title_col, req.text_cols)
        if not _texts:
            raise HTTPException(status_code=400, detail="텍스트 컬럼을 찾을 수 없습니다. text_cols를 지정하세요.")
        df = await fetch_table(engine, req.table)

        docs = await asyncio.to_thread(to_documents, df, _id, _title, _texts)
        chunks = await asyncio.to_thread(split_documents, docs)

        save_name = req.save_name or req.table
        save_dir = os.path.join(FAISS_ROOT, save_name)
        
        EMB = getattr(request.app.state, "EMB", None)
        if EMB is None:
            EMB = get_embeddings()

        vs = await asyncio.to_thread(build_and_save_faiss, chunks, save_dir, EMB)
        VECTORSTORE_CACHE[save_name] = vs

        return IngestResponse(
            ok=True, save_dir=save_dir, rows=len(df), chunks=len(chunks),
            schema={"id_col": _id, "title_col": _title, "text_cols": _texts, "all_cols": all_cols}
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion 실패: {e}")

@app.post("/query", response_model=QueryResponse)
async def query_api(req: QueryRequest, resp: Response, request: Request):
    t0 = time.perf_counter()

    cache_hit = False
    faiss_load_s = 0.0
    vs = VECTORSTORE_CACHE.get(req.save_name)
    if vs is None:
        t_load0 = time.perf_counter()
        save_dir = os.path.join(FAISS_ROOT, req.save_name)
        
        EMB = getattr(request.app.state, "EMB", None)
        if EMB is None:
            EMB = get_embeddings()

        vs = await asyncio.to_thread(load_faiss, save_dir, EMB)
        VECTORSTORE_CACHE[req.save_name] = vs
        faiss_load_s = time.perf_counter() - t_load0
    else:
        cache_hit = True

    old_k, old_m = CFG.top_k, CFG.score_margin
    answer_s = 0.0
    try:
        CFG.top_k, CFG.score_margin = req.top_k, req.margin

        t_a0 = time.perf_counter()
        qwen_instance = getattr(request.app.state, "QWEN", None)
        out = await answer_question(vs, req.question, qwen_instance)
        answer_s = time.perf_counter() - t_a0

    except Exception as e:
        total = time.perf_counter() - t0
        log.error(
            "query FAIL save=%s cache_hit=%s faiss_load=%.3fs answer=%.3fs total=%.3fs err=%r",
            req.save_name, cache_hit, faiss_load_s, answer_s, total, e
        )
        raise HTTPException(status_code=500, detail=f"Query 실패: {e}") from e
    finally:
        CFG.top_k, CFG.score_margin = old_k, old_m

    t_s0 = time.perf_counter()
    result = QueryResponse(answer=out["answer"], sources=out["sources"])
    serialize_s = time.perf_counter() - t_s0

    total = time.perf_counter() - t0

    resp.headers["X-Perf-Cache-Hit"]      = "1" if cache_hit else "0"
    resp.headers["X-Perf-FAISS-Load-s"]   = f"{faiss_load_s:.3f}"
    resp.headers["X-Perf-Answer-s"]       = f"{answer_s:.3f}"
    resp.headers["X-Perf-Serialize-s"]    = f"{serialize_s:.3f}"
    resp.headers["X-Perf-Total-s"]        = f"{total:.3f}"
    resp.headers["X-Perf-TopK"]           = str(req.top_k)
    resp.headers["X-Perf-Margin"]         = str(req.margin)

    log.warning(
        "perf save=%s cache_hit=%s faiss_load=%.3fs answer=%.3fs serialize=%.3fs total=%.3fs top_k=%s margin=%s",
        req.save_name, cache_hit, faiss_load_s, answer_s, serialize_s, total, req.top_k, req.margin
    )

    return result

@app.get("/status")
async def status_api():
    entries = []
    if os.path.isdir(FAISS_ROOT):
        for name in os.listdir(FAISS_ROOT):
            if os.path.isdir(os.path.join(FAISS_ROOT, name)):
                entries.append(name)
    return {"faiss_indices": entries, "cache_keys": list(VECTORSTORE_CACHE.keys())}

print("✅ Async FastAPI 라우트 준비 완료: /db-tables /ingest, /query, /status")
