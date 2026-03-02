from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://eventflow:eventflow_secret@localhost:5432/eventflow"
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 1440

    LOCAL_UPLOAD_DIR: str = str(Path(__file__).resolve().parent.parent / "uploads")
    SERVE_FILES_URL_PREFIX: str = "/files"
    STORAGE_BACKEND: str = "local"

    MAX_IMAGE_SIZE_BYTES: int = 20 * 1024 * 1024
    MAX_VIDEO_SIZE_BYTES: int = 500 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS: set = frozenset({"png", "jpg", "jpeg", "gif", "bmp", "tiff"})
    ALLOWED_VIDEO_EXTENSIONS: set = frozenset({"mp4"})

    class Config:
        env_file = ".env"


settings = Settings()
