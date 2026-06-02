from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record, tag_overlap_score


class ResolveSegmentImageRefsNode(BaseNode):
    """用资产目录确定性补全段落资产分配中的图片引用。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.resolve_segment_image_refs.v1",
            name="Resolve Segment Image Refs",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["segment_assignments", "asset_catalog"],
                "properties": {
                    "segment_assignments": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "asset_catalog": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["segment_assignments"],
                "properties": {
                    "segment_assignments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["segment_index", "characters", "key_props"],
                            "properties": {
                                "segment_index": {"type": "integer", "minimum": 0},
                                "location": {"type": "string"},
                                "time": {"type": "string"},
                                "characters": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["asset_type", "asset_name"],
                                        "properties": {
                                            "asset_type": {"type": "string", "minLength": 1},
                                            "asset_name": {"type": "string", "minLength": 1},
                                            "asset_tags": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                            "appearance_description": {"type": "string"},
                                            "presence": {"type": "string"},
                                            "visibility": {"type": "string"},
                                            "reason": {"type": "string"},
                                            "image_ref": _image_ref_schema(),
                                            "image_url": {"type": "string"},
                                        },
                                        "additionalProperties": False,
                                    },
                                },
                                "key_props": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1},
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
                },
                "additionalProperties": False,
            },
            description="根据资产目录中的 reference_image_ref、matched_asset_ref 或 asset_id 为段落角色补全 image_ref。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        _ = ctx
        segment_assignments = _list(inputs.get("segment_assignments"))
        catalog_lookup = _build_catalog_lookup(_mapping(inputs.get("asset_catalog")))

        resolved_assignments: list[dict[str, Any]] = []
        for assignment in segment_assignments:
            if not isinstance(assignment, Mapping):
                continue
            resolved_assignment = _copy_assignment(assignment)
            characters = assignment.get("characters")
            if not isinstance(characters, list):
                resolved_assignment["characters"] = []
                resolved_assignments.append(resolved_assignment)
                continue

            resolved_characters: list[dict[str, Any]] = []
            for character in characters:
                if not isinstance(character, Mapping):
                    continue
                resolved_characters.append(_resolve_character(character, catalog_lookup))
            resolved_assignment["characters"] = resolved_characters
            resolved_assignments.append(resolved_assignment)

        return NodeResult(status="succeeded", output={"segment_assignments": resolved_assignments})


def _image_ref_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["kind"],
        "properties": {
            "kind": {"type": "string", "enum": ["asset", "data_uri"]},
            "asset_id": {"type": "string", "minLength": 1},
            "data": {"type": "string", "minLength": 1},
            "role": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _copy_assignment(assignment: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("segment_index", "location", "time", "key_props"):
        if key in assignment:
            result[key] = assignment[key]
    result.setdefault("key_props", [])
    return result


def _resolve_character(
    character: Mapping[str, Any],
    lookup: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    normalized_character = normalize_asset_record(character, default_asset_type="character")
    result: dict[str, Any] = {}
    for key in (
        "asset_type",
        "asset_name",
        "asset_tags",
        "appearance_description",
        "presence",
        "visibility",
        "reason",
        "image_url",
    ):
        if key in normalized_character:
            result[key] = normalized_character[key]

    asset_type = _text(normalized_character.get("asset_type")) or "character"
    name = _text(normalized_character.get("asset_name"))
    asset_tags = _string_list(normalized_character.get("asset_tags"))
    catalog_item = _best_catalog_item(lookup.get((asset_type, name), []), asset_tags)
    appearance_description = _appearance_description(catalog_item) or _appearance_description(character)
    if appearance_description:
        result["appearance_description"] = appearance_description

    existing_ref = _clean_image_ref(character.get("image_ref"))
    if existing_ref is not None:
        result["image_ref"] = existing_ref
        image_url = _image_url_from_item(character)
        if image_url:
            result["image_url"] = image_url
        return result

    image_ref = _image_ref_from_item(catalog_item) if catalog_item is not None else None
    if image_ref is None:
        image_ref = _image_ref_from_item(character)
    if image_ref is not None:
        result["image_ref"] = image_ref
        image_url = _image_url_from_item(catalog_item) or _image_url_from_item(character)
        if image_url:
            result["image_url"] = image_url
    return result


def _build_catalog_lookup(asset_catalog: Mapping[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    source = _mapping(asset_catalog.get("approved_assets")) or asset_catalog
    lookup: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for item in _iter_catalog_items(source):
        normalized = normalize_asset_record(item, default_asset_type="character")
        name = _text(normalized.get("asset_name"))
        if not name:
            continue
        _store_lookup_item(lookup, (_text(normalized.get("asset_type")) or "character", name), normalized)

    for image in _list(asset_catalog.get("asset_images")):
        if not isinstance(image, Mapping):
            continue
        normalized = normalize_asset_record(image, default_asset_type="character")
        name = _text(normalized.get("asset_name"))
        if not name:
            continue
        _store_lookup_item(lookup, (_text(normalized.get("asset_type")) or "character", name), normalized)

    return lookup

def _store_lookup_item(
    lookup: dict[tuple[str, str], list[dict[str, Any]]],
    key: tuple[str, str],
    item: dict[str, Any],
) -> None:
    lookup.setdefault(key, []).append(item)


def _best_catalog_item(candidates: list[dict[str, Any]], target_tags: list[str]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            1 if _image_ref_from_item(item) is not None else 0,
            tag_overlap_score(_string_list(item.get("asset_tags")), target_tags),
            len(_string_list(item.get("asset_tags"))),
        ),
    )


def _iter_catalog_items(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []
    for key in ("characters", "assets", "props"):
        value = source.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, Mapping))
    return items


def _image_ref_from_item(item: Mapping[str, Any] | None) -> dict[str, str] | None:
    if item is None:
        return None
    for key in ("reference_image_ref", "matched_asset_ref", "asset_ref", "default_variant_ref"):
        image_ref = _clean_image_ref(item.get(key))
        if image_ref is not None:
            return image_ref
    for key in ("asset_id", "matched_asset_id"):
        asset_id = _text(item.get(key))
        if asset_id:
            return {"kind": "asset", "asset_id": asset_id, "role": "reference"}
    return None


def _image_url_from_item(item: Mapping[str, Any] | None) -> str:
    if item is None:
        return ""
    return _text(item.get("image_url")) or _text(item.get("public_url")) or _text(item.get("storage_uri"))


def _appearance_description(item: Mapping[str, Any] | None) -> str:
    if item is None:
        return ""
    for key in ("appearance_description", "variant_description", "visual_description", "description"):
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _clean_image_ref(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    kind = _text(value.get("kind"))
    if kind == "asset":
        asset_id = _text(value.get("asset_id"))
        if asset_id:
            return {"kind": "asset", "asset_id": asset_id, "role": _text(value.get("role")) or "reference"}
    if kind == "data_uri":
        data = _text(value.get("data"))
        if data.startswith("data:image/"):
            return {"kind": "data_uri", "data": data, "role": _text(value.get("role")) or "reference"}
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""
