from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.ai.image_references import image_refs_schema
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class PrepareStoryboardPanelCardsNode(BaseNode):
    """把逐段分镜描述和段落资产引用整理成 S8 分镜汇总卡片。"""

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.prepare_storyboard_panel_cards.v1",
            name="Prepare Storyboard Panel Cards",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["segment_descriptions", "segment_assignments"],
                "properties": {
                    "segment_descriptions": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "segment_assignments": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "storyboard_items": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "shared_context": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "generation_rules": {"type": "string"},
                    "negative_prompt": {"type": "string"},
                    "aspect_ratio": {"type": "string", "minLength": 1},
                    "resolution": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["panel_cards"],
                "properties": {
                    "panel_cards": {
                        "type": "array",
                        "items": _panel_card_schema(),
                    },
                    "storyboard_items": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "shared_context": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            description="为分镜汇总控件准备逐分格提示词、参考资产和重新生成提示词所需上下文。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        _ = ctx
        assignments = _assignments_by_index(inputs.get("segment_assignments"))
        items_by_index = _items_by_index(inputs.get("storyboard_items"))
        generation_rules = _text(inputs.get("generation_rules")) or _default_generation_rules()
        negative_prompt = _text(inputs.get("negative_prompt")) or _default_negative_prompt()
        aspect_ratio = _text(inputs.get("aspect_ratio")) or "16:9"
        resolution = _text(inputs.get("resolution")) or "2K"

        cards: list[dict[str, Any]] = []
        for segment in _object_list(inputs.get("segment_descriptions")):
            segment_index = _int(segment.get("index"), len(cards))
            segment_title = _text(segment.get("segment_title")) or f"段落 {segment_index + 1}"
            assignment = assignments.get(segment_index, {})
            reference_images = _reference_images(assignment)
            image_refs = [item["image_ref"] for item in reference_images if isinstance(item.get("image_ref"), Mapping)]
            references = _legacy_reference_assets(reference_images)
            segment_context = _segment_context(assignment)
            source_item = items_by_index.get(segment_index, {})

            for panel_index, panel in enumerate(_object_list(segment.get("panels"))):
                description = _text(panel.get("description")) or "分镜画面"
                style = _text(panel.get("style")) or "高质量漫画分镜"
                constraints = _text(panel.get("constraints")) or "保持角色、服装、道具和场景连续性。"
                prompt = _assemble_prompt(
                    description=description,
                    style=style,
                    constraints=constraints,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    generation_rules=generation_rules,
                    segment_context=segment_context,
                )
                cards.append(
                    {
                        "card_id": f"segment-{segment_index}-panel-{panel_index}",
                        "segment_index": segment_index,
                        "panel_index": panel_index,
                        "segment_title": segment_title,
                        "description": description,
                        "style": style,
                        "constraints": constraints,
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "reference_images": reference_images,
                        "image_refs": image_refs,
                        "reference_assets": references,
                        "aspect_ratio": aspect_ratio,
                        "resolution": resolution,
                        "source_item": source_item,
                    }
                )

        return NodeResult(
            status="succeeded",
            output={
                "panel_cards": cards,
                "storyboard_items": _object_list(inputs.get("storyboard_items")),
                "shared_context": _mapping(inputs.get("shared_context")),
            },
        )


def _panel_card_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "card_id",
            "segment_index",
            "panel_index",
            "segment_title",
            "description",
            "style",
            "constraints",
            "prompt",
            "image_refs",
            "reference_images",
            "reference_assets",
            "aspect_ratio",
            "resolution",
        ],
        "properties": {
            "card_id": {"type": "string", "minLength": 1},
            "segment_index": {"type": "integer", "minimum": 0},
            "panel_index": {"type": "integer", "minimum": 0},
            "segment_title": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
            "style": {"type": "string", "minLength": 1},
            "constraints": {"type": "string", "minLength": 1},
            "prompt": {"type": "string", "minLength": 1},
            "negative_prompt": {"type": "string"},
            "image_refs": image_refs_schema(),
            "reference_images": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["image_ref", "label", "source"],
                    "properties": {
                        "image_ref": image_refs_schema()["items"],
                        "label": {"type": "string", "minLength": 1},
                        "variant": {"type": "string"},
                        "source": {"type": "string", "enum": ["asset", "upload"]},
                        "preview_url": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "reference_assets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["full_name", "image_ref"],
                    "properties": {
                        "full_name": {"type": "string", "minLength": 1},
                        "variant": {"type": "string"},
                        "image_ref": image_refs_schema()["items"],
                        "image_url": {"type": "string"},
                        "source": {"type": "string", "enum": ["asset", "upload"]},
                    },
                    "additionalProperties": False,
                },
            },
            "aspect_ratio": {"type": "string", "minLength": 1},
            "resolution": {"type": "string", "minLength": 1},
            "source_item": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": False,
    }


