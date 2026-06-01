from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


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
                                        "required": ["full_name"],
                                        "properties": {
                                            "full_name": {"type": "string", "minLength": 1},
                                            "image_ref": _image_ref_schema(),
                                            "variant": {"type": "string"},
                                            "image_url": {"type": "string"},
                                            "accessories": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
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


def _resolve_character(character: Mapping[str, Any], lookup: Mapping[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("full_name", "variant", "image_url", "accessories"):
        if key in character:
            result[key] = character[key]

    existing_ref = _clean_image_ref(character.get("image_ref"))
    if existing_ref is not None:
        result["image_ref"] = existing_ref
        return result

    name = _text(character.get("full_name"))
    variant = _text(character.get("variant"))
    catalog_item = lookup.get((name, variant)) or lookup.get((name, ""))
    image_ref = _image_ref_from_item(catalog_item) if catalog_item is not None else None
    if image_ref is None:
        image_ref = _image_ref_from_item(character)
    if image_ref is not None:
        result["image_ref"] = image_ref
    return result


def _build_catalog_lookup(asset_catalog: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    source = _mapping(asset_catalog.get("approved_assets")) or asset_catalog
    lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for item in _iter_catalog_items(source):
        name = _text(item.get("name")) or _text(item.get("full_name"))
        if not name:
            continue
        variant = (
            _text(item.get("variant"))
            or _text(item.get("variant_name"))
            or _text(item.get("new_variant_name"))
        )
        normalized = dict(item)
        _store_lookup_item(lookup, (name, ""), normalized)
        if variant:
            _store_lookup_item(lookup, (name, variant), normalized)

    for image in _list(asset_catalog.get("asset_images")):
        if not isinstance(image, Mapping):
            continue
        name = _text(image.get("full_name")) or _text(image.get("name"))
        if not name:
            continue
        variant = _text(image.get("variant")) or _text(image.get("variant_name"))
        normalized = dict(image)
        _store_lookup_item(lookup, (name, variant), normalized)
        _store_lookup_item(lookup, (name, ""), normalized)

    return lookup


def _store_lookup_item(
    lookup: dict[tuple[str, str], dict[str, Any]],
    key: tuple[str, str],
    item: dict[str, Any],
) -> None:
    existing = lookup.get(key)
    if existing is None or (
        _image_ref_from_item(existing) is None and _image_ref_from_item(item) is not None
    ):
        lookup[key] = item


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
    for key in ("matched_variant_id", "asset_id", "matched_asset_id", "default_variant_asset_id"):
        asset_id = _text(item.get(key))
        if asset_id:
            return {"kind": "asset", "asset_id": asset_id, "role": "reference"}
    return None


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


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""
