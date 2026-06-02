from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


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
            for name in [
                _text(normalize_asset_record(character, default_asset_type="character").get("asset_name"))
                or _text(character.get("name"))
            ]
            if name
        }
        variant_result_by_name = {
            name: item
            for item in variant_results
            if isinstance(item, Mapping)
            for name in [
                _text(normalize_asset_record(item, default_asset_type="character").get("asset_name"))
                or _text(item.get("name"))
            ]
            if name
        }

        results: list[dict[str, Any]] = []
        for item in accessory_results:
            if not isinstance(item, Mapping):
                continue
            result = normalize_asset_record(item, default_asset_type="character")
            asset_name = _text(result.get("asset_name")) or ""
            variants = variants_by_name.get(asset_name, [])
            variant_result = variant_result_by_name.get(asset_name, {})
            same_variant_assets = _same_variant_assets(variants, variant_result)
            fallback_asset = same_variant_assets[0] if same_variant_assets else None

            selected: list[dict[str, Any]] = []
            existing_asset_tags = _string_list(result.get("existing_asset_tags"))
            new_asset_tags = _string_list(result.get("new_asset_tags"))
            for asset_tag in existing_asset_tags:
                matched_asset = _find_tag_asset(same_variant_assets, asset_tag)
                selected.append(
                    _selection(
                        asset_tag=asset_tag,
                        matched=True,
                        asset=matched_asset or fallback_asset,
                        source="matched_asset_tag" if matched_asset is not None else "first_variant_asset",
                    )
                )
            for asset_tag in new_asset_tags:
                selected.append(
                    _selection(
                        asset_tag=asset_tag,
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
    matched_asset_id = _text(variant_result.get("matched_asset_id"))
    matched_asset_tags = _string_list(variant_result.get("asset_tags"))
    matched_asset_tag = matched_asset_tags[0] if matched_asset_tags else ""
    if not matched_asset_tag and matched_asset_id:
        for variant in variants:
            if _text(variant.get("asset_id")) == matched_asset_id:
                variant_tags = _asset_tags(variant)
                matched_asset_tag = variant_tags[0] if variant_tags else _text(variant.get("name")) or ""
                break
    normalized_asset_tag = _normalize(matched_asset_tag)
    if not normalized_asset_tag:
        return variants
    return [
        variant
        for variant in variants
        if normalized_asset_tag in {_normalize(value) for value in _asset_tags(variant)}
    ]


def _find_tag_asset(variants: list[Mapping[str, Any]], asset_tag: str) -> Mapping[str, Any] | None:
    normalized = _normalize(asset_tag)
    for variant in variants:
        if normalized in {_normalize(value) for value in _asset_tags(variant)}:
            return variant
    return None


def _selection(
    *,
    asset_tag: str,
    matched: bool,
    asset: Mapping[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    asset_id = _text(asset.get("asset_id")) if asset is not None else None
    return {
        "asset_tag": asset_tag,
        "matched": matched,
        "asset_id": asset_id or "",
        "asset_name": (_text(asset.get("name")) if asset is not None else None) or "",
        "asset_tags": _asset_tags(asset) if asset is not None else [],
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


def _asset_tags(asset: Mapping[str, Any]) -> list[str]:
    normalized = normalize_asset_record(asset, default_asset_type="character")
    tags = normalized.get("asset_tags")
    return [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []


def _appearance_description(variant: Mapping[str, Any]) -> str:
    value = _text(variant.get("appearance_description"))
    if value:
        return value
    metadata = variant.get("metadata")
    if isinstance(metadata, Mapping):
        value = _text(metadata.get("appearance_description"))
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
