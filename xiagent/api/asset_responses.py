from __future__ import annotations

from dataclasses import asdict
from typing import Any

from xiagent.assets.models import AssetRecord

_HIDDEN_ASSET_FIELDS = {"storage_uri"}
_HIDDEN_METADATA_FIELDS = {"storage_uri"}


def asset_response(asset: AssetRecord) -> dict[str, Any]:
    item = asdict(asset)
    for field in _HIDDEN_ASSET_FIELDS:
        item.pop(field, None)
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        item["metadata"] = {
            key: value
            for key, value in metadata.items()
            if key not in _HIDDEN_METADATA_FIELDS
        }
    item["content_url"] = f"/api/assets/{asset.asset_id}/content"
    item["thumbnail_url"] = f"/api/assets/{asset.asset_id}/thumbnail"
    return item


def asset_list_response(assets: list[AssetRecord]) -> list[dict[str, Any]]:
    return [asset_response(asset) for asset in assets]
