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
                    "negative_prompt": {"type": "string", "minLength": 1},
                    "image_urls": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "required": ["prompt", "negative_prompt", "image_urls", "aspect_ratio", "resolution"],
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
                "风格指令\n"
                "参考《罗小黑战记》的线条、色彩逻辑和视觉质感生成高质量、细节丰富、富有张力的漫画。\n"
                "- 线条：典型的矢量图风格，干净且流畅，轮廓线利落。\n"
                "- 色彩：无复杂渐变，纯色块填充为主，阴影较浅，边缘锐利，阴影偏冷色调，软 cel shading。\n"
                "- 角色体型：所有角色都是胶囊形设计（达摩式 / 蛋形），下半身是个球，没有腿。\n"
                "- 透视：strict perspective with foreshortening，近大远小，强纵深（depth of field），layered foreground-midground-background composition。\n"
                "- 风格标签：digital illustration, chibi style, children's book art style, manhwa style, clean lineart, soft cel shading, vibrant colors, dynamic action atmosphere, masterpiece, best quality, 8k。",
                "角色一致性约束\n"
                "- 保持人物武器和参考完全一致。\n"
                "- 人物比例不变。\n"
                "- 所有角色为达摩/不倒翁体型：上半身正常比例，下半身为圆润饱满的半球形底部。\n"
                "- 完全没有腿部、没有膝盖、没有脚踝、没有足部。",
                "时代背景约束\n"
                "- 时代背景在中国古代，以水浒传为背景。\n"
                "- 根据时代背景和当前情景设计环境和物件。\n"
                "- 装饰和场景内的物体丰富，并与角色风格一致。",
                "透视与空间约束\n"
                "- 严格遵守近大远小的透视关系。\n"
                "- 透视线体现强烈的空间纵深感。\n"
                "- 前景遮挡感强烈。\n"
                "- 每个分格的消失点必须统一。\n"
                "- 多分格页面：采用不规则的梯形与矩形组合排版，打破平庸的视觉节奏。",
                "场景比例约束\n"
                "- 场景建筑比例符合 chibi style（不追求写实建筑比例）。",
            ]
        )

        negative_prompt = (
            "low quality, bad anatomy, worst quality, text, watermark, signature, "
            "ugly, bad proportions, deformed, realistic, gradient shading, complex textures, "
            "red lines, guidelines, nose, legs, feet, ankles, knees, thighs, calves, toes, "
            "footwear, shoes, boots, sandals, photorealistic, flat composition, no depth"
        )

        return NodeResult(
            status="succeeded",
            output={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
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
