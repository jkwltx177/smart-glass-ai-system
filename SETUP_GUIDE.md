# Smart Glass AI System - 멀티모달 처리 업데이트 가이드

## 📋 개요

FastAPI 기반 AI Server가 다음과 같이 업그레이드되었습니다:

### 추가된 기능

1. **STT (Speech-to-Text) 처리**
   - 파일 포맷: `.webm`, `.mp3`, `.wav`
   - 엔진: `faster-whisper` (CPU 최적화)
   - 자동 포맷 변환: webm/mp3 → wav (ffmpeg 사용)

2. **Vision LLM 기반 이미지 분석**
   - 파일 포맷: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
   - 엔진: GPT-4V (LangChain)
   - 분석 유형:
     - `general`: 일반적 상태 분석
     - `damage`: 손상/결함 감지
     - `maintenance`: 유지보수 필요사항

3. **멀티모달 통합 분석**
   - 음성 + 이미지 동시 처리
   - 통합 분석 결과 생성

---

## 🔧 설치 및 실행

### 1단계: 시스템 패키지 설치

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Fedora/RHEL
sudo dnf install ffmpeg
```

### 2단계: Python 패키지 설치

```bash
cd ai-server
pip install -r requirements.txt
```

### 3단계: 환경 변수 설정

`.env` 파일을 `ai-server/` 루트에 생성하세요:

```env
# OpenAI API (Vision LLM용)
OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE

# MariaDB 접속 정보
DB_HOST=127.0.0.1
DB_PORT=3380
DB_NAME=smart_glass_dev
DB_USER=sg_app
DB_PASSWORD=sg_app_1

# Whisper 모델 크기 (선택사항)
# 옵션: tiny, base, small, medium, large
# 기본값: base
WHISPER_MODEL=base

# 예측 모델 가중치 경로 (LGBM/XGB/TCN)
PREDICTION_MODEL_DIR=models/weights

# 추가 설정
DEBUG=False
LOG_LEVEL=INFO
```

### 4단계: 서버 실행

```bash
# 개발 서버 (재로드 활성화)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션 서버
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📡 API 엔드포인트

### A. 사건 생성

**POST /api/v1/incidents**

```bash
curl -X POST "http://localhost:8000/api/v1/incidents" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "Plant A",
    "line": "Line 1",
    "device_type": "Pump",
    "equipment_id": "EQ-2024-X1",
    "description": "비정상 진동 감지"
  }'
```

**응답:**
```json
{
  "incident_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created",
  "created_at": "2024-03-06T12:30:45.123Z"
}
```

---

### B. 음성 파일 업로드 및 STT 처리

**POST /api/v1/incidents/{incident_id}/audio**

```bash
curl -X POST "http://localhost:8000/api/v1/incidents/550e8400-e29b-41d4-a716-446655440000/audio" \
  -F "audio_file=@recording.webm" \
  -F "analysis_context=현장 진동 소음 기록"
```

**응답:**
```json
{
  "transcription": "펌프에서 이상한 소음이 발생하고 진동이 심함",
  "confidence": 0.95,
  "duration_ms": 15230,
  "language": "ko"
}
```

**지원 포맷:**
- `.webm` (스마트 글래스 기본 포맷)
- `.mp3`
- `.wav`
- `.m4a`
- `.ogg`

---

### C. 이미지 업로드 및 Vision 분석

**POST /api/v1/incidents/{incident_id}/image**

```bash
curl -X POST "http://localhost:8000/api/v1/incidents/550e8400-e29b-41d4-a716-446655440000/image" \
  -F "image_file=@equipment.jpg" \
  -F "analysis_type=damage"
```

**분석 유형:**
- `general`: 일반 상태 분석
- `damage`: 손상/누유/균열 감지
- `maintenance`: 유지보수 필요사항

**응답:**
```json
{
  "analysis": "펌프 배관 연결부위에 미세 누유 확인. 씰 상태 양호하나 조인트 주변에 산화 흔적 발견...",
  "analysis_type": "damage",
  "filename": "equipment.jpg",
  "media_type": "image/jpeg",
  "timestamp": "2024-03-06T12:31:00.123Z"
}
```

**지원 포맷:**
- `.jpg`, `.jpeg`
- `.png`
- `.gif`
- `.webp`

---

### D. 멀티모달 통합 분석 (음성 + 이미지)

**POST /api/v1/incidents/{incident_id}/analyze**

```bash
curl -X POST "http://localhost:8000/api/v1/incidents/550e8400-e29b-41d4-a716-446655440000/analyze" \
  -F "audio_file=@recording.webm" \
  -F "image_file=@equipment.jpg" \
  -F "analysis_type=damage" \
  -F "analysis_context=정기 점검"
```

**응답:**
```json
{
  "incident_id": "550e8400-e29b-41d4-a716-446655440000",
  "transcription": "펌프에서 이상한 소음이 발생하고 진동이 심함",
  "vision_analysis": "펌프 배관 연결부위에 미세 누유 확인.",
  "integrated_summary": "장비 분석 보고서 (Pump / EQ-2024-X1)\n==================================================\n\n[현장 보고]\n펌프에서 이상한 소음이 발생하고 진동이 심함\n\n[이미지 분석]\n펌프 배관 연결부위에 미세 누유 확인...\n\n[추가 정보]\n정기 점검\n\n==================================================\n분석 완료",
  "timestamp": "2024-03-06T12:32:00.123Z",
  "assets": {
    "audio": "recording.webm",
    "image": "equipment.jpg"
  }
}
```

