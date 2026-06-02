from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AssetRecord:
    asset_id: str
    scope: str
    project_id: str | None
    asset_type: str
    name: str
    mime_type: str | None
    content_hash: str | None
    size_bytes: int | None
    storage_uri: str | None
    text_content: str | None
    metadata: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str
    deleted_at: str | None


@dataclass(frozen=True, slots=True)
class AssetContent:
    asset_id: str
    asset_type: str
    content_type: str | None
    bytes_content: bytes | None = None
    text_content: str | None = None
    cache_hit: bool = False


@dataclass(frozen=True, slots=True)
class AssetSearchResult:
    items: list[AssetRecord] = field(default_factory=list)
    total: int = 0


@dataclass(frozen=True, slots=True)
class AssetCollectionRecord:
    collection_id: str
    scope: str
    project_id: str | None
    parent_id: str | None
    name: str
    description: str | None
    sort_order: int
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AssetTagRecord:
    tag_id: str
    scope: str
    project_id: str | None
    name: str
    description: str | None
    created_by: str
    created_at: str
    updated_at: str
    asset_count: int = 0
