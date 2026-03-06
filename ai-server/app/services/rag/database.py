import pandas as pd
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Result
from datetime import datetime, UTC
from typing import Optional

from .config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME, SIMULATE_DEFAULT

def make_async_engine(simulate: bool = False) -> AsyncEngine:
    if not simulate:
        dsn = f"mysql+aiomysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        dsn = "sqlite+aiosqlite:///:memory:"
    return create_async_engine(dsn, pool_pre_ping=True, future=True)

async def bootstrap_simulation(conn: AsyncConnection):
    await conn.execute(text("""
        CREATE TABLE knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            description TEXT NOT NULL,
            role TEXT,
            details TEXT,
            updated_at TEXT NOT NULL
        );
    """))
    rows = [
        ("어텐션 메커니즘",
         "어텐션은 입력의 중요한 부분에 가중치를 부여해 정보를 통합하는 기법이다. 시퀀스 처리에서 문맥 의존성을 강화한다.",
         "입력 토큰 간 상호연관성을 계산하며 정보 흐름을 개선한다.",
         "Transformer의 핵심 구성요소로 번역·요약 등에서 성능을 끌어올린다.",
         datetime.now(UTC).isoformat(timespec="seconds")),
        ("Self-Attention",
         "Self-Attention은 동일 시퀀스 내 토큰들이 서로를 참조하여 가중합을 구한다. RNN의 순차 의존성을 줄여 병렬화를 가능케 한다.",
         "장기 의존성 문제를 완화하고 각 토큰의 전역 문맥 파악을 돕는다.",
         "멀티헤드로 다양한 표현 공간에서 주의를 분산해 학습을 안정화한다.",
         datetime.now(UTC).isoformat(timespec="seconds")),
        ("FAISS",
         "FAISS는 대규모 벡터에 대한 빠른 유사도 검색을 제공한다. 근사 최근접 탐색을 지원한다.",
         "대규모 임베딩 인덱싱과 빠른 검색을 제공한다.",
         "Facebook AI Research에서 개발되었고 CPU/GPU 백엔드를 제공한다.",
         datetime.now(UTC).isoformat(timespec="seconds")),
    ]
    for t, d, r, det, up in rows:
        await conn.execute(
            text("INSERT INTO knowledge(term, description, role, details, updated_at) VALUES (:t,:d,:r,:det,:u)"),
            {"t": t, "d": d, "r": r, "det": det, "u": up}
        )
    await conn.commit()

async def ensure_connection(engine: AsyncEngine, simulate: bool) -> AsyncEngine:
    async with engine.begin() as conn:
        if simulate:
            await bootstrap_simulation(conn)
        else:
            await conn.execute(text("SELECT 1"))
    return engine

TITLE_CANDIDATES = {"title","name","term","keyword","subject","heading"}
TEXT_CANDIDATES  = {"body","content","description","details","text","summary","note","notes","paragraph","article"}
ID_CANDIDATES    = {"id","pk","gid","uid"}

async def async_get_columns(engine: AsyncEngine, table: str):
    async with engine.connect() as conn:
        def _inspect(sync_conn):
            insp = sa_inspect(sync_conn)
            return insp.get_columns(table)
        return await conn.run_sync(_inspect)

async def infer_schema(engine: AsyncEngine, table: str, id_col=None, title_col=None, text_cols=None):
    cols_info = await async_get_columns(engine, table)
    cols = [c["name"] for c in cols_info]
    def pick(cands):
        for c in cols:
            if c.lower() in cands:
                return c
        return None
    _id = id_col or pick(ID_CANDIDATES) or (cols[0] if cols else None)
    _title = title_col or pick(TITLE_CANDIDATES)
    _texts = text_cols or [c for c in cols if c.lower() in TEXT_CANDIDATES]
    if not _texts:
        _texts = [c for c in cols if c != _title]
    return _id, _title, _texts, cols

async def fetch_table(engine: AsyncEngine, table: str, columns=None, limit=None) -> pd.DataFrame:
    def _qt(name: str) -> str:
        return f"`{str(name).replace('`', '``')}`"

    async with engine.connect() as conn:
        def _inspect(sync_conn):
            insp = sa_inspect(sync_conn)
            return {c["name"] for c in insp.get_columns(table)}
        available_cols = await conn.run_sync(_inspect)

    if columns:
        use_cols = [c for c in columns if c in available_cols]
        if not use_cols:
            raise ValueError(f"No valid columns in request. available={sorted(available_cols)}")
    else:
        use_cols = sorted(list(available_cols))

    cols_sql = ", ".join(_qt(c) for c in use_cols) if use_cols else "*"
    sql = f"SELECT {cols_sql} FROM {_qt(table)}"

    if limit is not None:
        try:
            n = int(limit)
            if n > 0:
                sql += f" LIMIT {n}"
        except Exception:
            pass

    async with engine.connect() as conn:
        result: Result = await conn.execute(text(sql))
        rows = [dict(r._mapping) for r in result.fetchall()]

    for row in rows:
        for k, v in list(row.items()):
            if isinstance(v, bytes):
                row[k] = v.decode("utf-8", "ignore")
            elif v is None:
                row[k] = ""

    return pd.DataFrame(rows)

ASYNC_ENGINE: Optional[AsyncEngine] = None

async def get_engine() -> AsyncEngine:
    global ASYNC_ENGINE
    if ASYNC_ENGINE is None:
        ASYNC_ENGINE = await ensure_connection(
            make_async_engine(simulate=SIMULATE_DEFAULT), SIMULATE_DEFAULT
        )
    return ASYNC_ENGINE
