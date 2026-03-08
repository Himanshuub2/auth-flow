"""Azure Blob Storage backend with streaming upload/download.

Currently a stub that mirrors the local backend interface.
Switch STORAGE_BACKEND=azure and provide AZURE_STORAGE_CONNECTION_STRING
and AZURE_CONTAINER_NAME in .env once credentials are available.
"""

import logging
import uuid

from fastapi import UploadFile

from app.config import settings
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB chunks for streaming


class AzureBlobStorageBackend(StorageBackend):
    def __init__(self) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING must be set when using azure storage backend"
            )
        self._client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING,
        )
        self._container_name = settings.AZURE_CONTAINER_NAME

    async def _get_container(self):
        return self._client.get_container_client(self._container_name)

    async def save(self, file: UploadFile, destination: str) -> str:
        container = await self._get_container()
        blob = container.get_blob_client(destination)

        # Stream upload in chunks to handle large files without buffering
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

    async def delete(self, path: str) -> None:
        container = await self._get_container()
        blob = container.get_blob_client(path)
        try:
            await blob.delete_blob()
            logger.info("Azure blob deleted: %s/%s", self._container_name, path)
        except Exception:
            logger.warning("Azure blob delete failed: %s/%s", self._container_name, path, exc_info=True)

    def get_url(self, path: str) -> str:
        account_url = self._client.url
        return f"{account_url}{self._container_name}/{path}"
