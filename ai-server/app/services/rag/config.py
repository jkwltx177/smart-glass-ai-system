import os
from dataclasses import dataclass

MODEL_NAME = os.getenv("QWEN_MODEL", "qwen/Qwen1.5-0.5B-Chat")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

FAISS_ROOT = os.getenv("FAISS_ROOT", "faiss_db")
os.makedirs(FAISS_ROOT, exist_ok=True)

# 컨테이너 MariaDB 연결(비동기)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3379"))
DB_USER = os.getenv("DB_USER", "manager")
DB_PASS = os.getenv("DB_PASS", "SqlDba-1")
DB_NAME = os.getenv("DB_NAME", "sql_db")

# CPU 친화
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "6")
os.environ.setdefault("MKL_NUM_THREADS", "6")

@dataclass
class RAGConfig:
    chunk_size: int = 100
    chunk_overlap: int = 10
    top_k: int = 5
    score_margin: float = 0.12
    max_context_chars: int = 1800
    max_new_tokens: int = 64
    temperature: float = 0.0
    fetch_multiplier: int = 4
    per_title_cap: int = 3

CFG = RAGConfig()
SCHEMA_TABLE = "knowledge"
SIMULATE_DEFAULT = True
