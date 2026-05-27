from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredObject:
    provider: str
    bucket: str
    key: str
    public_url: str
    content_type: str | None
    size_bytes: int
    etag: str | None = None
