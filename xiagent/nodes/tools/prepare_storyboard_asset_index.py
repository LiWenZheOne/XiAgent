from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


class PrepareStoryboardAssetIndexNode(BaseNode):
    """把完整集资产目录压缩为分镜资产判断用的轻量名称索引。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.prepare_storyboard_asset_index.v1",
            name="Prepare Storyboard Asset Index",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["asset_catalog"],
                "properties": {
                    "asset_catalog": {"type": "object", "additionalProperties": True},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["asset_index"],
                "properties": {
                    "asset_index": {
                        "type": "object",
                        "required": ["characters", "locations", "props"],
                        "properties": {
                            "characters": {"type": "array", "items": _asset_index_item_schema()},
                            "locations": {"type": "array", "items": _asset_index_item_schema()},
                            "props": {"type": "array", "items": _asset_index_item_schema()},
                        },
                        "additionalProperties": False,
                    }
                },
                "additionalProperties": False,
            },
            description="从完整集资产目录中提取角色、地点和道具名称，供分镜资产在场判断使用。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        _ = ctx
        catalog = _mapping(inputs.get("asset_catalog"))
        source = _mapping(catalog.get("approved_assets")) or catalog
        output = {
            "characters": _items(source.get("characters"), default_asset_type="character"),
            "locations": _items(source.get("assets"), default_asset_type="scene"),
            "props": _items(source.get("props"), default_asset_type="prop"),
        }
        return NodeResult(status="succeeded", output={"asset_index": output})


def _asset_index_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["asset_name"],
        "properties": {
            "asset_name": {"type": "string", "minLength": 1},
            "asset_type": {"type": "string", "minLength": 1},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "description": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _items(value: Any, *, default_asset_type: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        normalized = normalize_asset_record(item, default_asset_type=default_asset_type)
        asset_name = _text(normalized.get("asset_name"))
        if not asset_name:
            continue
        asset_type = _text(normalized.get("asset_type")) or default_asset_type
        key = (asset_type, asset_name)
        if key in seen:
            continue
        seen.add(key)
        record: dict[str, Any] = {
            "asset_name": asset_name,
            "asset_type": asset_type,
        }
        aliases = _string_list(normalized.get("aliases"))
        if aliases:
            record["aliases"] = aliases
        summary = _text(normalized.get("summary"))
        if summary:
            record["summary"] = summary
        description = _text(normalized.get("description"))
        if description:
            record["description"] = description
        items.append(record)
    return items


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""
