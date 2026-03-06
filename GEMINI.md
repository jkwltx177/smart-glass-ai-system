# 프로젝트 구조 설계 및 코드 통합 가이드 요청

## 1. 역할 및 목표
당신은 수석 소프트웨어 아키텍트이자 AI/백엔드 개발 전문가입니다. 
아래 제공된 **[시스템 아키텍처 및 데이터 흐름도]**를 분석하고, 현재 루트 디렉토리에 흩어져 있는 **[기술 스택별 템플릿 코드]**를 바탕으로 전체 프로젝트의 체계적인 디렉토리 구조(Monorepo 방식 또는 MSA 폴더 구조)를 설계해 주세요.

## 2. 시스템 아키텍처 및 데이터 흐름도
(스마트 글래스 기반 기계/설비 상태 진단 및 RUL 예측 AI 시스템)

```text
[사용자]
│
│ 음성 입력 / 이미지 입력
▼
[스마트 글래스 디바이스]
│
│ (API 요청)
▼
[Java 인증 서버]
│
│ 1. 사용자 인증
│ 2. Access Token 발급
│
▼
[AI 처리 서버 접근 허용]
│
│ Authorization: Bearer Token
▼
────────────────────────────────────
[AI Processing Server]
────────────────────────────────────
:zero: 설비/검사 장비 데이터 자동 수집
│
│ (공정/검사 장비에서 자동 수집)
├─ 로그 데이터 (Error/Event Log)
├─ 시계열 센서 데이터 (Temperature / Pressure / Current 등)
└─ 장비 ID / Lot / 시간정보 (Traceability)
│
└─ (API/Message Queue/DB)로 AI 서버에 연동
▼
:one: 입력 데이터 수집
│
├─ 음성 데이터 (Audio) ← 사용자(스마트글래스)
├─ 이미지 데이터 (Image) ← 사용자(스마트글래스)
└─ 시계열 데이터 (Time-series) ← 설비/검사 장비 자동 수집
├─ 온도/압력/전류/진동 등
└─ 이벤트/에러 로그(타임스탬프 포함)
▼
:two: 데이터 전처리 / 변환
음성 데이터
└─ STT (Speech To Text)
→ 음성 → 텍스트 문장 변환
이미지 데이터
└─ Vision LLM
→ 이미지 분석
→ 객체 / 상황 / 특징 추출
시계열 데이터
├─ 정규화/클리닝 (결측/이상치 처리)
├─ 윈도잉(Windowing) 및 특징 추출
│ ├─ 통계 특징(평균/분산/최대/최소)
│ ├─ 추세/변화율(gradient)
│ └─ 이벤트 기반 특징(에러코드 빈도/간격)
└─ (필요 시) 센서 융합(Sensor Fusion)
▼
:three: 예측형 AI 단계: RUL(고장까지 잔여수명) 예측
│
│ 입력: 시계열 특징 + 로그 특징 (+ 상황 태그)
└─ Predictive AI Model (예: LGBM/XGB/TCN 등)
→ 고장 확률 / 이상 점수 / RUL(잔여수명) 예측
│
├─ 예측 결과 생성
│ 예:
│ - predicted_rul_minutes: 120
│ - failure_probability: 0.63
│ - anomaly_score: 0.81
│
└─ 다음날/다음 배치 실제값 기반 성능평가(RMSE) 기록(AIOps)
▼
:four: LLM 구조화 단계
LLM 처리
├─ 사용자 발화 문장 이해
├─ 이미지 분석 결과 통합
├─ 시계열 기반 예측 결과(RUL/확률/이상점수) 통합
└─ 정형 데이터(JSON) 생성
예시 JSON
{
"user_intent": "엔진/칩 검사 중 오류 원인 및 조치 요청",
"objects_detected": ["엔진 베이", "커넥터", "센서"],
"observations": ["오염/느슨함 의심", "경고 LED 점등"],
"timeseries_summary": {
"temp_trend": "rising",
"pressure_trend": "unstable",
"error_log_pattern": "repeated within 10min"
},
"predictive_ai": {
"predicted_rul_minutes": 120,
"failure_probability": 0.63,
"anomaly_score": 0.81
},
"question": "현재 원인 후보와 즉시 조치, 에스컬레이션 기준을 알려줘"
}
▼
:five: RAG 기반 강화 검색
Query 생성
│
▼
Vector DB 검색
│
├─ 문서 검색
├─ 매뉴얼 검색
├─ 유사 사례(Case DB) 검색
└─ 예측 결과 기반 검색 보강
├─ RUL 임박 시: “긴급 조치/안전 절차” 우선
└─ 특정 센서/로그 패턴: “해당 패턴 사례” 우선
▼
:six: Qwen LLM 응답 생성
입력
├─ 사용자 질문
├─ 이미지 분석 결과
├─ RUL/고장확률 예측 결과
└─ RAG 검색 결과
처리
└─ Qwen LLM
▼
최종 답변 생성
├─ Action: 점검/조치 절차(우선순위 포함)
├─ Explanation: 근거(매뉴얼/사례 인용)
├─ Risk: 안전/품질 리스크 및 작업 중단 기준
└─ Escalation: 본사 품질팀/엔지니어 호출 조건
────────────────────────────────────
:seven: 응답 반환
서버 → 스마트 글래스
반환 데이터
{
"answer": "...",
"confidence": 0.92,
"predicted_rul_minutes": 120,
"failure_probability": 0.63,
"reference_docs": [...],
"escalation_condition": [...]
}
▼
[스마트 글래스]
├─ 화면 표시
└─ TTS 음성 출력
▼
[사용자에게 결과 전달]
└─ 보고서 출력
```

