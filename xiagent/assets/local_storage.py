from __future__ import annotations

import hashlib
from pathlib import Path

from xiagent.core.errors import ValidationError


class LocalAssetStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def put_bytes(self, *, file_name: str, content: bytes) -> tuple[str, str, int]:
        digest, storage_uri, size, _created = self.put_bytes_with_status(
            file_name=file_name,
            content=content,
        )
        return digest, storage_uri, size

    def put_bytes_with_status(
        self,
        *,
        file_name: str,
        content: bytes,
    ) -> tuple[str, str, int, bool]:
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(file_name).suffix
        target = self._root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        created = not target.exists()
        if created:
            target.write_bytes(content)
        return digest, target.relative_to(self._root).as_posix(), len(content), created

    def read_bytes(self, storage_uri: str) -> bytes:
        return self._resolve_uri(storage_uri).read_bytes()

    def delete_uri(self, storage_uri: str) -> None:
        target = self._resolve_uri(storage_uri)
        if target.exists():
            target.unlink()

    def _resolve_uri(self, storage_uri: str) -> Path:
        target = (self._root / storage_uri).resolve()
        if not target.is_relative_to(self._root):
            raise ValidationError(
                "invalid_storage_uri",
                "Storage URI must stay inside asset storage root",
            )
        return target
