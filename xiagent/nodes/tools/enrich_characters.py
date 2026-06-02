from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


class EnrichCharactersNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.enrich_characters.v1",
            name="Enrich Characters",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "characters": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "matched_by_name": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "semantic_matches": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "existing_assets": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["characters"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "characters": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["characters"],
                "additionalProperties": False,
            },
            description="将精确匹配和语义匹配结果合并到角色对象中，纯程序化，不调用 LLM。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        characters = inputs.get("characters")
        if not isinstance(characters, list):
            raise ValidationError(
                code="enrich_characters_invalid_input",
                message="characters must be an array",
            )

        matched_by_name = inputs.get("matched_by_name") or []
        semantic_matches = inputs.get("semantic_matches") or []
        existing_assets = inputs.get("existing_assets") or []
        default_asset_type = _infer_default_asset_type(matched_by_name, existing_assets) or "character"

        # Build lookup maps
        name_to_asset: dict[str, dict[str, Any]] = {}
        typed_name_to_asset: dict[tuple[str, str], dict[str, Any]] = {}
        typed_name_to_assets: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for asset in matched_by_name:
            if not isinstance(asset, dict):
                continue
            if isinstance(asset.get("name"), str):
                name_to_asset[asset["name"]] = asset
            normalized_asset = normalize_asset_record(asset)
            asset_name = _text(normalized_asset.get("asset_name"))
            if asset_name:
                name_to_asset.setdefault(asset_name, asset)
                asset_type = _text(normalized_asset.get("asset_type"))
                if asset_type:
                    typed_name = (_normalize(asset_type), _normalize(asset_name))
                    typed_name_to_asset.setdefault(typed_name, asset)
                    typed_name_to_assets.setdefault(typed_name, []).append(asset)

        name_to_semantic: dict[str, dict[str, Any]] = {}
        for match in semantic_matches:
            if isinstance(match, dict) and isinstance(match.get("asset_name"), str):
                name_to_semantic[match["asset_name"]] = match

        # Build variant map from existing_assets using asset library tags:
        # tags = ["角色", "林冲", "囚服", "佩刀"]
        #         L1     L2     L3    L4
        # L3 non-empty => variant; L3 empty => base image
        name_to_variants: dict[str, list[dict[str, Any]]] = {}
        for asset in existing_assets:
            if not isinstance(asset, dict):
                continue
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            normalized_asset = normalize_asset_record(asset)
            tags = _asset_tags(normalized_asset)
            char_name = _text(normalized_asset.get("asset_name"))
            if not char_name:
                continue
            asset_type = _text(normalized_asset.get("asset_type"))
            if asset_type:
                typed_name = (_normalize(asset_type), _normalize(char_name))
                typed_name_to_asset.setdefault(typed_name, asset)
                typed_name_to_assets.setdefault(typed_name, []).append(asset)
            if tags:
                variant_info: dict[str, Any] = {
                    "asset_id": asset.get("asset_id"),
                    "name": asset.get("name", ""),
                    "asset_type": normalized_asset.get("asset_type"),
                    "asset_name": char_name,
                    "asset_tags": tags,
                    "metadata": metadata,
                }
                image_url = _asset_image_url(asset)
                if image_url:
                    variant_info["storage_uri"] = image_url
                    variant_info["image_url"] = image_url
                appearance_description = _asset_appearance_description(asset)
                if appearance_description:
                    variant_info["appearance_description"] = appearance_description
                name_to_variants.setdefault(char_name, []).append(variant_info)

        enriched: list[dict[str, Any]] = []
        for char in characters:
            if not isinstance(char, dict):
                continue
            result = normalize_asset_record(char, default_asset_type=default_asset_type)
            asset_name = result.get("asset_name")
            if not isinstance(asset_name, str) or not asset_name.strip():
                continue

            # 1. Match by fixed type/name and unordered tags, then by plain asset name.
            asset = None
            asset_type = _text(result.get("asset_type"))
            if asset_type:
                typed_name = (_normalize(asset_type), _normalize(asset_name))
                asset = _find_asset_by_tags(typed_name_to_assets.get(typed_name, []), _asset_tags(result))
                if asset is None and not _asset_tags(result):
                    asset = typed_name_to_asset.get(typed_name)
            if asset is None:
                asset = name_to_asset.get(asset_name)
            if asset is not None:
                result["matched"] = True
                result["matched_asset_id"] = asset.get("asset_id")
                result["matched_asset_name"] = asset.get("name", "")
                image_ref = _asset_image_ref(asset)
                if image_ref is not None:
                    result["matched_asset_ref"] = image_ref
                appearance_description = _asset_appearance_description(asset)
                if appearance_description:
                    result["matched_asset_appearance_description"] = appearance_description
                    result["reference_appearance_description"] = appearance_description
            else:
                # 2. Semantic match fallback
                semantic = name_to_semantic.get(asset_name)
                if semantic is not None and semantic.get("matched") is True:
                    result["matched"] = True
                    result["matched_asset_id"] = semantic.get("matched_asset_id")
                    result["matched_asset_name"] = semantic.get("matched_asset_name", "")
                    image_ref = _asset_image_ref(semantic)
                    if image_ref is not None:
                        result["matched_asset_ref"] = image_ref
                    appearance_description = _asset_appearance_description(semantic)
                    if appearance_description:
                        result["matched_asset_appearance_description"] = appearance_description
                        result["reference_appearance_description"] = appearance_description
                else:
                    result["matched"] = False
                    result["matched_asset_id"] = None
                    result["matched_asset_name"] = ""

            # 3. Variants from 4-level tags
            result["existing_variants"] = name_to_variants.get(asset_name, [])

            enriched.append(result)

        return NodeResult(
            status="succeeded",
            output={"characters": enriched},
        )


