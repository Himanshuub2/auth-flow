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
    async def save_bytes(
        self, data: bytes, destination: str, *, content_type: str | None = None,
    ) -> str:
        """Save raw bytes to storage and return the stored path."""

    @abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        """Read blob/object body by stored path (container-relative, no URL scheme)."""

    @abstractmethod
    def get_url(self, path: str) -> str:
        """Convert a stored path to a public-facing URL."""

    @abstractmethod
    def get_blob_path(self, url: str) -> str | None:
        """Extract the container-relative blob path from a full URL (or return as-is if already a path)."""
