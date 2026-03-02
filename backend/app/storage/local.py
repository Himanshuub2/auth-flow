import logging
import os
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from app.config import settings
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.base_dir = Path(settings.LOCAL_UPLOAD_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, destination: str) -> str:
        full_path = self.base_dir / destination
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            while chunk := await file.read(1024 * 64):
                await f.write(chunk)

        logger.info("File saved: %s", full_path)
        return destination

    async def delete(self, path: str) -> None:
        full_path = self.base_dir / path
        if full_path.exists():
            os.remove(full_path)
            logger.info("File deleted: %s", full_path)

    def get_url(self, path: str) -> str:
        return f"{settings.SERVE_FILES_URL_PREFIX}/{path}"
