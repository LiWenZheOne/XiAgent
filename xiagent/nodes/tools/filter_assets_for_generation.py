from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class FilterAssetsForGenerationNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.filter_assets_for_generation.v1",
            name="Filter Assets For Generation",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "approved_assets": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "prompts_per_item": {"type": "integer", "minimum": 1, "maximum": 6, "default": 1},
                },
                "required": ["approved_assets"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "approved_assets",
                    "asset_count",
                    "new_asset_count",
                    "matched_asset_count",
                    "has_assets_to_generate",
                    "generation_summary",
                ],
                "properties": {
                    "approved_assets": {
                        "type": "object",
                        "required": ["characters", "assets", "props"],
                        "properties": {
                            "characters": {"type": "array", "items": {"type": "object"}},
                            "assets": {"type": "array", "items": {"type": "object"}},
                            "props": {"type": "array", "items": {"type": "object"}},
                        },
                        "additionalProperties": True,
                    },
                    "asset_count": {"type": "integer", "minimum": 0},
                    "new_asset_count": {"type": "integer", "minimum": 0},
                    "matched_asset_count": {"type": "integer", "minimum": 0},
                    "has_assets_to_generate": {"type": "boolean"},
                    "generation_summary": {
                        "type": "object",
                        "required": [
                            "total_asset_count",
                            "new_asset_count",
                            "matched_asset_count",
                            "has_assets_to_generate",
                        ],
                        "properties": {
                            "total_asset_count": {"type": "integer", "minimum": 0},
                            "new_asset_count": {"type": "integer", "minimum": 0},
                            "matched_asset_count": {"type": "integer", "minimum": 0},
                            "has_assets_to_generate": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            description="Filter out assets already matched to the asset library before prompt/image generation.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        approved_assets = inputs.get("approved_assets")
        if not isinstance(approved_assets, Mapping):
            raise ValidationError(
                code="filter_assets_approved_assets_required",
                message="approved_assets must be an object",
            )

        filtered: dict[str, list[dict[str, Any]]] = {}
        total_asset_count = 0
        matched_asset_count = 0
        prompts_per_item = _bounded_int(inputs.get("prompts_per_item"), fallback=1, minimum=1, maximum=6)
        for key in ("characters", "assets", "props"):
            value = approved_assets.get(key)
            items = value if isinstance(value, list) else []
            total_asset_count += len([item for item in items if isinstance(item, Mapping)])
            filtered_items: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                if _is_existing_asset(item):
                    matched_asset_count += 1
                    continue
                next_item = await _with_reference_context(ctx, _with_target_appearance_description(dict(item)))
                next_item["prompts_per_item"] = prompts_per_item
                filtered_items.append(next_item)
            filtered[key] = filtered_items

        new_asset_count = sum(len(items) for items in filtered.values())
        has_assets_to_generate = new_asset_count > 0
        generation_summary = {
            "total_asset_count": total_asset_count,
            "new_asset_count": new_asset_count,
            "matched_asset_count": matched_asset_count,
            "has_assets_to_generate": has_assets_to_generate,
        }
        return NodeResult(
            status="succeeded",
            output={
                "approved_assets": filtered,
                "asset_count": new_asset_count,
                "new_asset_count": new_asset_count,
                "matched_asset_count": matched_asset_count,
                "has_assets_to_generate": has_assets_to_generate,
                "generation_summary": generation_summary,
            },
        )


def _is_existing_asset(item: Mapping[str, Any]) -> bool:
    if item.get("matched") is not True:
        return False
    for key in ("matched_asset_id", "matched_asset_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _with_target_appearance_description(item: dict[str, Any]) -> dict[str, Any]:
    is_character = _asset_type(item) == "character"
    existing = _optional_text(item.get("target_appearance_description"))
    if existing:
        item["target_appearance_description"] = _clean_target_appearance_description(existing, is_character)
        return item
    for key in ("appearance_description", "description"):
        value = _optional_text(item.get(key))
        if value:
            item["target_appearance_description"] = _clean_target_appearance_description(value, is_character)
            return item
    for key in ("asset_name", "name"):
        value = _optional_text(item.get(key))
        if value:
            item["target_appearance_description"] = value
            return item
    return item


def _asset_type(item: Mapping[str, Any]) -> str:
    for key in ("asset_type", "type"):
        value = _optional_text(item.get(key))
        if value:
            return value
    return ""


_LOWER_BODY_PATTERN = re.compile(r"下半身|下肢|腿|脚|足部|鞋|靴|裤|下装|裙摆|膝|踝|四肢|球形整体")


def _clean_target_appearance_description(value: str, is_character: bool) -> str:
    if not is_character:
        return value

    parts = re.split(r"([，,；;。！？!?])", value)
    kept: list[str] = []
    for index in range(0, len(parts), 2):
        text = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        if not text.strip() or _LOWER_BODY_PATTERN.search(text):
            continue
        kept.append(text.strip() + separator)

    cleaned = "".join(kept).strip(" ，,；;。！？!?")
    return cleaned or "角色头面与上身外貌待补充。"


async def _with_reference_context(
    ctx: NodeContext | None,
    item: dict[str, Any],
) -> dict[str, Any]:
    item = _with_reference_image_ref(item)
    if not _optional_text(item.get("reference_appearance_description")):
        description = _reference_appearance_description(item)
        if not description:
            description = await _reference_appearance_description_from_ref(ctx, item.get("reference_image_ref"))
        if description:
            item["reference_appearance_description"] = description
    return item


def _with_reference_image_ref(item: dict[str, Any]) -> dict[str, Any]:
    if _valid_image_ref(item.get("reference_image_ref")):
        item["reference_image_ref"] = _clean_image_ref(item["reference_image_ref"])
        return item
    for key in ("matched_asset_ref", "default_asset_ref"):
        value = item.get(key)
        if _valid_image_ref(value):
            item["reference_image_ref"] = _clean_image_ref(value)
            return item
    for key in ("asset_id", "matched_asset_id", "default_asset_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            item["reference_image_ref"] = {"kind": "asset", "asset_id": value.strip(), "role": "reference"}
            return item
    return item


def _valid_image_ref(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    kind = value.get("kind")
    if kind == "asset":
        asset_id = value.get("asset_id")
        return isinstance(asset_id, str) and bool(asset_id.strip())
    if kind == "data_uri":
        data = value.get("data")
        return isinstance(data, str) and data.startswith("data:image/")
    return False


def _clean_image_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key in ("kind", "asset_id", "data", "role"):
        text = _optional_text(value.get(key))
        if text:
            result[key] = text
    return result


def _reference_appearance_description(item: Mapping[str, Any]) -> str | None:
    for key in (
        "matched_asset_appearance_description",
        "reference_appearance_description",
        "default_asset_appearance_description",
    ):
        value = _optional_text(item.get(key))
        if value:
            return value
    reference = item.get("reference_image_ref")
    if isinstance(reference, Mapping):
        value = _optional_text(reference.get("appearance_description"))
        if value:
            return value
    return None


async def _reference_appearance_description_from_ref(ctx: NodeContext | None, image_ref: Any) -> str | None:
    if ctx is None or ctx.asset_service is None or not isinstance(image_ref, Mapping):
        return None
    if image_ref.get("kind") != "asset":
        return None
    asset_id = _optional_text(image_ref.get("asset_id"))
    if not asset_id:
        return None
    try:
        asset = await ctx.asset_service.get_asset(
            user_id=ctx.user_id,
            asset_id=asset_id,
            project_id=ctx.project_id,
        )
    except Exception:
        return None
    return _asset_appearance_description(asset)


def _asset_appearance_description(asset: Any) -> str | None:
    metadata: Any
    if isinstance(asset, Mapping):
        metadata = asset.get("metadata")
    else:
        metadata = getattr(asset, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    return _optional_text(metadata.get("appearance_description"))


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _bounded_int(value: Any, *, fallback: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return fallback
    parsed = value if isinstance(value, int) else fallback
    return max(minimum, min(maximum, parsed))