[사용자 (스마트 글래스)] -> [Java 인증 서버 (토큰 발급)] -> [AI Processing Server (FastAPI)]

[AI Processing Server 내부 파이프라인]
1. 데이터 수집: 음성, 이미지 (스마트 글래스) / 시계열, 로그 (설비 장비)
2. 전처리: STT (음성->텍스트), Vision LLM (이미지 분석), 시계열 정규화 및 특징 추출
3. Predictive AI: 시계열/로그 기반 고장 확률 및 잔여수명(RUL) 예측 (LGBM/XGB/TCN)
4. LLM 구조화: 사용자 발화, 이미지 분석 결과, 예측 결과를 종합하여 JSON 형태로 구조화
5. RAG 검색: 구조화된 데이터를 바탕으로 Vector DB에서 매뉴얼, 유사 사례, 조치 방법 검색
6. 최종 응답 생성: Qwen LLM을 사용하여 최종 조치 절차, 근거, 리스크, 에스컬레이션 조건 생성
7. 응답 반환: JSON 형태로 스마트 글래스에 전달 (TTS 출력 및 화면 표시)

## 3. 현재 루트 디렉토리 환경 (템플릿 폴더)
현재 프로젝트 루트 디렉토리에는 위 아키텍처 구현에 필요한 각 기술 요소들의 코드 템플릿이 폴더별로 나뉘어 있습니다. (예: `rag`, `langchain`, `langgraph`, `lstm_model_serving`, `stt_tts`, `fastapi`, `java`, `vue_js` 등)

## 4. 요청 사항 (출력 포맷)
위 시스템 흐름과 현재 보유한 템플릿 폴더들을 참고하여 다음 항목들을 상세히 작성해 주세요.

1. **전체 프로젝트 디렉토리 구조도 (Directory Tree):** - 기존 템플릿들을 어떤 구조로 병합하고 재배치해야 유지보수성과 확장성이 좋을지 표준적인 트리 구조로 시각화해 주세요.
2. **주요 폴더 및 모듈별 역할 설명:**
   - 설계한 구조 내에서 각 폴더가 파이프라인의 어느 단계를 담당하는지 설명해 주세요.
3. **템플릿 통합 가이드 (Integration Plan):**
   - 현재 분리되어 있는 `fastapi`, `langchain/langgraph`, `rag`, `lstm_model_serving` 등의 템플릿 코드를 하나의 AI Processing Server로 어떻게 연결하고 통합해야 하는지 아키텍처 관점에서의 조언을 제공해 주세요.
4. **API 엔드포인트 설계 초안:**
   - 스마트 글래스 및 설비 장비와 통신하기 위한 FastAPI와 Java 인증 서버의 핵심 API 인터페이스(엔드포인트, Request/Response 구조) 초안을 작성해 주세요.