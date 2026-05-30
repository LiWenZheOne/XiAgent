from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.ai.image_references import image_refs_schema
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class StoryboardPromptAssemblerNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.storyboard_prompt_assembler.v1",
            name="Storyboard Prompt Assembler",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "minLength": 1},
                    "style": {"type": "string", "minLength": 1},
                    "constraints": {"type": "string", "minLength": 1},
                    "generation_rules": {"type": "string", "minLength": 1},
                    "negative_prompt": {"type": "string", "minLength": 1},
                    "image_refs": image_refs_schema(),
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "required": ["description", "style", "constraints", "image_refs"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "negative_prompt": {"type": "string", "minLength": 1},
                    "image_refs": image_refs_schema(),
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "required": ["prompt", "negative_prompt", "image_refs", "aspect_ratio", "resolution"],
                "additionalProperties": False,
            },
            description="Assemble a final image generation prompt for storyboard panels.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        description = _required_text(inputs, "description")
        style = _required_text(inputs, "style")
        constraints = _required_text(inputs, "constraints")
        image_refs = _image_refs(inputs)
        aspect_ratio = _optional_text(inputs, "aspect_ratio") or "16:9"
        resolution = _optional_text(inputs, "resolution") or "2K"
        generation_rules = _optional_text(inputs, "generation_rules")

        prompt = "\n\n".join(
            _prompt_parts(
                description=description,
                style=style,
                constraints=constraints,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                generation_rules=generation_rules,
            )
        )

        negative_prompt = _required_text(inputs, "negative_prompt")

        return NodeResult(
            status="succeeded",
            output={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "image_refs": image_refs,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
        )


class StoryboardPromptAssemblerNodeV2(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.storyboard_prompt_assembler.v2",
            name="Storyboard Prompt Assembler V2",
            version="2.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "minLength": 1},
                    "style": {"type": "string", "minLength": 1},
                    "constraints": {"type": "string", "minLength": 1},
                    "image_refs": image_refs_schema(),
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                    "generation_rules": {"type": "string", "minLength": 1},
                    "negative_prompt": {"type": "string", "minLength": 1},
                    "segment_context": {"type": "string"},
                    "manual_overrides": {
                        "type": "object",
                        "properties": {
                            "corrected_prompt": {"type": "string"},
                            "corrected_image_refs": image_refs_schema(),
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["description", "style", "constraints", "image_refs"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "image_refs": image_refs_schema(),
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "required": ["prompt", "image_refs", "aspect_ratio", "resolution"],
                "additionalProperties": False,
            },
            description="Assemble a final image generation prompt for storyboard panels (v2, no negative_prompt).",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        description = _required_text(inputs, "description")
        style = _required_text(inputs, "style")
        constraints = _required_text(inputs, "constraints")
        image_refs = _image_refs(inputs)
        aspect_ratio = _optional_text(inputs, "aspect_ratio") or "16:9"
        resolution = _optional_text(inputs, "resolution") or "2K"

        # Check manual overrides first
        manual_overrides: dict | None = inputs.get("manual_overrides")
        if isinstance(manual_overrides, dict) and manual_overrides.get("corrected_prompt"):
            prompt = manual_overrides["corrected_prompt"]
        else:
            prompt = "\n\n".join(
                _prompt_parts(
                    description=description,
                    style=style,
                    constraints=constraints,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    generation_rules=_optional_text(inputs, "generation_rules"),
                )
            )

        # Inject segment_context if present
        segment_context: str | None = _optional_text(inputs, "segment_context")
        if segment_context:
            prompt = f"{prompt}\n\n在场资产约束\n- {segment_context}"

        # Apply manual overrides for image_refs
        if isinstance(manual_overrides, dict):
            corrected = _optional_image_refs(manual_overrides.get("corrected_image_refs"))
            if corrected:
                image_refs = corrected

        return NodeResult(
            status="succeeded",
            output={
                "prompt": prompt,
                "image_refs": image_refs,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
        )


def _required_text(inputs: Mapping[str, Any], key: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            code=f"{key}_required",
            message=f"{key} cannot be empty",
        )
    return value.strip()


def _optional_text(inputs: Mapping[str, Any], key: str) -> str | None:
    value = inputs.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _prompt_parts(
    *,
    description: str,
    style: str,
    constraints: str,
    aspect_ratio: str,
    resolution: str,
    generation_rules: str | None,
) -> list[str]:
    parts = [
        f"分镜描述\n{description}",
        f"画风\n{style}",
        f"额外约束\n{constraints}",
        "固定图像生成规则\n"
        f"- 画幅比例：{aspect_ratio}\n"
        f"- 输出清晰度：{resolution}\n"
        "- 严格参考输入图片中的角色、服装、道具和场景一致性。\n"
        "- 不要在画面中添加文字、字幕、水印或无关标识。",
    ]
    if generation_rules is not None:
        parts.append(f"补充生成规则\n{generation_rules}")
    return parts


def _image_refs(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = inputs.get("image_refs")
    image_refs = _optional_image_refs(value)
    if not image_refs:
        raise ValidationError(
            code="image_refs_required",
            message="image_refs must include at least one image reference",
        )
    return image_refs


def _optional_image_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    image_refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        kind = item.get("kind")
        if kind == "asset":
            asset_id = item.get("asset_id")
            if isinstance(asset_id, str) and asset_id.strip():
                image_refs.append({"kind": "asset", "asset_id": asset_id.strip(), "role": _role(item)})
        elif kind == "data_uri":
            data = item.get("data")
            if isinstance(data, str) and data.startswith("data:image/"):
                image_refs.append({"kind": "data_uri", "data": data, "role": _role(item)})
    return image_refs


def _role(item: Mapping[str, Any]) -> str:
    role = item.get("role")
    return role.strip() if isinstance(role, str) and role.strip() else "reference"
