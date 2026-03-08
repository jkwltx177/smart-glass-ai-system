# 2026-03-06 작성
# Smart Glass RAG Pipeline
# - 입력: ai_payload (예측 결과) + 이미지 설명 텍스트 + 사용자 발화 텍스트
# - Vector DB: FAISS (로컬 파일 기반)
# - Embedding: OpenAI text-embedding-3-small
# - LLM: OpenAI GPT (gpt-4o-mini)
# - 입력: 사용자 발화 + 이미지 설명 + 예측형 AI 결과
# 1) 검색 쿼리 생성
# 2) OpenAI embedding으로 벡터화
# 3) FAISS에서 유사 문서 검색
# 4) 검색 결과 + 예측 결과 + 질문을 하나의 프롬프트로 조립
# 5) GPT 호출
# 6) escalation 여부 판단
# - 출력: 최종 답변 + 검색 문서
#    + failure probability + anomaly score + predicted RUL + escalation flag


import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

import numpy as np
from dotenv import load_dotenv

# 프로젝트 루트의 .env 파일을 로드한다.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")

# =========================================================
# 1. 설정
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
FAISS_INDEX_DIR = BASE_DIR / "faiss_store"

# OpenAI API 키는 환경변수에서 읽는다.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536  # text-embedding-3-small 차원

LLM_MODEL = "gpt-4o-mini"
LLM_MAX_TOKENS = 1024

# 검색 시 반환할 최대 문서 수
TOP_K = 3


# =========================================================
# 2. 데이터 클래스
# =========================================================

@dataclass
class RAGInput:
    """
    RAG 파이프라인의 통합 입력 구조.
    ai_pipeline의 prepare_ai_response_payload 출력,
    이미지 설명 텍스트, 사용자 발화 텍스트를 하나로 묶는다.
    """
    user_query: str                          # 사용자 발화 (STT 변환 결과)
    image_description: str = ""              # Vision LLM 이미지 분석 결과
    ai_payload: Dict[str, Any] = field(default_factory=dict)  # prepare_ai_response_payload 출력

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RAGResult:
    """
    RAG 파이프라인 최종 출력 구조.
    백엔드 API 응답, 프론트엔드 표시, TTS 출력에 그대로 사용 가능하다.
    """
    answer: str = ""
    confidence: float = 0.0
    retrieved_docs: List[Dict[str, Any]] = field(default_factory=list)
    predicted_rul_minutes: Optional[int] = None
    failure_probability: Optional[float] = None
    anomaly_score: Optional[float] = None
    escalation_needed: bool = False
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Document:
    """
    Vector DB에 저장되는 문서 단위.
    매뉴얼, 유사 사례, 조치 절차 등을 담는다.
    """
    doc_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# =========================================================
# 3. OpenAI API 호출 유틸
# =========================================================

def _get_openai_client():
    """OpenAI 클라이언트를 반환한다. 미설치 시 안내 메시지를 출력한다."""
    try:
        from openai import OpenAI
        api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY 환경변수를 설정해라. "
                "예: export OPENAI_API_KEY='sk-...'"
            )
        return OpenAI(api_key=api_key)
    except ImportError:
        raise ImportError("openai 패키지를 설치해라: pip install openai")


def get_embedding(text: str) -> np.ndarray:
    """
    텍스트를 OpenAI Embedding API로 벡터화한다.

    Args:
        text: 임베딩할 문자열

    Returns:
        1차원 numpy 배열 (dim=1536)
    """
    client = _get_openai_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return np.array(response.data[0].embedding, dtype=np.float32)


def call_llm(prompt: str, system_prompt: str = "") -> str:
    """
    OpenAI GPT에 프롬프트를 보내고 응답 텍스트를 반환한다.

    Args:
        prompt: 사용자 프롬프트 (컨텍스트 + 질문)
        system_prompt: 시스템 역할 설정

    Returns:
        LLM 응답 문자열
    """
    client = _get_openai_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=LLM_MAX_TOKENS,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# =========================================================
# 4. FAISS Vector Store 관리
# =========================================================

