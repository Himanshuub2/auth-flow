from app.config import settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend


def get_storage() -> StorageBackend:
    if settings.STORAGE_BACKEND == "local":
        return LocalStorageBackend()
    if settings.STORAGE_BACKEND == "azure":
        from app.storage.azure import AzureBlobStorageBackend
        return AzureBlobStorageBackend()
    raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")
