from storage.azure import AzureBlobStorageBackend

_backend: AzureBlobStorageBackend | None = None


def get_storage() -> AzureBlobStorageBackend:
    global _backend
    if _backend is None:
        _backend = AzureBlobStorageBackend()
    return _backend
