from __future__ import annotations

from dataclasses import dataclass

from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.models import StoredObject


class DisabledObjectStorageService(ObjectStorageService):
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        raise RuntimeError("Object storage is not configured")

    async def delete_object(self, *, key: str) -> None:
        return None


class LocalPublicUrlObjectStorageService(ObjectStorageService):
    def __init__(self, *, public_base_url: str = "https://assets.local.invalid") -> None:
        self._public_base_url = public_base_url.rstrip("/")

    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        clean_key = key.strip("/")
        return StoredObject(
            provider="local_public_url",
            bucket="local",
            key=clean_key,
            public_url=f"{self._public_base_url}/{clean_key}",
            content_type=content_type,
            size_bytes=len(content),
            etag=None,
        )

    async def delete_object(self, *, key: str) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ObjectStorageRouter(ObjectStorageService):
    provider: str
    services: dict[str, ObjectStorageService]

    def __post_init__(self) -> None:
        self.current()

    def current(self) -> ObjectStorageService:
        try:
            return self.services[self.provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported object storage provider: {self.provider}") from exc

    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        return await self.current().put_object(
            key=key,
            content=content,
            content_type=content_type,
        )

    async def delete_object(self, *, key: str) -> None:
        await self.current().delete_object(key=key)
