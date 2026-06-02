from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


class PrepareAssetSemanticMatchNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.prepare_asset_semantic_match.v1",
            name="Prepare Asset Semantic Match",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "candidates": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "default_asset_type": {"type": "string"},
                },
                "required": ["items", "candidates"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "candidates": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["items", "candidates"],
                "additionalProperties": False,
            },
            description="为地点/道具语义匹配裁剪输入字段，只保留名称、标签和描述，候选额外保留 asset_id 用于回填。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        items = inputs.get("items")
        candidates = inputs.get("candidates")
        if not isinstance(items, list):
            raise ValidationError(
                code="prepare_asset_semantic_match_invalid_items",
                message="items must be an array",
            )
        if not isinstance(candidates, list):
            raise ValidationError(
                code="prepare_asset_semantic_match_invalid_candidates",
                message="candidates must be an array",
            )
        default_asset_type = _text(inputs.get("default_asset_type"))
        return NodeResult(
            status="succeeded",
            output={
                "items": [
                    _compact_record(item, default_asset_type=default_asset_type, include_asset_id=False)
                    for item in items
                    if isinstance(item, Mapping)
                ],
                "candidates": [
                    _compact_record(item, default_asset_type=default_asset_type, include_asset_id=True)
                    for item in candidates
                    if isinstance(item, Mapping)
                ],
            },
        )


def _compact_record(
    value: Mapping[str, Any],
    *,
    default_asset_type: str | None,
    include_asset_id: bool,
) -> dict[str, Any]:
    normalized = normalize_asset_record(value, default_asset_type=default_asset_type)
    result: dict[str, Any] = {}
    if include_asset_id:
        asset_id = _text(value.get("asset_id"))
        if asset_id:
            result["asset_id"] = asset_id
    for key in ("asset_type", "asset_name"):
        item = normalized.get(key)
        if item:
            result[key] = item
    asset_tags = normalized.get("asset_tags")
    result["asset_tags"] = asset_tags if isinstance(asset_tags, list) else []
    description = _description(value)
    if description:
        result["description"] = description
    return result


def _description(value: Mapping[str, Any]) -> str:
    for key in ("description", "appearance_description", "text_content"):
        item = _text(value.get(key))
        if item:
            return item
    metadata = value.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("description", "appearance_description", "prompt"):
            item = _text(metadata.get(key))
            if item:
                return item
    return ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""
