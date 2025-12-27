from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://podcast:podcast@localhost:5432/podcast_search"

    def validate_production_secrets(self) -> list[str]:
        """
        Validate that required secrets are properly set for production.

        Returns:
            List of validation error messages (empty if all valid)
        """
        errors = []

        if self.ENVIRONMENT == "production":
            # Check admin secret is not default
            if self.ADMIN_SECRET == "change-me-in-production":
                errors.append("ADMIN_SECRET must be changed from default in production")

            # Check admin secret is strong enough (min 32 chars)
            if len(self.ADMIN_SECRET) < 32:
                errors.append("ADMIN_SECRET must be at least 32 characters in production")

            # Check CORS is configured (not wildcarded)
            if "*" in self.cors_origins_list:
                errors.append("CORS_ORIGINS cannot be '*' in production")

            # Check database is not localhost
            if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
                errors.append("DATABASE_URL should not use localhost in production")

        return errors

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "podcast_chunks"

    # OpenAI
    OPENAI_API_KEY: str
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # Anthropic
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Transcription - AssemblyAI
    ASSEMBLYAI_API_KEY: str | None = None
    ASSEMBLYAI_MAX_CONCURRENT: int = 32

    # Transcription - Deepgram
    DEEPGRAM_API_KEY: str | None = None
    DEEPGRAM_MAX_CONCURRENT: int = 50

    # Transcription - Whisper (original OpenAI)
    WHISPER_MODEL: str = "large-v3"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_MAX_CONCURRENT: int = 2

    # Transcription - Faster-Whisper (4x faster, recommended for local)
    FASTER_WHISPER_MODEL: str = "large-v3"
    FASTER_WHISPER_DEVICE: str = "auto"  # "auto", "cuda", or "cpu"
    FASTER_WHISPER_COMPUTE_TYPE: str = "auto"  # "auto", "float16", "int8", "int8_float16"
    FASTER_WHISPER_MAX_CONCURRENT: int = 2

    # Transcription - Modal Cloud (serverless GPU)
    MODAL_WHISPER_MODEL: str = "large-v3"
    MODAL_GPU_TYPE: str = "A10G"  # T4, A10G, A100
    MODAL_MAX_CONCURRENT: int = 10

    # HuggingFace (for pyannote diarization)
    HF_TOKEN: str | None = None

    # Default provider
    DEFAULT_TRANSCRIPTION_PROVIDER: Literal[
        "assemblyai", "deepgram", "whisper", "faster-whisper", "modal-cloud"
    ] = "assemblyai"

    # Application
    ENVIRONMENT: Literal["development", "production"] = "development"
    PUBLIC_URL: str = "http://localhost:3000"
    ADMIN_SECRET: str = "change-me-in-production"

    # CORS - comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100  # requests per window
    RATE_LIMIT_WINDOW: int = 60  # seconds

    # Database pool settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Batch processing - MUST be <= DB_POOL_SIZE to avoid pool exhaustion
    BATCH_CONCURRENCY: int = 5  # Max concurrent episodes in a batch

    @property
    def safe_batch_concurrency(self) -> int:
        """Ensure batch concurrency doesn't exceed pool size."""
        return min(self.BATCH_CONCURRENCY, self.DB_POOL_SIZE)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if self.ENVIRONMENT == "development":
            return ["*"]  # Allow all in development
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Chunking
    CHUNK_SIZE: int = 500  # words
    CHUNK_OVERLAP: int = 50  # words

    # Paths
    TRANSCRIPTS_DIR: str = "/app/data/transcripts"
    AUDIO_DIR: str = "/app/data/audio"

    # Redis (optional)
    REDIS_URL: str | None = None

    # Sentry (optional)
    SENTRY_DSN: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
