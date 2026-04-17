from abc import ABC, abstractmethod

from fastapi import UploadFile


class StorageBackend(ABC):
    @abstractmethod
    async def save(
        self,
        file: UploadFile,
        destination: str,
        *,
        content_type: str | None = None,
        content_disposition: str | None = None,
    ) -> str:
        """Save file and return its accessible URL/path."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file by its stored path."""

    @abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        """Read object contents by stored path (path within container, no URL scheme)."""

    @abstractmethod
    def get_url(self, path: str) -> str:
        """Convert a stored path to a public-facing URL."""
