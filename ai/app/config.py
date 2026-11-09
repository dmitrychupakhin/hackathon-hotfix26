from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.provider_settings import normalize_base_url

AI_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AI_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", AI_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )
    api_key: SecretStr = Field(default=SecretStr(""), validation_alias="APIMIRA_API_KEY")
    base_url: str = Field(default="https://apimira.com/v1", validation_alias="APIMIRA_BASE_URL")
    model: str = Field(default="openai/gpt-6-luna", validation_alias="APIMIRA_MODEL")
    llm_timeout: float = Field(default=180, gt=0, validation_alias="AI_LLM_TIMEOUT_SECONDS")
    rate_limit_retries: int = Field(default=3, ge=0, le=5, validation_alias="AI_RATE_LIMIT_RETRIES")
    enable_thinking: bool | None = Field(default=None, validation_alias="APIMIRA_ENABLE_THINKING")
    max_output_tokens: int = Field(
        default=8000, ge=256, le=32000, validation_alias="AI_LLM_MAX_OUTPUT_TOKENS"
    )
    environment: str = Field(default="development", validation_alias="AI_ENV")
    database_path: str = Field(default="data/ai.sqlite3", validation_alias="AI_DATABASE_PATH")
    database_url: SecretStr = Field(default=SecretStr(""), validation_alias="AI_DATABASE_URL")
    source_root: str = Field(default="data/incoming", validation_alias="AI_SOURCE_ROOT")
    file_cache_root: str = Field(default="data/files", validation_alias="AI_FILE_CACHE_ROOT")
    file_import_timeout: float = Field(
        default=300, ge=30, le=1800, validation_alias="AI_FILE_IMPORT_TIMEOUT_SECONDS"
    )
    ocr_enabled: bool = Field(default=False, validation_alias="AI_OCR_ENABLED")
    chunk_target_tokens: int = Field(
        default=2000, ge=256, le=16000, validation_alias="AI_CHUNK_TARGET_TOKENS"
    )
    chunk_overlap_tokens: int = Field(
        default=200, ge=0, le=4000, validation_alias="AI_CHUNK_OVERLAP_TOKENS"
    )
    service_key: SecretStr = Field(default=SecretStr(""), validation_alias="AI_SERVICE_KEY")
    allowed_base_urls: str = Field(default="", validation_alias="AI_ALLOWED_BASE_URLS")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", validation_alias="AI_ALLOWED_ORIGINS"
    )
    context_window: int = Field(
        default=266000, ge=1024, validation_alias="AI_CONTEXT_WINDOW_TOKENS"
    )
    max_context_reductions: int = Field(
        default=5, ge=0, le=8, validation_alias="AI_MAX_CONTEXT_REDUCTIONS"
    )
    concurrent_runs: int = Field(default=2, ge=1, le=8, validation_alias="AI_MAX_CONCURRENT_RUNS")
    pending_runs: int = Field(default=100, ge=1, le=1000, validation_alias="AI_MAX_PENDING_RUNS")
    # Document chats use this ceiling (up to 3600s); plain chats default to 600s.
    # Comparison datasets request their separately configured run budget.
    run_timeout: float = Field(default=1200, gt=0, validation_alias="AI_RUN_TIMEOUT_SECONDS")
    max_model_calls: int = Field(default=48, ge=1, le=200, validation_alias="AI_MAX_MODEL_CALLS")
    max_upload_bytes: int = Field(default=10485760, ge=1024, validation_alias="AI_MAX_UPLOAD_BYTES")
    max_package_bytes: int = Field(
        default=33554432, ge=1024, validation_alias="AI_MAX_PACKAGE_BYTES"
    )
    input_price: float | None = Field(
        default=None, ge=0, validation_alias="AI_INPUT_PRICE_PER_MILLION"
    )
    output_price: float | None = Field(
        default=None, ge=0, validation_alias="AI_OUTPUT_PRICE_PER_MILLION"
    )
    cached_price: float | None = Field(
        default=None, ge=0, validation_alias="AI_CACHED_PRICE_PER_MILLION"
    )
    price_currency: str = Field(default="RUB", validation_alias="AI_PRICE_CURRENCY")

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("AI_ENV must be development, test or production")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("Chunk overlap must be smaller than target")
        if self.environment == "production" and len(self.service_key.get_secret_value()) < 32:
            raise ValueError("Production requires AI_SERVICE_KEY with at least 32 characters")
        self.base_url = normalize_base_url(self.base_url)
        for value in self.allowed_base_urls.split(","):
            if value.strip():
                normalize_base_url(value.strip())
        return self

    @property
    def db_file(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else AI_ROOT / path

    def storage_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else AI_ROOT / path

    @property
    def base_urls(self) -> set[str]:
        return {
            self.base_url,
            *(
                normalize_base_url(v.strip())
                for v in self.allowed_base_urls.split(",")
                if v.strip()
            ),
        }

    @property
    def origins(self) -> list[str]:
        return [v.strip() for v in self.allowed_origins.split(",") if v.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
