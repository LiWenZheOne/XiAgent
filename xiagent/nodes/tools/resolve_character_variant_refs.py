from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


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
            for name in [_text(character.get("full_name")) or _text(character.get("name"))]
            if name
        }

        results: list[dict[str, Any]] = []
        for item in variant_results:
            if not isinstance(item, Mapping):
                continue
            result = dict(item)
            full_name = _text(result.get("full_name")) or ""
            variants = variants_by_name.get(full_name, [])
            matched_variant = _find_matched_variant(
                variants,
                variant_id=_text(result.get("matched_variant_id")),
                variant_name=_text(result.get("matched_variant")),
            )
            default_variant = _find_default_variant(variants)

            if matched_variant is not None:
                matched_id = _text(matched_variant.get("asset_id"))
                if matched_id:
                    result["matched_variant_id"] = matched_id
                matched_description = _appearance_description(matched_variant)
                result["matched_variant_appearance_description"] = matched_description or ""
            else:
                result["matched_variant_appearance_description"] = ""

            if default_variant is not None:
                result["default_variant_status"] = _variant_status(default_variant) or ""
                result["default_variant_storage_uri"] = _variant_image_url(default_variant) or ""
                result["default_variant_appearance_description"] = _appearance_description(default_variant) or ""
            else:
                result["default_variant_status"] = ""
                result["default_variant_storage_uri"] = ""
                result["default_variant_appearance_description"] = ""

            results.append(result)

        return NodeResult(status="succeeded", output={"results": results})


def _variant_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _find_matched_variant(
    variants: list[Mapping[str, Any]],
    *,
    variant_id: str | None,
    variant_name: str | None,
) -> Mapping[str, Any] | None:
    if variant_id:
        for variant in variants:
            if _text(variant.get("asset_id")) == variant_id:
                return variant
    if variant_name:
        normalized = _normalize(variant_name)
        for variant in variants:
            if _normalize(_text(variant.get("variant"))) == normalized:
                return variant
            if _normalize(_text(variant.get("name"))) == normalized:
                return variant
    return None


def _find_default_variant(variants: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not variants:
        return None
    for variant in variants:
        text = _normalize(_text(variant.get("variant")) or _text(variant.get("name")))
        if text in {"默认", "默认变体", "基础", "基础变体"}:
            return variant
    return None


def _variant_status(variant: Mapping[str, Any]) -> str | None:
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


def _variant_image_url(variant: Mapping[str, Any]) -> str | None:
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


def _normalize(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""
