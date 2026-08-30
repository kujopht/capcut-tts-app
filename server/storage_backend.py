from typing import Protocol, Optional
from server.r2_adapter import R2StorageAdapter

class StorageBackend(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]: ...
    def delete(self, key: str) -> bool: ...
    def usage_bytes(self) -> int: ...

class R2StorageBackendWrapper:
    def __init__(self, r2_adapter: R2StorageAdapter):
        self._adapter = r2_adapter

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        return self._adapter.put(key, data, content_type)

    def get_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]:
        return self._adapter.signed_url(key, expires_seconds)

    def delete(self, key: str) -> bool:
        return self._adapter.delete(key)

    def usage_bytes(self) -> int:
        # Sums up the size of all objects in the bucket to calculate usage
        total = 0
        for obj in self._adapter.list_objects():
            total += obj.size_bytes
        return total

class DriveArchiveBackend:
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError("Drive integration not yet implemented for archive tier")

    def get_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]:
        raise NotImplementedError("Drive integration not yet implemented for archive tier")

    def delete(self, key: str) -> bool:
        raise NotImplementedError("Drive integration not yet implemented for archive tier")

    def usage_bytes(self) -> int:
        raise NotImplementedError("Drive integration not yet implemented for archive tier")
