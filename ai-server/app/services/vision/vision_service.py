"""
이미지 분석 및 Vision LLM 기반 처리

- Base64 인코딩
- MultiModal LLM (GPT-4V) 또는 Vision LLM (Qwen-VL)을 통한 분석
- 이미지 기반 장비 상태 분석
"""

import base64
import os
import io
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv() # .env 파일에서 환경변수 로드

try:
    from PIL import Image
except ImportError:
    Image = None

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# ============================================
# 전역 설정
# ============================================

_vision_llm = None

def get_vision_llm():
    """
    Vision LLM 모델 동적 로드 (GPT-4V)
    
    환경 변수 OPENAI_API_KEY 필수
    """
    global _vision_llm
    if _vision_llm is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")
        
        _vision_llm = ChatOpenAI(
            model="gpt-4o", # 현재 gpt-4o를 사용 중입니다 (노트북과 동일)
            max_tokens=1024,
            temperature=0.7
        )
    return _vision_llm


# ============================================
# 이미지 처리 함수
# ============================================

def encode_image_to_base64(file_content: bytes) -> str:
    """
    바이너리 이미지를 Base64로 인코딩합니다.
    
    Args:
        file_content: 이미지 바이너리 데이터
        
    Returns:
        Base64 인코딩된 문자열
    """
    return base64.b64encode(file_content).decode('utf-8')


def encode_image_from_path(image_path: str) -> str:
    """
    파일 경로의 이미지를 Base64로 인코딩합니다.
    
    Args:
        image_path: 이미지 파일 경로
        
    Returns:
        Base64 인코딩된 문자열
        
    Raises:
        FileNotFoundError: 파일이 없을 경우
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_image_media_type(filename: str) -> str:
    """
    파일 확장자로부터 MIME 타입을 결정합니다.
    
    Args:
        filename: 파일 이름
        
    Returns:
        MIME 타입 (예: "image/jpeg")
    """
    ext = filename.lower().split('.')[-1]
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }
    return media_types.get(ext, 'image/jpeg')


# ============================================
# Vision LLM 분석 함수
# ============================================

def analyze_equipment_image(
    image_base64: str,
    filename: str,
    analysis_type: str = "general"
) -> str:
    """
    Vision LLM을 사용하여 장비 이미지를 분석합니다.
    
    Args:
        image_base64: Base64 인코딩된 이미지
        filename: 원본 파일 이름
        analysis_type: 분석 유형
            - "general": 일반적 상태 분석
            - "damage": 손상 및 결함 감지
            - "maintenance": 유지보수 필요사항 판단
            
    Returns:
        분석 결과 텍스트
    """
    media_type = get_image_media_type(filename)
    
    llm = get_vision_llm()
    
    # 분석 프롬프트 선택
    if analysis_type == "damage":
        prompt = """이 설비/장비 사진을 분석하고 다음을 평가하세요:
        
1. 눈에 띄는 손상, 누유, 균열 또는 부식 징후
2. 비정상적인 색상 변화 (과열, 산화 등)
3. 연결부, 씰, 조인트의 상태
4. 즉각적인 조치가 필요한 위험 요소

분석 결과를 명확하고 구조화된 형식으로 제시하세요."""
    
    elif analysis_type == "maintenance":
        prompt = """이 설비/장비의 유지보수 상태를 평가하세요:
        
1. 정상적인 작동 상태 여부
2. 예방 유지보수 필요 부분
3. 청소 또는 윤활이 필요한 부분
4. 부품 교체 시기 평가
5. 다음 검사 예정 시간

권장 조치를 우선순위 별로 정리하세요."""
    
    else:  # "general"
        prompt = """이 설비/장비의 현재 상태를 종합적으로 분석하세요:
        
1. 외형적 상태 (청결도, 손상 등)
2. 작동 상태 지표 (색상, 소음 징후 등)
3. 안전 우려사항
4. 필요한 조치 (있을 경우)

분석을 간결하고 전문적으로 작성하세요."""
    
    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{image_base64}",
                },
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    )
    
    response = llm.invoke([message])
    return response.content


def extract_image_contents(
    image_base64: str,
    filename: str,
    language: str = "korean"
) -> Dict[str, Any]:
    """
    이미지에서 텍스트 및 주요 구성 요소를 추출합니다.
    
    Args:
        image_base64: Base64 인코딩된 이미지
        filename: 원본 파일 이름
        language: 응답 언어 ("korean", "english")
        
    Returns:
        추출된 정보의 딕셔너리
    """
    media_type = get_image_media_type(filename)
    
    llm = get_vision_llm()
    
    lang_text = "한국어로" if language == "korean" else "English로"
    
    prompt = f"""이 이미지를 분석하고 다음을 {lang_text} 제공하세요:

1. 이미지에 보이는 주요 객체/장비 목록
2. 각 객체의 상태 또는 조건
3. 감지된 텍스트 또는 라벨
4. 주요 관찰사항 또는 이상 징후

JSON 형식으로 구조화된 응답을 제공하세요."""
    
    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{image_base64}",
                },
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    )
    
    response = llm.invoke([message])
    
    return {
        "raw_analysis": response.content,
        "filename": filename,
        "media_type": media_type,
    }


def process_image_upload(
    file_content: bytes,
    filename: str,
    analysis_type: str = "general"
) -> Dict[str, Any]:
    """
    업로드된 이미지를 처리하고 Vision LLM으로 분석합니다.
    
    Args:
        file_content: 이미지 바이너리 데이터
        filename: 파일 이름
        analysis_type: 분석 유형
        
    Returns:
        분석 결과 딕셔너리
        
    Raises:
        ValueError: 지원하지 않는 이미지 포맷
    """
    # 유효성 검사
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    ext = '.' + filename.split('.')[-1].lower()
    if ext not in valid_extensions:
        raise ValueError(f"Unsupported image format: {ext}")
    
    # Base64 인코딩
    image_base64 = encode_image_to_base64(file_content)
    
    # Vision 분석
    analysis = analyze_equipment_image(
        image_base64,
        filename,
        analysis_type
    )
    
    return {
        "filename": filename,
        "analysis": analysis,
        "analysis_type": analysis_type,
        "base64_preview": image_base64[:100] + "..." if len(image_base64) > 100 else image_base64,
    }


def compare_images(
    image1_base64: str,
    filename1: str,
    image2_base64: str,
    filename2: str,
    context: str = ""
) -> str:
    """
    두 이미지를 비교 분석합니다.
    
    Args:
        image1_base64: 첫 번째 Base64 이미지
        filename1: 첫 번째 파일 이름
        image2_base64: 두 번째 Base64 이미지
        filename2: 두 번째 파일 이름
        context: 비교 컨텍스트 (예: "과거 vs 현재", "정상 vs 비정상")
        
    Returns:
        비교 분석 결과
    """
    media_type1 = get_image_media_type(filename1)
    media_type2 = get_image_media_type(filename2)
    
    llm = get_vision_llm()
    
    context_text = f"컨텍스트: {context}" if context else ""
    
    prompt = f"""다음 두 이미지를 비교 분석하세요:
    
{context_text}

비교 분석:
1. 주요 차이점
2. 상태 변화 (개선/악화)
3. 원인 추정
4. 권장 조치 또는 후續 모니터링

분석을 명확하게 구조화하여 작성하세요."""
    
    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type1};base64,{image1_base64}",
                },
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type2};base64,{image2_base64}",
                },
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    )
    
    response = llm.invoke([message])
    return response.content
