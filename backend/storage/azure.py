"""Azure Blob Storage backend with streaming upload and short-lived SAS URLs."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from fastapi import UploadFile

from config import settings
from storage.base import StorageBackend

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


def _parse_connection_string(conn_str: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for segment in conn_str.split(";"):
        if not segment:
            continue
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        parts[key.strip()] = value.strip()
    return parts


def _blob_path_from_url(url: str, container_name: str) -> str | None:
    """
    Extract blob path from an Azure blob URL (with or without SAS query string).
    Returns the path after the container segment, or None if not parseable.
    """
    if "://" not in url or not container_name:
        return None
    try:
        # Strip query string (SAS) if present
        base = url.split("?", 1)[0]
        # .../container_name/path/to/blob
        prefix = f"/{container_name}/"
        if prefix not in base:
            return None
        idx = base.index(prefix) + len(prefix)
        raw = base[idx:].strip("/")
        return unquote(raw) if raw else None
    except Exception:
        return None


def _fake_image_url(path: str) -> str:
    """Return a placeholder image URL for testing (bypass mode)."""
    seed = hashlib.md5(path.encode()).hexdigest()[:8]
    w, h = 400, 300
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


class AzureBlobStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self._bypass = getattr(settings, "BYPASS_AZURE_UPLOAD", False)
        self._container_name = settings.AZURE_CONTAINER_NAME
        self._client: Any = None
        self._account_name: str | None = None
        self._account_key: str | None = None
        self._sas_permissions_cls: Any = None

        if self._bypass:
            logger.info("Azure blob upload bypass enabled: returning fake URLs for testing")
            return

        from azure.storage.blob.aio import BlobServiceClient
        from azure.storage.blob import BlobSasPermissions  # type: ignore[attr-defined]

        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING must be set in .env"
            )

        self._client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING,
            logging_enable=False,
        )
        conn_parts = _parse_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
        self._account_name = conn_parts.get("AccountName")
        self._account_key = conn_parts.get("AccountKey")
        self._sas_permissions_cls = BlobSasPermissions

        if not self._account_name or not self._account_key:
            logger.warning(
                "Azure connection string is missing AccountName or AccountKey; "
                "falling back to unsigned blob URLs."
            )

    async def _get_container(self):
        return self._client.get_container_client(self._container_name)

    async def save(
        self,
        file: UploadFile,
        destination: str,
        *,
        content_type: str | None = None,
        content_disposition: str | None = None,
    ) -> str:
        if self._bypass:
            logger.debug("Bypass: skipping Azure upload for %s", destination)
            return destination

        try:
            from azure.storage.blob import ContentSettings  # type: ignore[attr-defined]

            container = await self._get_container()
            blob = container.get_blob_client(destination)

            async def _chunk_reader():
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

            content_settings = None
            if content_type or content_disposition:
                content_settings = ContentSettings(
                    content_type=content_type,
                    content_disposition=content_disposition,
                )

            await blob.upload_blob(
                _chunk_reader(),
                overwrite=True,
                max_concurrency=4,
                content_settings=content_settings,
                logging_enable=False,
            )
            logger.info("Azure blob saved: %s/%s", self._container_name, destination)
            return destination
        except Exception:
            logger.exception("Azure blob upload failed: %s/%s", self._container_name, destination)
            raise

    async def delete(self, path: str) -> None:
        if self._bypass:
            logger.debug("Bypass: skipping Azure delete for %s", path)
            return
        try:
            container = await self._get_container()
            blob = container.get_blob_client(path)
            await blob.delete_blob(logging_enable=False)
            logger.info("Azure blob deleted: %s/%s", self._container_name, path)
        except Exception:
            logger.warning("Azure blob delete failed: %s/%s", self._container_name, path, exc_info=True)

    async def read_bytes(self, path: str) -> bytes:
        """Download full blob body for server-side processing (e.g. bulk applicability)."""
        if self._bypass:
            raise OSError(
                "Cannot read blobs when BYPASS_AZURE_UPLOAD is enabled; "
                "use real Azure storage for bulk applicability processing."
            )
        try:
            container = await self._get_container()
            blob = container.get_blob_client(path)
            downloader = await blob.download_blob()
            return await downloader.readall()
        except Exception:
            logger.exception("Azure blob download failed: %s/%s", self._container_name, path)
            raise

    def get_read_url(self, path_or_url: str) -> str:
        """
        Always return a fresh SAS URL (10 min expiry). If path_or_url is a blob path
        (no '://'), use it directly. If it is a full blob URL (legacy), extract the
        blob path and generate a new SAS URL. When bypass is enabled, returns a fake image URL.
        """
        if self._bypass:
            path = path_or_url
            if "://" in path_or_url:
                path = _blob_path_from_url(path_or_url, self._container_name) or path_or_url
            return _fake_image_url(path)
        if "://" in path_or_url:
            path = _blob_path_from_url(path_or_url, self._container_name)
            if path is not None:
                return self.get_url(path)
            logger.warning(
                "Could not extract blob path from URL for container %s; returning URL as-is",
                self._container_name,
            )
            return path_or_url
        return self.get_url(path_or_url)

    def _generate_sas_url(
        self,
        path: str,
        *,
        read: bool = False,
        write: bool = False,
        create: bool = False,
        expiry_minutes: int = 10,
    ) -> str:
        """Generate a SAS URL for a blob with the specified permissions and expiry."""
        if self._bypass:
            return _fake_image_url(path)

        account_url = self._client.url
        base_url = f"{account_url}{self._container_name}/{path}"

        if not self._account_name or not self._account_key:
            logger.debug(
                "Returning unsigned Azure blob URL for %s/%s; missing account credentials",
                self._container_name,
                path,
            )
            return base_url

        try:
            from azure.storage.blob import generate_blob_sas  # type: ignore[attr-defined]

            now_utc = datetime.now(timezone.utc)
            start_naive = (now_utc - timedelta(hours=1)).replace(tzinfo=None)
            expiry_naive = (now_utc + timedelta(minutes=expiry_minutes)).replace(tzinfo=None)
            permissions = self._sas_permissions_cls(read=read, write=write, create=create)

            sas_token = generate_blob_sas(
                account_name=self._account_name,
                container_name=self._container_name,
                blob_name=path,
                account_key=self._account_key,
                permission=permissions,
                start=start_naive,
                expiry=expiry_naive,
            )

            signed_url = f"{base_url}?{sas_token}"
            logger.debug(
                "Generated SAS URL for blob %s/%s (read=%s, write=%s, expiry=%dm)",
                self._container_name,
                path,
                read,
                write,
                expiry_minutes,
            )
            return signed_url
        except Exception:
            logger.exception(
                "Failed to generate SAS URL for Azure blob: %s/%s; returning unsigned URL",
                self._container_name,
                path,
            )
            return base_url

    def get_url(self, path: str) -> str:
        """Return a read SAS URL for the given blob path with a 10-minute expiry."""
        return self._generate_sas_url(path, read=True, expiry_minutes=10)

    def get_container_upload_sas(self, expiry_minutes: int = 120) -> tuple[str, str]:
        """
        Return (base_url, sas_token) for direct uploads from the browser.

        base_url is `https://{account}.blob.core.windows.net/{container}/` (trailing slash).
        sas_token is the query string without a leading ``?``. The FE builds the final URL as:
        ``{base_url}{blob_path}?{sas_token}`` where blob_path is e.g. ``events/events-{slug}/file.jpg``.
        """
        if self._bypass:
            base = f"https://fake.blob.core.windows.net/{self._container_name}/"
            return base, "sv=bypass&sig=fake"

        account_url = self._client.url
        base_url = f"{account_url}{self._container_name}/"

        if not self._account_name or not self._account_key:
            logger.debug(
                "Cannot sign container SAS for %s; returning base URL with empty token",
                self._container_name,
            )
            return base_url, ""

        try:
            from azure.storage.blob import ContainerSasPermissions, generate_container_sas  # type: ignore[attr-defined]

            now_utc = datetime.now(timezone.utc)
            start_naive = (now_utc - timedelta(hours=1)).replace(tzinfo=None)
            expiry_naive = (now_utc + timedelta(minutes=expiry_minutes)).replace(tzinfo=None)
            permissions = ContainerSasPermissions(read=True, write=True, create=True)

            sas_token = generate_container_sas(
                account_name=self._account_name,
                container_name=self._container_name,
                account_key=self._account_key,
                permission=permissions,
                start=start_naive,
                expiry=expiry_naive,
            )
            logger.debug(
                "Generated container upload SAS for %s with %dm expiry",
                self._container_name,
                expiry_minutes,
            )
            return base_url, sas_token
        except Exception:
            logger.exception(
                "Failed to generate container SAS for %s; returning unsigned base URL",
                self._container_name,
            )
            return base_url, ""
