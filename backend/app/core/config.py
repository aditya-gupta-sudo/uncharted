from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Car Manual Explorer API"
    ORIGINS: str = Field("http://localhost:3000", env="ORIGINS")
    
    # Application configuration - Hardcoded for car manuals
    INDUSTRY: str = "automotive"
    APP_NAME: str = "Car Manual Explorer"
    APP_DESCRIPTION: str = "AI-powered car manual search and exploration system"
    
    # MongoDB configuration
    MONGODB_URI: str = Field(..., env="MONGODB_URI")
    DATABASE_NAME: str = Field(..., env="DATABASE_NAME")
    MONGODB_DB: Optional[str] = Field(None, env="DATABASE_NAME")  # Optional alias for DATABASE_NAME
    CHUNKS_COLLECTION: str = Field("manuals", env="CHUNKS_COLLECTION")  # Unified collection for text chunks and images
    
    # GCP Vertex AI configuration
    GCP_PROJECT_ID: str = Field(..., env="GCP_PROJECT_ID")
    GCP_LOCATION: str = Field("us-central1", env="GCP_LOCATION")
    GCP_CHAT_LOCATION: str = Field("global", env="GCP_CHAT_LOCATION")
    DOCUMENT_AI_PROCESSOR_NAME: Optional[str] = Field(None, env="DOCUMENT_AI_PROCESSOR_NAME")
    DOCUMENT_AI_LOCATION: str = Field("us", env="DOCUMENT_AI_LOCATION")
    
    # Model configuration - Hardcoded for car manuals
    EMBEDDINGS_MODEL_ID: str = "text-embedding-005"
    CHATCOMPLETIONS_MODEL_ID: str = Field("gemini-3.8-flash", env="CHATCOMPLETIONS_MODEL_ID")
    
    # Search configuration - Hardcoded for car manuals
    VECTOR_DIMENSIONS: int = 768
    VECTOR_INDEX_NAME: str = "manual_vector_search_index"
    DOCUMENT_VECTOR_INDEX_NAME: str = Field("vector_index", env="DOCUMENT_VECTOR_INDEX_NAME")
    TEXT_INDEX_NAME: str = "manual_text_search_index"
    VECTOR_FIELD_NAME: str = "embedding"
    
    # Multimodal configuration - Voyage AI
    VOYAGE_API_KEY: str = Field(..., env="VOYAGE_API_KEY")
    MULTIMODAL_MODEL_ID: str = Field("voyage-multimodal-3", env="MULTIMODAL_MODEL_ID")
    MULTIMODAL_VECTOR_INDEX_NAME: str = Field(..., env="MULTIMODAL_VECTOR_INDEX_NAME")
    MULTIMODAL_VECTOR_DIMENSIONS: int = 1024
    MAX_PDF_UPLOAD_MB: int = Field(10, ge=1, le=25, env="MAX_PDF_UPLOAD_MB")
    MAX_PDF_PAGES: int = Field(300, ge=1, le=1000, env="MAX_PDF_PAGES")
    GRIDFS_BUCKET_NAME: str = "fs"
    
    # Document configuration - Hardcoded for car manuals
    DOCUMENT_TYPES: List[str] = ["manual", "maintenance", "troubleshooting", "specifications"]
    DEFAULT_DOCUMENT_TYPE: str = "manual"
    
    # AWS Bedrock configuration
    AWS_REGION: str = Field("us-east-1", env="AWS_REGION")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, env="AWS_SECRET_ACCESS_KEY")
    
    # Application settings
    DEBUG: bool = Field(False, env="DEBUG")
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

def get_settings() -> Settings:
    """Return the settings object"""
    settings = Settings()
    # Make sure MONGODB_DB is set from DATABASE_NAME if it's None
    if settings.MONGODB_DB is None and hasattr(settings, 'DATABASE_NAME'):
        settings.MONGODB_DB = settings.DATABASE_NAME
    return settings
