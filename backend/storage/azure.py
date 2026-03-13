"""Azure Blob Storage backend with streaming upload and short-lived SAS URLs."""

import logging
from datetime import datetime, timedelta
from typing import Any

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


class AzureBlobStorageBackend(StorageBackend):
    def __init__(self) -> None:
        from azure.storage.blob.aio import BlobServiceClient
        from azure.storage.blob import BlobSasPermissions  # type: ignore[attr-defined]

        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING must be set in .env"
            )

        self._client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING,
        )
        self._container_name = settings.AZURE_CONTAINER_NAME

        conn_parts = _parse_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
        self._account_name: str | None = conn_parts.get("AccountName")
        self._account_key: str | None = conn_parts.get("AccountKey")
        self._sas_permissions_cls: Any = BlobSasPermissions

        if not self._account_name or not self._account_key:
            logger.warning(
                "Azure connection string is missing AccountName or AccountKey; "
                "falling back to unsigned blob URLs."
            )

    async def _get_container(self):
        return self._client.get_container_client(self._container_name)

    async def save(self, file: UploadFile, destination: str) -> str:
        try:
            container = await self._get_container()
            blob = container.get_blob_client(destination)

            async def _chunk_reader():
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

            await blob.upload_blob(
                _chunk_reader(),
                overwrite=True,
                max_concurrency=4,
            )
            logger.info("Azure blob saved: %s/%s", self._container_name, destination)
            return destination
        except Exception:
            logger.exception("Azure blob upload failed: %s/%s", self._container_name, destination)
            raise

    async def delete(self, path: str) -> None:
        try:
            container = await self._get_container()
            blob = container.get_blob_client(path)
            await blob.delete_blob()
            logger.info("Azure blob deleted: %s/%s", self._container_name, path)
        except Exception:
            logger.warning("Azure blob delete failed: %s/%s", self._container_name, path, exc_info=True)

    def get_url(self, path: str) -> str:
        """
        Return a SAS URL for the given blob path with a 10-minute expiry.

        Falls back to an unsigned URL if SAS generation is not possible, and
        logs errors appropriately.
        """
        account_url = self._client.url
        base_url = f"{account_url}{self._container_name}/{path}"

        # If we don't have the pieces needed to sign, return the plain URL.
        if not self._account_name or not self._account_key:
            logger.debug(
                "Returning unsigned Azure blob URL for %s/%s; missing account credentials",
                self._container_name,
                path,
            )
            return base_url

        try:
            from azure.storage.blob import generate_blob_sas  # type: ignore[attr-defined]

            expiry = datetime.utcnow() + timedelta(minutes=10)
            permissions = self._sas_permissions_cls(read=True)

            sas_token = generate_blob_sas(
                account_name=self._account_name,
                container_name=self._container_name,
                blob_name=path,
                account_key=self._account_key,
                permission=permissions,
                expiry=expiry,
            )

            signed_url = f"{base_url}?{sas_token}"
            logger.debug(
                "Generated SAS URL for blob %s/%s with 10-minute expiry",
                self._container_name,
                path,
            )
            return signed_url
        except Exception:
            logger.exception(
                "Failed to generate SAS URL for Azure blob: %s/%s; returning unsigned URL",
                self._container_name,
                path,
            )
            return base_url
