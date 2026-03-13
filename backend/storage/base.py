from abc import ABC, abstractmethod

from fastapi import UploadFile


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, destination: str) -> str:
        """Save file and return its accessible URL/path."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file by its stored path."""

    @abstractmethod
    def get_url(self, path: str) -> str:
        """Convert a stored path to a public-facing URL."""
