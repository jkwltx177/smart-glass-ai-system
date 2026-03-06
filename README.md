# 스마트 글래스 기반 기계/설비 상태 진단 및 RUL 예측 AI 시스템

## 1. 전체 프로젝트 디렉토리 구조도 (Directory Tree)

기존 파편화된 템플릿들을 마이크로서비스 관점(인증, AI, 프론트엔드)으로 분리하되, 개발 및 배포 편의성을 위해 하나의 레포지토리 내에 병합하는 구조입니다.

```text
smart-glass-ai-system/
├── auth-server/             # Java 인증 서버 (Spring Boot / JWT 발급)
│   └── (stt_tts_server_fastapi_java/workplace 템플릿 코드 이동)
├── ai-server/               # AI Processing Server (FastAPI 기반)
│   ├── app/
│   │   ├── api/             # API 라우터 (엔드포인트 설정)
│   │   │   └── v1/
│   │   │       └── endpoints/
│   │   ├── core/            # 공통 설정 (DB, Security, Logging 등)
│   │   ├── models/          # SQLAlchemy 데이터베이스 모델 정의
│   │   ├── schemas/         # Pydantic 기반 Request/Response DTO
│   │   ├── services/        # 핵심 비즈니스 로직 및 파이프라인
│   │   │   ├── auth/        # Auth Server 토큰 검증 로직
│   │   │   ├── pipeline/    # LangGraph 오케스트레이션 (전체 흐름 제어)
│   │   │   ├── prediction/  # 고장 확률/RUL 예측 (LGBM/TCN/LSTM)
│   │   │   ├── rag/         # VectorDB 매뉴얼/유사 사례 검색
│   │   │   ├── speech/      # 스마트 글래스 음성 STT 변환
│   │   │   └── vision/      # 이미지 전처리 및 Vision LLM
│   │   ├── utils/           # 유틸리티 함수
│   │   └── main.py          # FastAPI 애플리케이션 진입점
│   └── requirements.txt     # 통합된 Python 패키지 의존성
├── frontend/                # 관리자 대시보드 및 모니터링 (Vue.js)
│   └── (vuejs 템플릿 코드 이동)
└── infrastructure/          # 공통 인프라 설정 (Docker, DB 볼륨 등)
    ├── docker-compose.yml   # MSA 통합 실행 스크립트
    └── vector-db/           # VectorDB (FAISS/Milvus) 데이터 저장소
```

## 2. 주요 폴더 및 모듈별 역할 설명

| 폴더/모듈 | 담당 파이프라인 단계 및 역할 |
|---|---|
| `auth-server/` | **사용자 인증**: 스마트 글래스 사용자의 로그인 처리 및 보안 토큰(JWT) 발급. |
| `ai-server/.../speech` | **데이터 수집 & 전처리 (음성)**: 수신된 오디오 스트림을 텍스트로 변환(STT). |
| `ai-server/.../vision` | **데이터 수집 & 전처리 (이미지)**: 현장 이미지를 Vision LLM(Qwen-VL 등)을 이용해 텍스트 분석 결과로 변환. |
| `ai-server/.../prediction` | **Predictive AI**: 설비 시계열/로그 데이터를 정규화하고 학습된 모델(LGBM/XGB/TCN)을 통해 RUL 및 고장 확률 도출. |
| `ai-server/.../rag` | **RAG 검색**: 구조화된 데이터를 쿼리로 변환해 Vector DB(FAISS 등)에서 매뉴얼, 과거 고장 사례, 조치법 등을 검색. |
| `ai-server/.../pipeline` | **LLM 구조화 및 최종 응답 생성**: LangGraph를 통해 STT/Vision/Prediction/RAG 결과를 종합하고 Qwen LLM으로 최종 조치 절차 및 에스컬레이션 조건 생성 (전체 오케스트레이션). |
| `frontend/` | (선택적) 관리자 및 중앙 관제 센터에서 현재 설비 상태 및 진단 내역을 모니터링하는 대시보드 웹. |

## 3. 템플릿 통합 가이드 (Integration Plan)

루트 디렉토리에 있는 기존 템플릿들을 새 구조(`smart-glass-ai-system`)로 마이그레이션하기 위한 아키텍처 관점의 통합 전략입니다.

1. **인증 서버 (Java)**
   - `stt_tts_server_fastapi_java/workplace` 내부의 Gradle/Spring 코드를 `auth-server/`로 전체 이동합니다.
   - 역할은 토큰(JWT) 발급으로 한정하고, FastAPI(AI Server)에서는 해당 토큰의 유효성만 검증(Public Key 또는 검증 API 호출)하는 구조로 결합도를 낮춥니다.