def _assignments_by_index(value: Any) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for item in _object_list(value):
        index = item.get("segment_index")
        if isinstance(index, int) and not isinstance(index, bool):
            result[index] = item
    return result


def _items_by_index(value: Any) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for item in _object_list(value):
        index = item.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            result[index] = item
    return result


def _reference_images(assignment: Mapping[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for character in _object_list(assignment.get("characters")):
        image_ref = character.get("image_ref")
        name = _text(character.get("full_name"))
        if name and isinstance(image_ref, Mapping):
            item: dict[str, Any] = {
                "label": name,
                "image_ref": dict(image_ref),
                "source": "asset",
            }
            variant = _text(character.get("variant"))
            if variant:
                item["variant"] = variant
            image_url = _text(character.get("image_url"))
            if image_url:
                item["preview_url"] = image_url
            references.append(item)
    return references


def _legacy_reference_assets(reference_images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for image in reference_images:
        image_ref = image.get("image_ref")
        label = _text(image.get("label"))
        if not label or not isinstance(image_ref, Mapping):
            continue
        item: dict[str, Any] = {
            "full_name": label,
            "image_ref": dict(image_ref),
            "source": _text(image.get("source")) or "asset",
        }
        variant = _text(image.get("variant"))
        if variant:
            item["variant"] = variant
        preview_url = _text(image.get("preview_url"))
        if preview_url:
            item["image_url"] = preview_url
        references.append(item)
    return references


def _segment_context(assignment: Mapping[str, Any]) -> str:
    parts: list[str] = []
    characters = []
    for character in _object_list(assignment.get("characters")):
        name = _text(character.get("full_name"))
        variant = _text(character.get("variant"))
        if name:
            characters.append(f"{name}（{variant}）" if variant else name)
    if characters:
        parts.append(f"出场角色：{'、'.join(characters)}")
    location = _text(assignment.get("location"))
    if location:
        parts.append(f"地点：{location}")
    key_props = [_text(item) for item in _list(assignment.get("key_props"))]
    key_props = [item for item in key_props if item]
    if key_props:
        parts.append(f"关键道具：{'、'.join(key_props)}")
    return "\n- ".join(parts)


def _assemble_prompt(
    *,
    description: str,
    style: str,
    constraints: str,
    aspect_ratio: str,
    resolution: str,
    generation_rules: str,
    segment_context: str,
) -> str:
    parts = [
        f"分镜描述\n{description}",
        f"画风\n{style}",
        f"额外约束\n{constraints}",
        "固定图像生成规则\n"
        f"- 画幅比例：{aspect_ratio}\n"
        f"- 输出清晰度：{resolution}\n"
        "- 严格参考输入图片中的角色、服装、道具和场景一致性。\n"
        "- 不要在画面中添加文字、字幕、水印或无关标识。",
        f"补充生成规则\n{generation_rules}",
    ]
    if segment_context:
        parts.append(f"在场资产约束\n- {segment_context}")
    return "\n\n".join(parts)


def _default_generation_rules() -> str:
    return (
        "风格指令：参考《罗小黑战记》的线条、色彩逻辑和视觉质感生成高质量漫画。\n"
        "角色一致性：保持参考图人物比例、武器和关键服饰一致。\n"
        "时代背景：中国古代，以水浒传为背景。\n"
        "透视与构图：强纵深、前中后景分层、漫画分格画面。"
    )


def _default_negative_prompt() -> str:
    return "low quality, bad anatomy, worst quality, text, watermark, signature, realistic, legs, feet, shoes"


def _object_list(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback
