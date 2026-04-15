from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Curiosity Meter - FastAPI MVP"
    API_V1_STR: str = "/api"
    
    # Database URIs
    POSTGRES_DB_URL: str = "postgresql://user:password@localhost:5432/curiosity_meter"
    REDIS_URL: str = "redis://localhost:6379"
    QDRANT_URL: str = "http://localhost:6333"
    
    # API Keys
    GEMINI_API_KEY: str = ""
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
