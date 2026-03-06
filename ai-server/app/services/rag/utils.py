import re
import unicodedata

_HANGUL_OR_WORD = re.compile(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9\-_/]+")

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().lower()

def _keywords(s: str) -> set[str]:
    return {w for w in _HANGUL_OR_WORD.findall(_norm(s)) if len(w) >= 2}

def _contains_any(text: str, keys: set[str]) -> bool:
    if not keys: 
        return False
    t = _norm(text)
    return any(k in t for k in keys)

_WEAK_KO = {
    "무엇", "무엇인가", "뭐야", "뭔가", "정의", "설명", "설명하라", "설명해",
    "역할", "개요", "특징", "장점", "한계", "의미", "소개", "예시", "예", "비교"
}
_WEAK_EN = {"what", "define", "definition", "explain", "role", "overview", "feature", "pros", "cons"}

def _anchors_from_query(q: str) -> tuple[set[str], set[str]]:
    base = _keywords(q)
    strong, weak = set(), set()
    for w in base:
        if w in _WEAK_KO or w in _WEAK_EN:
            weak.add(w)
        else:
            strong.add(w)

    n = _norm(q)
    if re.search(r"\brag\b", n):
        strong |= {"rag", "retrieval augmented generation", "리트리벌 증강 생성", "리트리벌"}
    if "faiss" in n:
        strong |= {"faiss"}
    if "self-attention" in n or "self attention" in n:
        strong |= {"self-attention", "self attention", "셀프어텐션", "셀프 어텐션", "자기주의", "자기-주의"}
    if "attention" in n:
        strong |= {"attention", "어텐션", "주의"}

    strong = {_norm(x) for x in strong}
    weak   = {_norm(x) for x in weak}
    return strong, weak

def _get_text(doc) -> str:
    return _norm((doc.page_content or "").replace("passage:", " "))

_EN_WHITELIST = {
    "CPU","GPU","TPU","RAM","ROM","RNN","LSTM","GRU","LLM","NLP","AI",
    "FAISS","Qwen","BERT","GPT","SQL","JSON","API"
}

_EN2KO_PATTERNS = [
    (r"\bself[\-\s]?attention\b", "셀프-어텐션"),
    (r"\battention\b",           "어텐션"),
    (r"\bsequence(s)?\b",        "시퀀스"),
    (r"\btoken(s)?\b",           "토큰"),
    (r"\bmodel(s)?\b",           "모델"),
    (r"\bdata\b",                "데이터"),
    (r"\bpattern(s)?\b",         "패턴"),
    (r"\bweight(s)?\b",          "가중치"),
    (r"\bperformance\b",         "성능"),
    (r"\bspeed\b",               "속도"),
    (r"\boptimi[sz](e|ed|es|ing)\b", "최적화"),
    (r"\btable(s)?\b",           "테이블"),
]

_EN_WORD_RE = re.compile(r"[A-Za-z]{2,}[A-Za-z0-9_\-]*")

_CJK_KO_MAP = {"注意力":"어텐션", "自注意力":"셀프-어텐션", "序列":"시퀀스"}
_CJK_KO_PAT = re.compile("|".join(map(re.escape, _CJK_KO_MAP.keys())))

def _map_cjk_to_ko(text: str) -> str:
    return _CJK_KO_PAT.sub(lambda m: _CJK_KO_MAP[m.group(0)], text)

def _replace_en_to_ko(text: str) -> str:
    s = text
    s = _map_cjk_to_ko(s)
    for pat, ko in _EN2KO_PATTERNS:
        s = re.sub(pat, ko, s, flags=re.I)
    return s

def _clean_korean(text: str) -> str:
    if not text:
        return text
    s = unicodedata.normalize("NFC", text)
    if (s.startswith(("“",""","'","「","『")) and s.endswith(("”",""","'","」","』")) 
        and len(s) > 2):
        s = s[1:-1].strip()
    s = re.sub(r"[ 	]+", " ", s)
    s = re.sub(r"\s+([,.;:!?%])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\[\s+", "[", s)
    s = re.sub(r"\s+\]", "]", s)
    s = re.sub(r"([,.;:!?])\s*\1+", r"\1", s)
    return s.strip()

def _purge_unknown_english(text: str) -> str:
    slots = {}
    def _protect(m):
        key = f"@@S{len(slots)}@@"
        slots[key] = m.group(0)
        return key
    s = re.sub(r"\[S\d+\]", _protect, text)
    s = _replace_en_to_ko(s)
    def _keep_or_drop(m: re.Match) -> str:
        w = m.group(0)
        if w.upper() in _EN_WHITELIST:
            return w
        return ""
    s = _EN_WORD_RE.sub(_keep_or_drop, s)
    for k, v in slots.items():
        s = s.replace(k, v)
    return _clean_korean(s)

def _pick_eun_neun(word: str) -> str:
    if not word: return "는"
    last = word[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        jong = (code - 0xAC00) % 28
        return "은" if jong else "는"
    return "는"

def _ensure_topic_prefix(answer: str, topic: str) -> str:
    if not topic:
        return answer
    topic_ko = _replace_en_to_ko(topic)
    s = answer.strip()
    if s.startswith(topic_ko) or s.lower().startswith(topic.lower()):
        return s
    s = re.sub(r"^[,\s\-–—]*[은는]\b", "", s).lstrip()
    return f"{topic_ko}{_pick_eun_neun(topic_ko)} {s}"

SENT_SEP = re.compile(r"(?<=[.!?。])\s+")
def ensure_two_sentences(text: str) -> str:
    parts = [p.strip() for p in SENT_SEP.split(text) if p.strip()]
    if len(parts) >= 2:
        return " ".join(parts[:2])
    if parts:
        return parts[0] + " 추가적인 설명은 본문에 포함되어 있다."
    return "이 항목은 데이터베이스에 기술되어 있으며, 세부 내용은 본문을 참조한다."

def ensure_min_sentences(text: str, n: int = 2) -> str:
    parts = [p for p in SENT_SEP.split(text.strip()) if p.strip()]
    return text.strip() if len(parts) >= n else (text.strip() + " 추가 설명이 필요하면 관련 항목을 더 조회할 수 있습니다.")
