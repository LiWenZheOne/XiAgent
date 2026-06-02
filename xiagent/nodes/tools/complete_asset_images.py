from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


class CompleteAssetImagesNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.complete_asset_images.v1",
            name="Complete Asset Images",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "prompt_results": {"type": "array"},
                    "manual_images": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "object", "additionalProperties": True},
                            ]
                        },
                    },
                    "auto_images": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "target_asset_name": {"type": "string"},
                },
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "required": ["asset_images", "missing_prompt_results", "missing_count", "next_action"],
                "properties": {
                    "asset_images": {"type": "array"},
                    "missing_prompt_results": {"type": "array"},
                    "missing_count": {"type": "integer", "minimum": 0},
                    "next_action": {"type": "string", "enum": ["finish", "generate_missing"]},
                },
                "additionalProperties": False,
            },
            description="Combine uploaded asset images with generated images and keep prompts only for missing assets.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        prompt_results = _dict_list(inputs.get("prompt_results"))
        manual_images = _manual_images(inputs.get("manual_images"), prompt_results)
        auto_images = _dict_list(inputs.get("auto_images"))
        target_asset_name = _optional_text(inputs.get("target_asset_name"))
        uploaded_keys = {
            key
            for image in manual_images
            for key in [_asset_identity_key(image)]
        }
        uploaded_keys.discard("")
        uploaded_count = len(uploaded_keys) if uploaded_keys else len(manual_images)
        if target_asset_name:
            missing_prompt_results = [
                item
                for item in prompt_results
                if _prompt_matches_target(item, target_asset_name)
            ]
        else:
            missing_prompt_results = [
                item
                for index, item in enumerate(prompt_results)
                if not _prompt_has_image(item, index, uploaded_keys, uploaded_count)
            ]
        requested_generation = inputs.get("decision") == "generate_missing"
        next_action = "generate_missing" if requested_generation and missing_prompt_results else "finish"

        asset_images = [
            normalize_asset_record(image)
            for image in [*manual_images, *auto_images]
        ]

        return NodeResult(
            status="succeeded",
            output={
                "asset_images": asset_images,
                "missing_prompt_results": missing_prompt_results,
                "missing_count": len(missing_prompt_results),
                "next_action": next_action,
            },
        )


def _manual_images(value: Any, prompt_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        images: list[dict[str, Any]] = []
        for index, image_url in enumerate(value):
            clean_url = image_url.strip()
            if not clean_url:
                continue
            prompt = prompt_results[index] if index < len(prompt_results) else {}
            normalized_prompt = normalize_asset_record(prompt)
            asset_name = _optional_text(normalized_prompt.get("asset_name")) or f"手动上传{index + 1}"
            image: dict[str, Any] = {
                "asset_name": asset_name,
                "image_url": clean_url,
                "source": "manual_upload",
            }
            for key in ("asset_type", "asset_name", "asset_tags"):
                value = normalized_prompt.get(key)
                if value:
                    image[key] = value
            images.append(image)
        return images
    return [
        item
        for item in _dict_list(value)
        if isinstance(item.get("image_url"), str) and item["image_url"].strip()
    ]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _asset_identity_key(image: Mapping[str, Any]) -> str:
    normalized = normalize_asset_record(image)
    asset_type = normalized.get("asset_type") or image.get("asset_type")
    name = normalized.get("asset_name")
    tags = normalized.get("asset_tags")
    if isinstance(asset_type, str) and asset_type.strip() and isinstance(name, str) and name.strip():
        tag_suffix = "|".join(tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()) if isinstance(tags, list) else ""
        return f"{asset_type.strip()}:{name.strip()}:{tag_suffix}"
    return name.strip() if isinstance(name, str) and name.strip() else ""


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _prompt_key(prompt: Mapping[str, Any]) -> str:
    normalized = normalize_asset_record(prompt)
    asset_type = normalized.get("asset_type") or prompt.get("asset_type")
    name = normalized.get("asset_name")
    tags = normalized.get("asset_tags")
    if isinstance(asset_type, str) and asset_type.strip() and isinstance(name, str) and name.strip():
        tag_suffix = "|".join(tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()) if isinstance(tags, list) else ""
        return f"{asset_type.strip()}:{name.strip()}:{tag_suffix}"
    return name.strip() if isinstance(name, str) and name.strip() else ""


def _prompt_matches_target(prompt: Mapping[str, Any], target_asset_name: str) -> bool:
    target = target_asset_name.strip()
    if not target:
        return False
    normalized = normalize_asset_record(prompt)
    return normalized.get("asset_name") == target or _prompt_key(prompt) == target


def _prompt_has_image(
    prompt: Mapping[str, Any],
    index: int,
    uploaded_keys: set[str],
    uploaded_count: int,
) -> bool:
    key = _prompt_key(prompt)
    if key and uploaded_keys:
        return key in uploaded_keys
    return index < uploaded_count
