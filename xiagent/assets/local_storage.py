from __future__ import annotations

import hashlib
from pathlib import Path


class LocalAssetStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def put_bytes(self, *, file_name: str, content: bytes) -> tuple[str, str, int]:
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(file_name).suffix
        target = self._root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        return digest, target.relative_to(self._root).as_posix(), len(content)

    def read_bytes(self, storage_uri: str) -> bytes:
        return (self._root / storage_uri).read_bytes()
