from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Glass AI System"
    API_V1_STR: str = "/api/v1"
    
    # AI Model Keys (Set via .env or OS environment)
    OPENAI_API_KEY: Optional[str] = None
    QWEN_MODEL_PATH: str = "qwen/Qwen-VL-Chat"
    
    # Database Settings
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    VECTOR_DB_PATH: str = "infrastructure/vector-db/faiss_index"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