def _asset_image_url(asset: Mapping[str, Any]) -> str | None:
    for key in ("image_url", "public_url", "storage_uri"):
        value = asset.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = asset.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("image_url", "public_url", "storage_uri"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        object_storage = metadata.get("object_storage")
        if isinstance(object_storage, Mapping):
            value = object_storage.get("public_url")
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def _asset_tags(asset: Mapping[str, Any]) -> list[str]:
    asset_tags = asset.get("asset_tags")
    if isinstance(asset_tags, list):
        return [tag.strip() for tag in asset_tags if isinstance(tag, str) and tag.strip()]
    return []


def _infer_default_asset_type(*asset_groups: Any) -> str | None:
    for group in asset_groups:
        if not isinstance(group, list):
            continue
        for asset in group:
            if not isinstance(asset, dict):
                continue
            asset_type = _text(normalize_asset_record(asset).get("asset_type"))
            if asset_type:
                return asset_type
    return None


def _find_asset_by_tags(assets: list[dict[str, Any]], target_tags: list[str]) -> dict[str, Any] | None:
    if not assets:
        return None
    if not target_tags:
        return assets[0]

    target = _tag_atoms(target_tags)
    if not target:
        return assets[0]

    for asset in assets:
        candidate = _tag_atoms(_asset_tags(normalize_asset_record(asset)))
        if target.issubset(candidate):
            return asset
    return None


def _tag_atoms(tags: list[str]) -> set[str]:
    result: set[str] = set()
    for tag in tags:
        for part in tag.replace("，", "、").replace(",", "、").replace("/", "、").split("、"):
            clean = _normalize(part)
            if clean:
                result.add(clean)
    return result


def _asset_image_ref(asset: Mapping[str, Any]) -> dict[str, Any] | None:
    asset_id = asset.get("asset_id") or asset.get("matched_asset_id")
    if isinstance(asset_id, str) and asset_id.strip():
        return {"kind": "asset", "asset_id": asset_id.strip(), "role": "reference"}
    return None


def _asset_appearance_description(asset: Mapping[str, Any]) -> str | None:
    value = asset.get("appearance_description")
    if isinstance(value, str) and value.strip():
        return value.strip()

    metadata = asset.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get("appearance_description")
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize(value: str) -> str:
    return value.strip().lower()
