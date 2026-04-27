from pydantic import model_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine import URL


_DB_NAME_BY_ENV: dict[str, str] = {
    "dev": "ecp_dev",
    "uat": "ecp_uat",
    "prod": "ecp_prod",
}


class Settings(BaseSettings):
    # ── Required from .env ────────────────────────────────────────────────
    APP_ENV: str = "dev"          # dev | uat | prod
    KV_URL: str = ""              # https://<vault-name>.vault.azure.net

    # ── DB params (filled from Key Vault at startup) ───────────────────
    DATABASE_URL: str = ""
    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_USER: str = ""
    DB_PASSWORD: str = ""

    # ── File limits ───────────────────────────────────────────────────────
    MAX_IMAGE_SIZE_BYTES: int = 20 * 1024 * 1024
    MAX_VIDEO_SIZE_BYTES: int = 500 * 1024 * 1024
    MAX_DOCUMENT_FILE_SIZE_BYTES: int = 35 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS: set = frozenset({"png", "jpg", "jpeg", "gif", "bmp", "tiff"})
    ALLOWED_VIDEO_EXTENSIONS: set = frozenset({"mp4"})
    ALLOWED_DOCUMENT_EXTENSIONS: set = frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "pptx",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "tiff",
    })

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 86400
    ITEM_DETAIL_CACHE_TTL_SECONDS: int = 300

    # ── Azure Blob Storage ────────────────────────────────────────────────
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_CONTAINER_NAME: str = "uploads"
    BYPASS_AZURE_UPLOAD: bool = True

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def _load_db_from_kv(self) -> "Settings":
        """
        If DB_HOST is already set (e.g. from .env / env vars), skip Key Vault.
        Otherwise fetch DB_HOST, DB_PORT, DB_USER, DB_PASSWORD from Key Vault,
        then build DATABASE_URL using URL.create().
        """
        if self.DB_HOST:
            # Params supplied directly — just build the URL.
            self._build_database_url()
            return self

        if not self.KV_URL:
            # Local dev shortcut: DATABASE_URL must already be set in .env.
            return self

        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            client = SecretClient(vault_url=self.KV_URL, credential=DefaultAzureCredential())
            self.DB_HOST = client.get_secret("DB-HOST").value or ""
            self.DB_PORT = int(client.get_secret("DB-PORT").value or 5432)
            self.DB_USER = client.get_secret("DB-USER").value or ""
            self.DB_PASSWORD = client.get_secret("DB-PASSWORD").value or ""
        except Exception as exc:
            raise RuntimeError(f"Failed to load DB secrets from Key Vault: {exc}") from exc

        self._build_database_url()
        return self

    def _build_database_url(self) -> None:
        if not self.DB_HOST:
            return
        db_name = _DB_NAME_BY_ENV.get(self.APP_ENV.lower(), f"ecp_{self.APP_ENV.lower()}")
        self.DATABASE_URL = str(
            URL.create(
                drivername="postgresql+asyncpg",
                username=self.DB_USER,
                password=self.DB_PASSWORD,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=db_name,
            )
        )


settings = Settings()