---

### E. 사건 상세 조회

**GET /api/v1/incidents/{incident_id}**

```bash
curl -X GET "http://localhost:8000/api/v1/incidents/550e8400-e29b-41d4-a716-446655440000"
```

---

### F. 사건 목록 조회

**GET /api/v1/incidents**

```bash
# 모든 사건 조회
curl -X GET "http://localhost:8000/api/v1/incidents"

# 특정 사이트 필터링
curl -X GET "http://localhost:8000/api/v1/incidents?site=Plant%20A&limit=20"
```

---

## 🗂️ 디렉토리 구조

```
ai-server/
├── app/
│   ├── main.py                          # FastAPI 앱 진입점
│   ├── __init__.py
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── incidents.py         # ✨ 음성/이미지 처리 업데이트됨
│   │           ├── kb.py
│   │           ├── rag.py
│   │           ├── predictive.py
│   │           ├── aiops.py
│   │           └── reporting.py
│   ├── core/
│   │   └── config.py
│   ├── models/
│   ├── schemas/
│   │   └── api_models.py                # ✨ STT/Vision 스키마 추가됨
│   ├── services/
│   │   ├── speech/                      # 🆕 STT 서비스
│   │   │   ├── __init__.py
│   │   │   └── stt_service.py
│   │   ├── vision/                      # 🆕 Vision LLM 서비스
│   │   │   ├── __init__.py
│   │   │   └── vision_service.py
│   │   ├── pipeline/
│   │   ├── prediction/
│   │   ├── rag/
│   │   └── auth/
│   ├── utils/
│   └── __init__.py
├── requirements.txt                     # ✨ faster-whisper, langchain-openai 추가됨
└── README.md
```

---

## 🔌 요구 사항

### 필수 환경 변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 (Vision LLM용) | `sk-proj-...` |
| `WHISPER_MODEL` | Whisper 모델 크기 (선택) | `base`, `small` |

### 시스템 요구사항

- **Python**: 3.9+
- **OS**: macOS, Linux, Windows
- **ffmpeg**: 오디오 변환용 (시스템 패키지)
- **메모리**: STT/Vision 처리 시 최소 4GB RAM

### 성능 특성

| 작업 | 처리 시간 | 주의사항 |
|------|---------|--------|
| STT (1분 음성) | ~5-10초 | CPU 사용, webm→wav 변환 포함 |
| Vision 분석 | ~3-5초 | OpenAI API 호출 비용 |
| 멀티모달 분석 | ~10-15초 | 병렬 처리 아님 |

---

## 🧪 테스트 예제

### Python을 이용한 통합 테스트

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# 1. 사건 생성
incident_resp = requests.post(
    f"{BASE_URL}/api/v1/incidents",
    json={
        "site": "Plant A",
        "line": "Line 1",
        "device_type": "Pump",
        "equipment_id": "EQ-2024-X1",
    }
)
incident_id = incident_resp.json()["incident_id"]
print(f"Created incident: {incident_id}")

# 2. 음성 파일 업로드
with open("recording.webm", "rb") as f:
    audio_resp = requests.post(
        f"{BASE_URL}/api/v1/incidents/{incident_id}/audio",
        files={"audio_file": f},
        data={"analysis_context": "현장 진단"}
    )
print(f"STT Result: {audio_resp.json()['transcription']}")

# 3. 이미지 파일 업로드
with open("equipment.jpg", "rb") as f:
    image_resp = requests.post(
        f"{BASE_URL}/api/v1/incidents/{incident_id}/image",
        files={"image_file": f},
        data={"analysis_type": "damage"}
    )
print(f"Vision Analysis: {image_resp.json()['analysis']}")

# 4. 통합 분석
with open("recording.webm", "rb") as audio, \
     open("equipment.jpg", "rb") as image:
    multi_resp = requests.post(
        f"{BASE_URL}/api/v1/incidents/{incident_id}/analyze",
        files={
            "audio_file": audio,
            "image_file": image,
        },
        data={"analysis_type": "damage"}
    )
print(f"Integrated Summary:\n{multi_resp.json()['integrated_summary']}")
```

---

## 🐛 문제 해결

### 1. `ModuleNotFoundError: No module named 'faster_whisper'`

```bash
pip install -r requirements.txt
```

### 2. `ffmpeg not found`

```bash
# macOS
brew install ffmpeg

# Linux
sudo apt-get install ffmpeg
```

### 3. `OPENAI_API_KEY not set in environment`

`.env` 파일에 API 키를 추가하세요:

```env
OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
```

### 4. 음성 처리 느림

- Whisper 모델 크기를 줄입니다: `WHISPER_MODEL=tiny`
- GPU가 있으면 활성화 (현재 CPU 강제)

---

## 📚 참고 자료

- [LangChain Vision](https://python.langchain.com/docs/modules/model_io/models/llm/integrations/openai_vision)
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
- [FastAPI File Upload](https://fastapi.tiangolo.com/tutorial/request-files/)

---

## 📝 업데이트 이력

### v2.1.0 (2024-03-06)
- ✨ STT 서비스 추가 (faster-whisper)
- ✨ Vision LLM 서비스 추가 (GPT-4V)
- ✨ 멀티모달 분석 엔드포인트 추가
- 📝 API 문서 업데이트
