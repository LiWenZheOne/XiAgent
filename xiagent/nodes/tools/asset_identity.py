from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ASSET_TYPE_TAGS: dict[str, str] = {
    "character": "角色",
    "scene": "地点",
    "prop": "道具",
    "episode_metadata": "集元数据",
    "asset": "资产",
}

ASSET_TAG_TYPES: dict[str, str] = {value: key for key, value in ASSET_TYPE_TAGS.items()}
REMOVED_ASSET_FIELDS = {
    "full_name",
    "asset_key",
    "variant_name",
    "variant",
    "new_variant_name",
    "matched_variant",
    "matched_variant_id",
    "required_tags",
    "reference_assets",
    "accessories",
}


def normalize_asset_record(
    value: Mapping[str, Any],
    *,
    default_asset_type: str | None = None,
) -> dict[str, Any]:
    """Return a copy with canonical asset_type, asset_name and asset_tags fields.

    Workflow payloads must use asset_type, asset_name and asset_tags directly.
    Asset-library records may still provide name/tags because those are storage
    fields, not workflow identity aliases. The canonical tags intentionally
    exclude the first-level type tag and the main asset name.
    """

    result = {key: item for key, item in value.items() if key not in REMOVED_ASSET_FIELDS}
    asset_type = asset_type_from_record(value, default_asset_type=default_asset_type)
    asset_name = asset_name_from_record(value)
    asset_tags = asset_tags_from_record(value, asset_type=asset_type, asset_name=asset_name)

    if asset_type:
        result["asset_type"] = asset_type
    if asset_name:
        result["asset_name"] = asset_name
    if asset_tags:
        result["asset_tags"] = asset_tags
    return result


def asset_type_from_record(
    value: Mapping[str, Any],
    *,
    default_asset_type: str | None = None,
) -> str:
    raw = _text(value.get("asset_type")) or _text(default_asset_type)
    if raw in ASSET_TYPE_TAGS:
        return raw
    if raw in ASSET_TAG_TYPES:
        return ASSET_TAG_TYPES[raw]

    tags = _string_list(value.get("tags"))
    if tags and tags[0] in ASSET_TAG_TYPES:
        return ASSET_TAG_TYPES[tags[0]]

    name = _text(value.get("name"))
    parts = _split_composite_name(name)
    if parts and parts[0] in ASSET_TAG_TYPES:
        return ASSET_TAG_TYPES[parts[0]]
    return ""


def asset_name_from_record(value: Mapping[str, Any]) -> str:
    explicit = _text(value.get("asset_name"))
    if explicit:
        return explicit

    raw = _text(value.get("name"))
    if raw:
        parts = _split_composite_name(raw)
        if len(parts) >= 2 and parts[0] in ASSET_TAG_TYPES:
            return parts[1]
        return raw

    tags = _string_list(value.get("tags"))
    if len(tags) >= 2 and tags[0] in ASSET_TAG_TYPES:
        return tags[1]
    return ""


def asset_tags_from_record(
    value: Mapping[str, Any],
    *,
    asset_type: str = "",
    asset_name: str = "",
) -> list[str]:
    tags = _string_list(value.get("asset_tags"))
    if tags:
        return _clean_tags(tags, asset_type=asset_type, asset_name=asset_name)

    name = _text(value.get("name"))
    parts = _split_composite_name(name)
    if len(parts) >= 2 and parts[0] in ASSET_TAG_TYPES:
        return _clean_tags(parts[2:], asset_type=asset_type, asset_name=asset_name)

    library_tags = _string_list(value.get("tags"))
    if library_tags:
        return _clean_tags(library_tags, asset_type=asset_type, asset_name=asset_name)

    return []


def tag_overlap_score(candidate_tags: list[str], target_tags: list[str]) -> int:
    if not target_tags:
        return 0
    candidate = {_normalize(tag) for tag in candidate_tags if tag}
    return sum(1 for tag in target_tags if _normalize(tag) in candidate)


def _clean_tags(tags: list[str], *, asset_type: str, asset_name: str) -> list[str]:
    type_tag = ASSET_TYPE_TAGS.get(asset_type, "")
    result: list[str] = []
    for tag in tags:
        clean = tag.strip()
        if not clean or clean == type_tag or clean == asset_name:
            continue
        if clean not in result:
            result.append(clean)
    return result


def _split_composite_name(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.replace("＿", "_").split("_") if part.strip()]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _normalize(value: str) -> str:
    return value.strip().lower()
