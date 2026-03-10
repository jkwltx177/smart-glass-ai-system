import os
import re
import time
import torch
import unicodedata
import logging
import asyncio
from typing import Dict, Any, List
from collections import defaultdict
from functools import lru_cache
from transformers import AutoModelForCausalLM, AutoTokenizer
from langchain_community.vectorstores import FAISS

from .config import MODEL_NAME, CFG
from .utils import _anchors_from_query, _contains_any, _get_text, _ensure_topic_prefix, _clean_korean, ensure_min_sentences
from .vectorstore import similarity_search_with_margin, build_marked_context

perf_log = logging.getLogger("perf.qwen")

def get_threads():
    try:
        return min(int(os.environ.get("OMP_NUM_THREADS","6")), os.cpu_count() or 6)
    except Exception:
        return 6

def load_qwen():
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    tok = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True, use_fast=True)
    if torch.cuda.is_available():
        mdl = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME, dtype=dtype, device_map="auto", trust_remote_code=True
        )
    else:
        mdl = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME, dtype=dtype, device_map={"": "cpu"},
            low_cpu_mem_usage=True, trust_remote_code=True
        )
        torch.set_num_threads(get_threads())
    mdl.eval()
    return tok, mdl

@lru_cache(maxsize=1)
def get_qwen():
    tok, mdl = load_qwen()
    try:
        mdl.eval()
    except Exception:
        pass
    return tok, mdl