class FAISSStore:
    """
    FAISS 기반 로컬 벡터 저장소.
    문서 추가, 검색, 저장/로드를 지원한다.
    """

    def __init__(self, index_dir: str = str(FAISS_INDEX_DIR)):
        try:
            import faiss
        except ImportError:
            raise ImportError("faiss 패키지를 설치해라: pip install faiss-cpu")

        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self._faiss = faiss
        self.index = faiss.IndexFlatL2(EMBEDDING_DIM)
        self.documents: List[Document] = []

    def add_documents(self, documents: List[Document]) -> int:
        """
        문서 리스트를 임베딩하여 FAISS 인덱스에 추가한다.

        Args:
            documents: 추가할 Document 리스트

        Returns:
            추가된 문서 수
        """
        if not documents:
            return 0

        texts = [doc.content for doc in documents]
        embeddings = np.array(
            [get_embedding(text) for text in texts],
            dtype=np.float32,
        )

        self.index.add(embeddings)
        self.documents.extend(documents)
        return len(documents)

    def search(self, query: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
        """
        쿼리 텍스트로 유사 문서를 검색한다.

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 최대 문서 수

        Returns:
            doc_id, content, metadata, score를 담은 dict 리스트
        """
        if self.index.ntotal == 0:
            return []

        query_vec = get_embedding(query).reshape(1, -1)
        distances, indices = self.index.search(query_vec, min(top_k, self.index.ntotal))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            doc = self.documents[idx]
            results.append({
                "doc_id": doc.doc_id,
                "content": doc.content,
                "metadata": doc.metadata,
                "score": round(float(dist), 4),
            })
        return results

    def save(self) -> None:
        """인덱스와 문서 메타데이터를 파일로 저장한다."""
        self._faiss.write_index(
            self.index, str(self.index_dir / "index.faiss")
        )
        docs_data = [
            {"doc_id": d.doc_id, "content": d.content, "metadata": d.metadata}
            for d in self.documents
        ]
        with open(self.index_dir / "documents.json", "w", encoding="utf-8") as f:
            json.dump(docs_data, f, ensure_ascii=False, indent=2)

    def load(self) -> bool:
        """
        저장된 인덱스와 문서를 로드한다.

        Returns:
            로드 성공 여부
        """
        index_path = self.index_dir / "index.faiss"
        docs_path = self.index_dir / "documents.json"

        if not index_path.exists() or not docs_path.exists():
            return False

        self.index = self._faiss.read_index(str(index_path))
        with open(docs_path, "r", encoding="utf-8") as f:
            docs_data = json.load(f)

        self.documents = [
            Document(
                doc_id=d["doc_id"],
                content=d["content"],
                metadata=d.get("metadata", {}),
            )
            for d in docs_data
        ]
        return True

    @property
    def total_docs(self) -> int:
        return len(self.documents)


# =========================================================
# 5. 쿼리 생성 (구조화된 입력 → 검색 쿼리)
# =========================================================

def build_search_query(rag_input: RAGInput) -> str:
    """
    RAGInput의 사용자 발화, 이미지 설명, 예측 결과를 조합하여
    Vector DB 검색에 적합한 쿼리 문자열을 생성한다.

    Args:
        rag_input: 통합 입력

    Returns:
        검색 쿼리 문자열
    """
    parts = [rag_input.user_query]

    if rag_input.image_description:
        parts.append(f"이미지 분석: {rag_input.image_description}")

    # 예측 결과에서 핵심 정보를 쿼리에 반영한다.
    predictive = rag_input.ai_payload.get("predictive_ai", {})
    if predictive:
        prob = predictive.get("failure_probability", 0)
        rul = predictive.get("predicted_rul_minutes")
        if prob and prob > 0.5:
            parts.append("고장 확률 높음 긴급 조치 필요")
        if rul and rul < 30:
            parts.append("잔여 수명 임박 안전 절차 우선")

    return " ".join(parts)


# =========================================================
# 6. 프롬프트 생성
# =========================================================

SYSTEM_PROMPT = """너는 스마트 글래스 기반 설비 진단 AI 어시스턴트이다.
현장 작업자에게 정확하고 실행 가능한 조치를 안내해야 한다.
반드시 아래 형식으로 답변해라:

1. **조치 절차** (Action): 우선순위를 포함한 구체적 점검/조치 단계
2. **근거** (Explanation): 판단 근거 (매뉴얼, 유사 사례 인용)
3. **리스크** (Risk): 안전/품질 리스크 및 작업 중단 기준
4. **에스컬레이션** (Escalation): 본사/품질팀 호출 조건"""


def build_llm_prompt(
    rag_input: RAGInput,
    retrieved_docs: List[Dict[str, Any]],
) -> str:
    """
    검색 결과와 구조화된 입력을 결합하여 LLM 프롬프트를 생성한다.

    Args:
        rag_input: 통합 입력
        retrieved_docs: FAISS 검색 결과

    Returns:
        LLM에 보낼 프롬프트 문자열
    """
    sections = []

    # 사용자 질문
    sections.append(f"## 사용자 질문\n{rag_input.user_query}")

    # 이미지 분석
    if rag_input.image_description:
        sections.append(f"## 이미지 분석 결과\n{rag_input.image_description}")

    # 예측 결과
    predictive = rag_input.ai_payload.get("predictive_ai", {})
    ts_summary = rag_input.ai_payload.get("timeseries_summary", {})
    if predictive:
        pred_text = json.dumps(predictive, ensure_ascii=False, indent=2)
        sections.append(f"## 설비 예측 AI 결과\n```json\n{pred_text}\n```")
    if ts_summary:
        ts_text = json.dumps(ts_summary, ensure_ascii=False, indent=2)
        sections.append(f"## 시계열 요약\n```json\n{ts_text}\n```")

    # 에러 로그
    error_logs = rag_input.ai_payload.get("recent_error_logs", [])
    if error_logs:
        log_text = json.dumps(error_logs, ensure_ascii=False, indent=2)
        sections.append(f"## 최근 에러 로그\n```json\n{log_text}\n```")

    # RAG 검색 결과
    if retrieved_docs:
        doc_texts = []
        for i, doc in enumerate(retrieved_docs, 1):
            doc_texts.append(f"[문서 {i}] {doc['content']}")
        sections.append(f"## 참고 문서 (Vector DB 검색 결과)\n" + "\n\n".join(doc_texts))
    else:
        sections.append("## 참고 문서\n(검색 결과 없음 — 일반 지식 기반으로 답변)")

    return "\n\n".join(sections)


# =========================================================
# 7. RAG 파이프라인 실행
# =========================================================

def run_rag_pipeline(
    rag_input: RAGInput,
    vector_store: Optional[FAISSStore] = None,
    top_k: int = TOP_K,
) -> RAGResult:
    """
    전체 RAG 파이프라인을 실행한다.
    1) 검색 쿼리 생성
    2) Vector DB 검색
    3) LLM 프롬프트 조립
    4) GPT 호출 → 최종 응답 생성

    Args:
        rag_input: 통합 입력 (사용자 발화 + 이미지 설명 + ai_payload)
        vector_store: FAISS 벡터 저장소 (None이면 검색 건너뜀)
        top_k: 검색 문서 수

    Returns:
        RAGResult dataclass
    """
    # 1) 검색 쿼리 생성
    search_query = build_search_query(rag_input)

    # 2) Vector DB 검색
    retrieved_docs = []
    if vector_store and vector_store.total_docs > 0:
        retrieved_docs = vector_store.search(search_query, top_k=top_k)

    # 3) LLM 프롬프트 조립
    prompt = build_llm_prompt(rag_input, retrieved_docs)

    # 4) GPT 호출
    answer = call_llm(prompt, system_prompt=SYSTEM_PROMPT)

    # 5) 예측 결과에서 에스컬레이션 판단
    predictive = rag_input.ai_payload.get("predictive_ai", {})
    failure_prob = predictive.get("failure_probability")
    rul = predictive.get("predicted_rul_minutes")
    anomaly = predictive.get("anomaly_score")

    escalation_needed = False
    if failure_prob is not None and failure_prob > 0.7:
        escalation_needed = True
    if rul is not None and rul < 30:
        escalation_needed = True

    return RAGResult(
        answer=answer,
        confidence=round(1.0 - (failure_prob or 0.0), 2),
        retrieved_docs=retrieved_docs,
        predicted_rul_minutes=rul,
        failure_probability=failure_prob,
        anomaly_score=anomaly,
        escalation_needed=escalation_needed,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# =========================================================
# 8. Vector Store 초기화
# =========================================================

def init_vector_store(index_dir: str = str(FAISS_INDEX_DIR)) -> FAISSStore:
    """
    기존 FAISS 인덱스를 로드한다.
    인덱스가 아직 없으면 빈 저장소를 반환한다.
    """
    store = FAISSStore(index_dir=index_dir)
    store.load()
    return store