2. **AI Processing Server (FastAPI 통합)**
   - **엔트리포인트**: 기존 템플릿들(`db_vectordb_llm/rag_app/main.py` 등)의 코드를 참고하여 `ai-server/app/main.py`를 단일 진입점으로 구성합니다.
   - **RAG & VectorDB**: `db_vectordb_llm` 및 `pdf_vectordb_llm` 폴더 내 문서 전처리 및 FAISS 코드를 `ai-server/app/services/rag`로 이식합니다.
   - **예측 모델**: `lstm_model_serving`의 추론 로직(Inference)을 `ai-server/app/services/prediction`으로 이동하고, 모델 가중치(`*.h5`, `*.pt` 등)는 별도의 `/models/weights` 폴더를 두어 로드하도록 구성합니다.
   - **LangGraph 오케스트레이션**: `LangChain_LangGraph`와 `trendpilot/agents`의 코드를 바탕으로 `ai-server/app/services/pipeline` 내에 상태 기반 워크플로우(State Graph)를 작성합니다. 음성, 이미지, 시계열 데이터를 각각의 Node에서 병렬 처리한 후 RAG Node, LLM Generation Node로 이어지도록 구성해야 응답 속도를 최적화할 수 있습니다.
3. **프론트엔드 (Vue.js)**
   - `vuejs` 폴더의 전체 내용을 `frontend/`로 이동합니다. Vite/Vue 설정은 그대로 유지하되 `vite.config.js` 프록시를 통해 AI Server 및 Auth Server와 통신하도록 `.env`를 셋팅합니다.

## 4. API 엔드포인트 설계 초안

스마트 글래스 및 설비 장비 통신을 위한 핵심 REST API 구조입니다.

### [Java 인증 서버 (`auth-server`)]
- **`POST /api/v1/auth/login`**
  - **Req**: `{"username": "glass_operator_1", "password": "..."}`
  - **Res**: `{"access_token": "eyJhb...", "token_type": "Bearer", "expires_in": 3600}`

### [FastAPI AI 서버 (`ai-server`)]
- **`POST /api/v1/analyze/diagnostic`** (스마트 글래스 호출용 메인 API)
  - **Description**: 스마트 글래스에서 수집된 음성, 이미지 및 타겟 장비 ID를 한 번에 전송받아 전체 파이프라인(STT->Vision->RAG->LLM)을 병렬/순차 실행합니다.
  - **Req (Multipart/form-data)**:
    - `audio_file`: 현장 음성 파일 (바이너리)
    - `image_file`: 현장 촬영 파일 (바이너리)
    - `equipment_id`: "EQ-2024-X1" (설비 식별자)
    - `timestamp`: "2024-10-25T14:30:00Z"
  - **Res (JSON)**:
    ```json
    {
      "status": "success",
      "data": {
        "transcription": "펌프에서 이상한 소음이 발생하고 진동이 심함",
        "vision_analysis": "펌프 배관 연결부위 미세 누유 확인",
        "predicted_rul_days": 12.5,
        "failure_probability": 0.85,
        "final_action_plan": {
          "steps": [
            "1. 즉시 펌프 가동 중지",
            "2. 연결부위 누유 차단 밸브 잠금",
            "3. 매뉴얼 [PUMP-M-01]에 따라 조인트 씰 교체"
          ],
          "risk_level": "HIGH",
          "escalation_required": true
        }
      }
    }
    ```

- **`POST /api/v1/equipment/{equipment_id}/telemetry`** (설비 장비 호출용)
  - **Description**: 설비 장비가 주기적으로 센서(시계열) 데이터 및 로그를 전송하여 고장 확률/RUL 예측 AI 모델 업데이트 및 캐싱에 쓰이는 엔드포인트입니다.
  - **Req (JSON)**: `{"temperature": 85.2, "vibration": 1.2, "pressure": 120, "timestamp": "..."}`
  - **Res**: `{"status": "ok", "recorded": true}`

## 5. 로컬 DB 실행 및 MySQL Workbench 접속

현재 프로젝트는 단일 `docker-compose.yml`에서 전용 MariaDB 컨테이너 `smart-glass-project-db`(호스트 포트 `3380`)를 함께 실행합니다.

1. 전용 DB 컨테이너 실행
   ```bash
   cd /Users/bangdawon_skala/workspace/skala-intro/GenerativeAIservice/smart-glass-ai-system
   docker compose -f docker-compose.yml up -d project-db
   docker compose -f docker-compose.yml ps
   ```
   `smart-glass-project-db`가 `0.0.0.0:3380->3306/tcp`로 보이면 정상입니다.

2. MySQL Workbench 접속 정보
   - Hostname: `127.0.0.1` (또는 `localhost`)
   - Port: `3380`
   - Username (개발): `root`
   - Password (개발): `mysql_1`
   - Username (서비스): `sg_app`
   - Password (서비스): `sg_app_1`

3. DB 확인
   ```sql
   SHOW DATABASES;
   USE smart_glass_dev;
   SELECT DATABASE();
   ```

4. 앱 실행 (개발 계정 root)
   ```bash
   docker compose --env-file .env -f docker-compose.yml up -d app
   ```

5. 서비스 계정으로 앱 실행
   ```bash
   docker compose --env-file .env.service -f docker-compose.yml up -d app
   ```
