"""
Speech Processing Services

- STT (Speech-to-Text): faster-whisper 기반
- 멀티포맷 오디오 지원: webm, mp3, wav
"""

from .stt_service import (
    transcribe_audio_file,
    process_audio_upload,
    convert_webm_to_wav,
    convert_mp3_to_wav,
)

__all__ = [
    "transcribe_audio_file",
    "process_audio_upload",
    "convert_webm_to_wav",
    "convert_mp3_to_wav",
]
