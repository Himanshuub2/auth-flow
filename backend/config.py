from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://authuser:authpass@localhost:5432/auth-flow"

    MAX_IMAGE_SIZE_BYTES: int = 20 * 1024 * 1024
    MAX_VIDEO_SIZE_BYTES: int = 500 * 1024 * 1024
    MAX_DOCUMENT_FILE_SIZE_BYTES: int = 30 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS: set = frozenset({"png", "jpg", "jpeg", "gif", "bmp", "tiff"})
    ALLOWED_VIDEO_EXTENSIONS: set = frozenset({"mp4"})
    ALLOWED_DOCUMENT_EXTENSIONS: set = frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "pptx",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "tiff",
    })

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 86400
    ITEM_DETAIL_CACHE_TTL_SECONDS: int = 300

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_CONTAINER_NAME: str = "uploads"

    class Config:
        env_file = ".env"


settings = Settings()
