from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 480

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072

    database_url: str = "postgresql+psycopg2://medassist:medassist@localhost:5432/medassist"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "medassist_chunks"

    storage_backend: str = "local"  # local | s3 | supabase
    local_storage_path: str = "/data/storage"
    s3_bucket: str = "medassist-documents"
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    retrieval_top_k: int = 8
    retrieval_candidates: int = 30
    min_dense_score: float = 0.28
    min_keyword_rank: float = 0.05
    chunk_target_tokens: int = 800
    chunk_overlap_ratio: float = 0.15

    ocr_enabled: bool = True
    ocr_languages: str = "eng"

    rate_limit_chat: str = "30/60"
    rate_limit_upload: str = "20/3600"
    rate_limit_default: str = "240/60"

    first_admin_email: str = "admin@example.com"
    first_admin_password: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
