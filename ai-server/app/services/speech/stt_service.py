"""
음성 파일을 텍스트로 변환하는 STT(Speech-to-Text) 서비스

- webm → wav 변환 (ffmpeg)
- Whisper 기반 음성 인식 (CPU 최적화)
"""

import os
import subprocess
import tempfile
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

# ============================================
# 전역 설정
# ============================================

DEVICE = "cpu"
MODEL_NAME = os.getenv("WHISPER_MODEL", "base")

# 모델을 동적으로 로드 (Lazy Loading)
_model = None

def get_model():
    """Whisper 모델 동적 로드"""
    global _model
    if _model is None:
        if WhisperModel is None:
            raise RuntimeError("faster_whisper not installed")
        _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type="int8")
    return _model


# ============================================
# 변환 및 STT 함수
# ============================================

def convert_webm_to_wav(webm_path: str, wav_path: str) -> None:
    """
    webm 파일을 wav 파일로 변환합니다.
    
    ffmpeg를 직접 호출하여 변환합니다.
    STT 안정성을 위해 모노 채널 + 16kHz로 맞춰줍니다.
    
    Args:
        webm_path: 입력 webm 파일 경로
        wav_path: 출력 wav 파일 경로
        
    Raises:
        FileNotFoundError: 입력 파일이 없을 경우
        RuntimeError: ffmpeg 변환 실패
    """
    if not os.path.exists(webm_path):
        raise FileNotFoundError(f"Input not found: {webm_path}")

    out_dir = os.path.dirname(wav_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",        # overwrite
        "-i", webm_path,
        "-ac", "1",  # mono
        "-ar", "16000",  # 16kHz
        "-vn",  # no video
        wav_path,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg convert failed: {proc.stderr.strip()}")


def convert_mp3_to_wav(mp3_path: str, wav_path: str) -> None:
    """
    mp3 파일을 wav 파일로 변환합니다.
    
    Args:
        mp3_path: 입력 mp3 파일 경로
        wav_path: 출력 wav 파일 경로
    """
    if not os.path.exists(mp3_path):
        raise FileNotFoundError(f"Input not found: {mp3_path}")

    out_dir = os.path.dirname(wav_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", mp3_path,
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        wav_path,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg convert failed: {proc.stderr.strip()}")


def transcribe_audio_file(file_path: str) -> str:
    """
    로컬 Whisper 모델로 STT를 수행합니다.
    
    faster-whisper 라이브러리를 사용하여:
    - 빔 서치 (beam_size=5)
    - 음성 활동 감지 (VAD)를 통한 자동 무음 제거
    
    Args:
        file_path: 오디오 파일 경로 (.wav, .mp3 등)
        
    Returns:
        변환된 텍스트
        
    Raises:
        FileNotFoundError: 파일이 없을 경우
        RuntimeError: Whisper 모델 로드 실패
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input not found: {file_path}")

    model = get_model()

    # faster-whisper은 segments generator를 반환
    segments, info = model.transcribe(
        file_path,
        beam_size=5,
        language="ko", # 한국어 강제 (노이즈로 인한 중국어/외국어 할루시네이션 방지)
        vad_filter=True,  # 무음 자동 제거
    )

    text = "".join(seg.text for seg in segments).strip()
    return text


def process_audio_upload(file_content: bytes, filename: str) -> str:
    """
    업로드된 음성 파일을 처리하고 텍스트로 변환합니다.
    
    내부 임시 파일을 생성하여 처리 후 자동 정리합니다.
    
    Args:
        file_content: 파일 바이너리 내용
        filename: 파일 이름 (확장자 포함)
        
    Returns:
        변환된 텍스트
        
    Raises:
        RuntimeError: 오디오 처리 실패
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 입력 파일 저장
        input_path = os.path.join(tmpdir, filename)
        with open(input_path, "wb") as f:
            f.write(file_content)

        # 필요시 wav로 변환
        audio_path = input_path
        if filename.endswith(".webm"):
            wav_path = os.path.join(tmpdir, filename.replace(".webm", ".wav"))
            convert_webm_to_wav(input_path, wav_path)
            audio_path = wav_path
        elif filename.endswith(".mp3"):
            wav_path = os.path.join(tmpdir, filename.replace(".mp3", ".wav"))
            convert_mp3_to_wav(input_path, wav_path)
            audio_path = wav_path

        # STT 수행
        text = transcribe_audio_file(audio_path)
        return text