def _qwen_answer_sync(prompt: str, qwen_instance=None) -> str:
    t0 = time.perf_counter()
    try:
        if qwen_instance:
            tok, mdl = qwen_instance
        else:
            tok, mdl = get_qwen()
    except Exception:
        tok, mdl = get_qwen()
    mdl.eval()

    messages = [
        {
            "role": "system",
            "content": (
                "당신은 한국어로만 답하는 RAG 어시스턴트입니다. "
                "아래 CONTEXT의 정보만 사용하세요. 충분하지 않으면 정확히 "
                "'지식베이스에서 답을 찾지 못했습니다.' 라고만 답하세요. "
                "영문 병기는 사용하지 말고, Self-Attention→셀프-어텐션, "
                "sequence→시퀀스, token→토큰처럼 한국어 표기로 답하세요. "
                "문장은 2~3문장으로 간결하게 작성합니다."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    tmpl = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)

    model_ctx     = int(getattr(mdl.config, "max_position_embeddings", getattr(tok, "model_max_length", 4096)))
    max_new       = int(getattr(CFG, "max_new_tokens", 256))
    max_input_len = max(32, model_ctx - max_new)

    enc = tok(tmpl, return_tensors="pt", truncation=True, max_length=max_input_len)
    enc = {k: v.to(mdl.device) for k, v in enc.items()}

    try:
        im_end_id = tok.convert_tokens_to_ids("<|im_end|>")
    except Exception:
        im_end_id = None
    eos_ids = [tok.eos_token_id] + ([im_end_id] if isinstance(im_end_id, int) and im_end_id >= 0 else [])

    with torch.inference_mode():
        out = mdl.generate(
            input_ids=enc["input_ids"],
            attention_mask=enc.get("attention_mask"),
            max_new_tokens=max_new,
            min_new_tokens=min(48, max_new),
            do_sample=True,
            temperature=0.2,
            top_p=0.9,
            top_k=50,
            repetition_penalty=1.0,
            eos_token_id=eos_ids,
            pad_token_id=tok.pad_token_id if getattr(tok, "pad_token_id", None) is not None else tok.eos_token_id,
            use_cache=True,
        )

    input_len = int(enc["input_ids"].shape[1])
    gen_ids   = out[0][input_len:]
    text_dec  = tok.decode(gen_ids, skip_special_tokens=True)
    text_dec  = re.split(r"<\|im_end\|>", text_dec, maxsplit=1)[0]

    def _ko_postprocess(s: str) -> str:
        s = unicodedata.normalize("NFC", s)
        for pat, ko in [
            (r"\bself[\-\s]?attention\b", "셀프-어텐션"),
            (r"\battention\b",           "어텐션"),
            (r"\bsequence(s)?\b",        "시퀀스"),
            (r"\btoken(s)?\b",           "토큰"),
            (r"\bmodel(s)?\b",           "모델"),
        ]:
            s = re.sub(pat, ko, s, flags=re.I)
        s = s.replace("自注意力", "셀프-어텐션").replace("注意力", "어텐션").replace("序列", "시퀀스")
        s = re.sub(r"[ 	]+", " ", s)
        s = re.sub(r"\s+([,.;:!?%])", r"\1", s)
        s = re.sub(r"\(\s+", "(", s); s = re.sub(r"\s+\)", ")", s)
        s = re.sub(r"([,.;:!?])\s*\1+", r"\1", s)
        return s.strip()

    decoded = _ko_postprocess(text_dec.strip())
    answer  = ensure_min_sentences(decoded, 2) if decoded else "지식베이스에서 답을 찾지 못했습니다."

    perf_log.warning("qwen total=%.3fs", time.perf_counter() - t0)
    return answer

async def qwen_answer(prompt: str, qwen_instance=None) -> str:
    return await asyncio.to_thread(_qwen_answer_sync, prompt, qwen_instance)

def _answer_question_sync(vs: FAISS, question: str, qwen_instance=None) -> Dict[str, Any]:
    T0 = time.perf_counter()
    tA0 = time.perf_counter()
    top_k = int(getattr(CFG, "top_k", 5))
    fetch_mult = max(1, int(getattr(CFG, "fetch_multiplier", 4)))
    fetch_k = max(top_k * fetch_mult, top_k + 5)

    kept = similarity_search_with_margin(vs, question, fetch_k, CFG.score_margin)
    tA1 = time.perf_counter()
    fetched_n = len(kept)

    if not kept:
        perf_log.warning("rag timing retrieve=%.3fs assemble=%.3fs llm=%.3fs total=%.3fs (no hits)", tA1 - tA0, 0.0, 0.0, time.perf_counter() - T0)
        return {"answer": "지식베이스에서 답을 찾지 못했습니다.", "sources": []}

    strong, weak = _anchors_from_query(question)
    def _hit(doc, keys: set[str]) -> bool:
        return _contains_any(_get_text(doc), keys) or _contains_any((doc.metadata or {}).get("title", ""), keys)

    if not strong:
        return {"answer": "지식베이스에서 답을 찾지 못했습니다.", "sources": []}

    kept = [(d, s) for (d, s) in kept if _hit(d, strong)]
    if not kept:
        perf_log.warning("rag timing retrieve=%.3fs assemble=%.3fs llm=%.3fs total=%.3fs (strong_anchor_miss)", tA1 - tA0, 0.0, 0.0, time.perf_counter() - T0)
        return {"answer": "지식베이스에서 답을 찾지 못했습니다.", "sources": []}
    after_anchor_n = len(kept)

    cap = max(1, int(getattr(CFG, "per_title_cap", 3)))
    groups = defaultdict(list)
    for d, s in kept:
        meta = d.metadata or {}
        from .utils import _norm
        key = _norm(meta.get("title") or meta.get("OO") or _get_text(d)[:30])
        groups[key].append((d, s))

    for k in list(groups.keys()):
        groups[k].sort(key=lambda x: float(x[1]), reverse=True)
        groups[k] = groups[k][:cap]

    kept_final: List[tuple] = []
    buckets = list(groups.values())
    i = 0
    while len(kept_final) < top_k and buckets:
        progressed = False
        for b in list(buckets):
            if i < len(b):
                kept_final.append(b[i])
                progressed = True
                if len(kept_final) >= top_k:
                    break
        if not progressed:
            break
        i += 1

    if not kept_final:
        return {"answer": "지식베이스에서 답을 찾지 못했습니다.", "sources": []}

    tB0 = time.perf_counter()
    ctx = build_marked_context(kept_final)
    strong_txt = ", ".join(sorted(strong)) if strong else ""

    top_meta = (kept_final[0][0].metadata or {})
    topic = top_meta.get("title") or top_meta.get("OO") or ""

    prompt = (
        "역할: 내부 지식베이스 기반 RAG 어시스턴트.\n"
        "규칙:\n"
        "1) 반드시 한국어로만 답한다.\n"
        "2) 아래 CONTEXT 안의 정보만 사용한다. CONTEXT 밖 지식/추측/상식은 금지.\n"
        "3) 충분한 정보가 없으면 정확히 다음 문장으로만 답한다: '지식베이스에서 답을 찾지 못했습니다.'\n"
        "4) 인용한 문장 뒤에는 [S1], [S2] 형태의 마커를 붙인다.\n"
        f"주제 용어: {topic}\n"
        f"핵심어(강 앵커): {strong_txt}\n\n"
        f"{ctx}\n\n"
        f"사용자 질문: {question}\n"
    )
    tB1 = time.perf_counter()

    tC0 = time.perf_counter()
    ans = _qwen_answer_sync(prompt, qwen_instance)
    if ans and topic:
        ans = _ensure_topic_prefix(ans, topic)
    tC1 = time.perf_counter()

    srcs = [{
        "marker": f"S{j+1}",
        "id":     (doc.metadata or {}).get("id"),
        "title":  (doc.metadata or {}).get("title"),
        "OO":     (doc.metadata or {}).get("OO"),
        "score":  float(score),
    } for j, (doc, score) in enumerate(kept_final)]

    T1 = time.perf_counter()
    perf_log.warning(
        "rag timing retrieve=%.3fs assemble=%.3fs llm=%.3fs total=%.3fs (fetched=%d after_anchor=%d grouped=%d final=%d)",
        tA1 - tA0, tB1 - tB0, tC1 - tC0, T1 - T0, fetched_n, after_anchor_n, len(groups), len(kept_final)
    )

    return {"answer": ans, "sources": srcs}

async def answer_question(vs: FAISS, question: str, qwen_instance=None) -> Dict[str, Any]:
    return await asyncio.to_thread(_answer_question_sync, vs, question, qwen_instance)
