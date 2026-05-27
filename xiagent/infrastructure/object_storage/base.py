from __future__ import annotations

from abc import ABC, abstractmethod

from xiagent.infrastructure.object_storage.models import StoredObject


class ObjectStorageService(ABC):
    @abstractmethod
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    async def delete_object(self, *, key: str) -> None:
        raise NotImplementedError
