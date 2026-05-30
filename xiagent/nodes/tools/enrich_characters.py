from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


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

        # Build lookup maps
        name_to_asset: dict[str, dict[str, Any]] = {}
        for asset in matched_by_name:
            if isinstance(asset, dict) and isinstance(asset.get("name"), str):
                name_to_asset[asset["name"]] = asset

        name_to_semantic: dict[str, dict[str, Any]] = {}
        for match in semantic_matches:
            if isinstance(match, dict) and isinstance(match.get("full_name"), str):
                name_to_semantic[match["full_name"]] = match

        # Build variant map from existing_assets using 4-level tags:
        # tags = ["角色", "林冲", "囚服", "佩刀"]
        #         L1     L2     L3    L4
        # L3 non-empty => variant; L3 empty => base image
        name_to_variants: dict[str, list[dict[str, Any]]] = {}
        for asset in existing_assets:
            if not isinstance(asset, dict):
                continue
            metadata = asset.get("metadata")
            if not isinstance(metadata, dict):
                continue
            tags = metadata.get("tags")
            if not isinstance(tags, list) or len(tags) < 2:
                continue
            # L1 = tags[0] (e.g. "角色"), L2 = tags[1] (e.g. "林冲")
            char_name = tags[1] if len(tags) > 1 else None
            if not isinstance(char_name, str) or not char_name:
                continue
            variant_tag = tags[2] if len(tags) > 2 else ""
            # Only include as variant if L3 is non-empty (skip base images)
            if isinstance(variant_tag, str) and variant_tag:
                variant_info: dict[str, Any] = {
                    "asset_id": asset.get("asset_id"),
                    "name": asset.get("name", ""),
                    "variant": variant_tag,
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
            full_name = char.get("full_name")
            if not isinstance(full_name, str) or not full_name.strip():
                continue

            result = dict(char)

            # 1. Exact match by name
            asset = name_to_asset.get(full_name)
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
                semantic = name_to_semantic.get(full_name)
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
            result["existing_variants"] = name_to_variants.get(full_name, [])

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


def _asset_image_ref(asset: Mapping[str, Any]) -> dict[str, Any] | None:
    asset_id = asset.get("asset_id") or asset.get("matched_asset_id")
    if isinstance(asset_id, str) and asset_id.strip():
        return {"kind": "asset", "asset_id": asset_id.strip(), "role": "reference"}
    return None


def _asset_appearance_description(asset: Mapping[str, Any]) -> str | None:
    for key in (
        "appearance_description",
        "visual_description",
        "variant_description",
        "description",
        "prompt",
        "text_content",
    ):
        value = asset.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = asset.get("metadata")
    if isinstance(metadata, Mapping):
        for key in (
            "appearance_description",
            "visual_description",
            "variant_description",
            "description",
            "prompt",
        ):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None
