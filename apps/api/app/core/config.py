# IP — Caramurú Construções — assinatura do autor

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "Caramurú Field Engineering API"
    api_version: str = "0.1.0"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://caramuru:caramuru@localhost:5432/caramuru"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "caramuru-evidence"
    minio_use_ssl: bool = False
    upload_temp_dir: str = "data/uploads"
    upload_max_bytes: int = 20_000_000
    upload_chunk_size: int = 8 * 1024 * 1024
    upload_presign_expiry_seconds: int = 900

    secret_key: str = "change-me-in-production"
    jwt_issuer: str = "caramuru-api"
    jwt_audience: str = "caramuru-field"
    sync_max_future_skew_ms: int = 300_000
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
