from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
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
                    "image_urls": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "required": ["description", "style", "constraints", "image_urls"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "image_urls": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "required": ["prompt", "image_urls", "aspect_ratio", "resolution"],
                "additionalProperties": False,
            },
            description="Assemble a final image generation prompt for storyboard panels.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        description = _required_text(inputs, "description")
        style = _required_text(inputs, "style")
        constraints = _required_text(inputs, "constraints")
        image_urls = _image_urls(inputs)
        aspect_ratio = _optional_text(inputs, "aspect_ratio") or "16:9"
        resolution = _optional_text(inputs, "resolution") or "2K"

        prompt = "\n\n".join(
            [
                f"分镜描述\n{description}",
                f"画风\n{style}",
                f"额外约束\n{constraints}",
                "固定图像生成规则\n"
                f"- 画幅比例：{aspect_ratio}\n"
                f"- 输出清晰度：{resolution}\n"
                "- 严格参考输入图片中的角色、服装、道具和场景一致性。\n"
                "- 不要在画面中添加文字、字幕、水印或无关标识。",
            ]
        )

        return NodeResult(
            status="succeeded",
            output={
                "prompt": prompt,
                "image_urls": image_urls,
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


def _image_urls(inputs: Mapping[str, Any]) -> list[str]:
    value = inputs.get("image_urls")
    if not isinstance(value, list):
        raise ValidationError(
            code="image_urls_required",
            message="image_urls must be an array",
        )
    image_urls = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if not image_urls:
        raise ValidationError(
            code="image_urls_required",
            message="image_urls must include at least one URL",
        )
    return image_urls
