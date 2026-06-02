from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


class ResolveCharacterVariantRefsNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.resolve_character_variant_refs.v1",
            name="Resolve Character Variant References",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "characters": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "variant_results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["characters", "variant_results"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["results"],
                "additionalProperties": False,
            },
            description="程序化继承角色变体参考图事实字段，避免由 LLM 生成或改写。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        characters = inputs.get("characters")
        variant_results = inputs.get("variant_results")
        if not isinstance(characters, list):
            raise ValidationError(
                code="resolve_character_variant_refs_invalid_input",
                message="characters must be an array",
            )
        if not isinstance(variant_results, list):
            raise ValidationError(
                code="resolve_character_variant_refs_invalid_input",
                message="variant_results must be an array",
            )

        variants_by_name = {
            name: _variant_items(character.get("existing_variants"))
            for character in characters
            if isinstance(character, Mapping)
            for name in [
                _text(normalize_asset_record(character, default_asset_type="character").get("asset_name"))
            ]
            if name
        }

        results: list[dict[str, Any]] = []
        for item in variant_results:
            if not isinstance(item, Mapping):
                continue
            result = normalize_asset_record(item, default_asset_type="character")
            asset_name = _text(result.get("asset_name")) or ""
            variants = variants_by_name.get(asset_name, [])
            matched_asset = _find_matched_asset(
                variants,
                asset_id=_text(result.get("matched_asset_id")),
                asset_tags=_string_list(result.get("asset_tags")),
            )
            default_asset = _find_default_asset(variants)

            if matched_asset is not None:
                matched_id = _text(matched_asset.get("asset_id"))
                if matched_id:
                    result["matched_asset_id"] = matched_id
                    result["matched_asset_ref"] = {"kind": "asset", "asset_id": matched_id, "role": "reference"}
                matched_description = _appearance_description(matched_asset)
                result["matched_asset_appearance_description"] = matched_description or ""
            else:
                result["matched_asset_appearance_description"] = ""

            if default_asset is not None:
                result["default_asset_status"] = _asset_status(default_asset) or ""
                result["default_asset_storage_uri"] = _asset_image_url(default_asset) or ""
                result["default_asset_appearance_description"] = _appearance_description(default_asset) or ""
            else:
                result["default_asset_status"] = ""
                result["default_asset_storage_uri"] = ""
                result["default_asset_appearance_description"] = ""

            results.append(result)

        return NodeResult(status="succeeded", output={"results": results})


def _variant_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _find_matched_asset(
    variants: list[Mapping[str, Any]],
    *,
    asset_id: str | None,
    asset_tags: list[str],
) -> Mapping[str, Any] | None:
    if asset_id:
        for variant in variants:
            if _text(variant.get("asset_id")) == asset_id:
                return variant
    required = {_normalize(tag) for tag in asset_tags if tag}
    if required:
        for variant in variants:
            existing = {_normalize(tag) for tag in _string_list(variant.get("asset_tags"))}
            if required.issubset(existing):
                return variant
    return None


def _find_default_asset(variants: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not variants:
        return None
    for variant in variants:
        tags = {_normalize(tag) for tag in _string_list(variant.get("asset_tags"))}
        if tags & {"默认", "基础"}:
            return variant
    return variants[0]


def _asset_status(variant: Mapping[str, Any]) -> str | None:
    for key in ("status", "variant_status", "character_status", "summary"):
        value = _text(variant.get(key))
        if value:
            return value
    metadata = variant.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("status", "variant_status", "character_status", "summary"):
            value = _text(metadata.get(key))
            if value:
                return value
    return None


def _asset_image_url(variant: Mapping[str, Any]) -> str | None:
    for key in ("storage_uri", "image_url", "public_url"):
        value = _text(variant.get(key))
        if value:
            return value
    metadata = variant.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("storage_uri", "image_url", "public_url"):
            value = _text(metadata.get(key))
            if value:
                return value
        object_storage = metadata.get("object_storage")
        if isinstance(object_storage, Mapping):
            return _text(object_storage.get("public_url"))
    return None


def _appearance_description(variant: Mapping[str, Any]) -> str | None:
    for key in ("appearance_description", "visual_description", "variant_description", "description", "prompt"):
        value = _text(variant.get(key))
        if value:
            return value
    metadata = variant.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("appearance_description", "visual_description", "variant_description", "description", "prompt"):
            value = _text(metadata.get(key))
            if value:
                return value
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""
