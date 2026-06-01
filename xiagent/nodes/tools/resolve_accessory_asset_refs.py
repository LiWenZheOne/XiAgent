from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class ResolveAccessoryAssetRefsNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.resolve_accessory_asset_refs.v1",
            name="Resolve Accessory Asset References",
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
                    "accessory_results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["characters", "variant_results", "accessory_results"],
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
            description="Resolve accessory match results to concrete asset refs with same-variant fallback.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        characters = inputs.get("characters")
        variant_results = inputs.get("variant_results")
        accessory_results = inputs.get("accessory_results")
        if not isinstance(characters, list):
            raise ValidationError(
                code="resolve_accessory_asset_refs_invalid_input",
                message="characters must be an array",
            )
        if not isinstance(variant_results, list):
            raise ValidationError(
                code="resolve_accessory_asset_refs_invalid_input",
                message="variant_results must be an array",
            )
        if not isinstance(accessory_results, list):
            raise ValidationError(
                code="resolve_accessory_asset_refs_invalid_input",
                message="accessory_results must be an array",
            )

        variants_by_name = {
            name: _variant_items(character.get("existing_variants"))
            for character in characters
            if isinstance(character, Mapping)
            for name in [_text(character.get("full_name")) or _text(character.get("name"))]
            if name
        }
        variant_result_by_name = {
            name: item
            for item in variant_results
            if isinstance(item, Mapping)
            for name in [_text(item.get("full_name")) or _text(item.get("name"))]
            if name
        }

        results: list[dict[str, Any]] = []
        for item in accessory_results:
            if not isinstance(item, Mapping):
                continue
            result = dict(item)
            full_name = _text(result.get("full_name")) or ""
            variants = variants_by_name.get(full_name, [])
            variant_result = variant_result_by_name.get(full_name, {})
            same_variant_assets = _same_variant_assets(variants, variant_result)
            fallback_asset = same_variant_assets[0] if same_variant_assets else None

            selected: list[dict[str, Any]] = []
            existing_accessories = _string_list(result.get("existing_accessories"))
            new_accessories = _string_list(result.get("new_accessories"))
            for accessory in existing_accessories:
                matched_asset = _find_accessory_asset(same_variant_assets, accessory)
                selected.append(
                    _selection(
                        accessory=accessory,
                        matched=True,
                        asset=matched_asset or fallback_asset,
                        source="matched_accessory" if matched_asset is not None else "first_variant_asset",
                    )
                )
            for accessory in new_accessories:
                selected.append(
                    _selection(
                        accessory=accessory,
                        matched=False,
                        asset=fallback_asset,
                        source="first_variant_asset",
                    )
                )

            result["selected_accessory_assets"] = selected
            results.append(result)

        return NodeResult(status="succeeded", output={"results": results})


def _variant_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _same_variant_assets(
    variants: list[Mapping[str, Any]],
    variant_result: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    matched_variant_id = _text(variant_result.get("matched_variant_id"))
    matched_variant = _text(variant_result.get("matched_variant"))
    if not matched_variant and matched_variant_id:
        for variant in variants:
            if _text(variant.get("asset_id")) == matched_variant_id:
                matched_variant = _text(variant.get("variant")) or _text(variant.get("name"))
                break
    normalized_variant = _normalize(matched_variant)
    if not normalized_variant:
        return variants
    return [
        variant
        for variant in variants
        if _normalize(_text(variant.get("variant")) or _text(variant.get("name"))) == normalized_variant
    ]


def _find_accessory_asset(variants: list[Mapping[str, Any]], accessory: str) -> Mapping[str, Any] | None:
    normalized = _normalize(accessory)
    for variant in variants:
        if normalized in {_normalize(value) for value in _accessory_labels(variant)}:
            return variant
    return None


def _accessory_labels(variant: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    tags = variant.get("tags")
    if isinstance(tags, list):
        labels.extend(tag for tag in tags[3:] if isinstance(tag, str) and tag.strip())
    for key in ("accessory", "accessories", "name"):
        value = variant.get(key)
        if isinstance(value, str) and value.strip():
            labels.append(value.strip())
        elif isinstance(value, list):
            labels.extend(item.strip() for item in value if isinstance(item, str) and item.strip())
    return labels


def _selection(
    *,
    accessory: str,
    matched: bool,
    asset: Mapping[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    asset_id = _text(asset.get("asset_id")) if asset is not None else None
    return {
        "accessory": accessory,
        "matched": matched,
        "asset_id": asset_id or "",
        "asset_name": (_text(asset.get("name")) if asset is not None else None) or "",
        "asset_ref": {"kind": "asset", "asset_id": asset_id, "role": "reference"} if asset_id else None,
        "storage_uri": _variant_image_url(asset) if asset is not None else "",
        "appearance_description": _appearance_description(asset) if asset is not None else "",
        "source": source,
    }


def _variant_image_url(variant: Mapping[str, Any]) -> str:
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
            return _text(object_storage.get("public_url")) or ""
    return ""


def _appearance_description(variant: Mapping[str, Any]) -> str:
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
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""
