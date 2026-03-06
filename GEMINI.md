# 프로젝트 아키텍처 및 API 명세서 (최신)

## 1. 역할 및 목표
스마트 글래스(Vue.js 프론트엔드) 기반의 기계/설비 상태 진단, RUL 예측, 그리고 RAG 기반 조치 가이드를 제공하는 통합 AI 시스템.

## 2. 상세 API 엔드포인트 명세

### A. Incident 수집/조회
- `POST /api/v1/incidents`: 사건 생성
- `POST /api/v1/incidents/{incident_id}/assets`: 이미지/음성 업로드
- `POST /api/v1/incidents/{incident_id}/telemetry`: 센서/로그 업로드
- `GET /api/v1/incidents/{incident_id}`: 사건 상세 조회
- `GET /api/v1/incidents`: 사건 목록/필터

### B. Knowledge Ingestion (RAG 지식 구축)
- `POST /api/v1/kb/ingest`: 문서 업로드 및 인덱싱
- `GET /api/v1/kb/status`: 인덱싱 상태 확인

### C. RAG 질의/결과
- `POST /api/v1/rag/query`: 사건 기반 RAG 실행
- `GET /api/v1/rag/outputs/{incident_id}`: 생성 결과 조회

### D. Predictive AI (예측/피드백)
- `POST /api/v1/predict`: 예측 수행 (RUL, 고장 확률)
- `POST /api/v1/feedback`: 실제값 입력 및 모델 성능(RMSE) 갱신

### E. AIOps (재학습/모델/메트릭)
- `POST /api/v1/retrain`: 재학습 Job 생성
- `GET /api/v1/models`: 모델 목록 및 상태 확인
- `GET /api/v1/metrics`: 성능 추이 조회
- `GET /api/v1/drift`: 데이터 드리프트 이벤트 조회

### F. 보고서 생성
- `POST /api/v1/report/quality`: 품질팀 보고서 생성 (PDF/JSON)
- `POST /api/v1/report/aiops`: 모델 운영 보고서 생성

## 3. 데모 시나리오 (핵심 검증 케이스)
1. **MAF Sensor 오류**: DTC P0101 기반 공기 유량 센서 진단 및 청소/점검 가이드.
2. **ECU 과열 문제**: DTC P0606 기반 온도 상승 추이 분석 및 냉각 시스템 점검.
3. **점화 시스템 이상**: DTC P0302 기반 2번 실린더 미스파이어 진단 및 코일/플러그 교체 가이드.

## 4. 디렉토리 구조
- `ai-server/app/api/v1/endpoints/`: incidents, kb, rag, predictive, aiops, reporting 라우터 위치.
- `ai-server/app/services/`: 각 단계별 AI 로직 구현.
