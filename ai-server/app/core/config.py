from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Glass AI System"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "2.0.0"
    
    # AI Model Keys
    OPENAI_API_KEY: Optional[str] = None
    QWEN_MODEL_PATH: str = "qwen/Qwen-VL-Chat"
    
    # Database & Storage
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    VECTOR_DB_PATH: str = "infrastructure/vector-db/faiss_index"
    REPORT_OUTPUT_DIR: str = "storage/reports"
    ASSET_UPLOAD_DIR: str = "storage/assets"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
