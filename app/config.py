"""
Invoice Detective AI — Application Configuration.

Loads settings from .env file using Pydantic Settings.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # App settings
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me-to-a-random-secret"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./invoice_detective.db"
    SEED_DEMO_DATA: bool = False

    # File upload
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 20
    MAX_UPLOAD_COUNT: int = 50

    # Reports
    REPORT_DIR: str = "./reports"

    # CORS — comma-separated origins
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"

    # OCR (optional — set path to tesseract binary)
    TESSERACT_PATH: Optional[str] = None

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    @property
    def cors_origins_list(self) -> list[str]:
        """Split comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum file size in bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
