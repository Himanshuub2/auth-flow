"""Azure Blob Storage backend with streaming upload."""

import logging

from fastapi import UploadFile

from config import settings
from storage.base import StorageBackend

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


class AzureBlobStorageBackend(StorageBackend):
    def __init__(self) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING must be set in .env"
            )
        self._client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING,
        )
        self._container_name = settings.AZURE_CONTAINER_NAME

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
        account_url = self._client.url
        return f"{account_url}{self._container_name}/{path}"
