from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


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
            source_item = items_by_index.get(segment_index, {})
            status = _text(segment.get("status")) or "ready"
            error = _error_text(segment.get("error"))

            image_prompt = _image_prompt_text(segment.get("image_prompt"))
            if status == "failed" and not image_prompt:
                image_prompt = "当前段落画面提示词生成失败，请重新生成提示词或手动编辑后再生成分镜图。"
            image_prompt = image_prompt or "分镜画面"
            description = image_prompt
            visible_characters = _present_character_names(assignment)
            reference_images = _reference_images(assignment, visible_characters=visible_characters)
            prompt = _assemble_prompt(
                image_prompt=image_prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                generation_rules=generation_rules,
                negative_prompt=negative_prompt,
                reference_images=reference_images,
            )
            cards.append(
                {
                    "card_id": f"segment-{segment_index}",
                    "segment_index": segment_index,
                    "panel_index": 0,
                    "segment_title": segment_title,
                    "description": description,
                    "image_prompt": image_prompt,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "reference_images": reference_images,
                    "visible_characters": visible_characters,
                    "aspect_ratio": aspect_ratio,
                    "resolution": resolution,
                    "source_item": source_item,
                    "status": status,
                    "error": error,
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
            "prompt",
            "reference_images",
            "aspect_ratio",
            "resolution",
        ],
        "properties": {
            "card_id": {"type": "string", "minLength": 1},
            "segment_index": {"type": "integer", "minimum": 0},
            "panel_index": {"type": "integer", "minimum": 0},
            "segment_title": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
            "image_prompt": {"type": "string", "minLength": 1},
            "prompt": {"type": "string", "minLength": 1},
            "negative_prompt": {"type": "string"},
            "reference_images": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["image_ref", "label", "source"],
                    "properties": {
                        "image_ref": _image_ref_schema(),
                        "label": {"type": "string", "minLength": 1},
                        "asset_type": {"type": "string", "minLength": 1},
                        "asset_name": {"type": "string", "minLength": 1},
                        "asset_tags": {"type": "array", "items": {"type": "string"}},
                        "reference_index": {"type": "integer", "minimum": 1},
                        "source": {"type": "string", "enum": ["asset", "upload"]},
                        "preview_url": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "visible_characters": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "aspect_ratio": {"type": "string", "minLength": 1},
            "resolution": {"type": "string", "minLength": 1},
            "source_item": {"type": "object", "additionalProperties": True},
            "status": {"type": "string"},
            "error": {"type": "string"},
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


def _reference_images(
    assignment: Mapping[str, Any],
    *,
    visible_characters: list[str],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    visible_names = {_normalise_name(name) for name in visible_characters}
    for character in _object_list(assignment.get("characters")):
        normalized = normalize_asset_record(character, default_asset_type="character")
        image_ref = character.get("image_ref")
        name = _text(normalized.get("asset_name"))
        if visible_names and _normalise_name(name) not in visible_names:
            continue
        if name and isinstance(image_ref, Mapping):
            item: dict[str, Any] = {
                "label": name,
                "asset_type": _text(normalized.get("asset_type")) or "character",
                "asset_name": name,
                "image_ref": dict(image_ref),
                "reference_index": len(references) + 1,
                "source": "asset",
            }
            asset_tags = _string_list(normalized.get("asset_tags"))
            if asset_tags:
                item["asset_tags"] = asset_tags
            image_url = _text(character.get("image_url"))
            if image_url:
                item["preview_url"] = image_url
            references.append(item)
    location_reference = _asset_reference(assignment.get("location_asset"), default_asset_type="scene", reference_index=len(references) + 1)
    if location_reference is not None:
        references.append(location_reference)
    for prop in _object_list(assignment.get("prop_assets")):
        prop_reference = _asset_reference(prop, default_asset_type="prop", reference_index=len(references) + 1)
        if prop_reference is not None:
            references.append(prop_reference)
    return references


def _asset_reference(value: Any, *, default_asset_type: str, reference_index: int) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    normalized = normalize_asset_record(value, default_asset_type=default_asset_type)
    image_ref = value.get("image_ref")
    name = _text(normalized.get("asset_name"))
    if not name or not isinstance(image_ref, Mapping):
        return None
    item: dict[str, Any] = {
        "label": name,
        "asset_type": _text(normalized.get("asset_type")) or default_asset_type,
        "asset_name": name,
        "image_ref": dict(image_ref),
        "reference_index": reference_index,
        "source": "asset",
    }
    asset_tags = _string_list(normalized.get("asset_tags"))
    if asset_tags:
        item["asset_tags"] = asset_tags
    image_url = _text(value.get("image_url"))
    if image_url:
        item["preview_url"] = image_url
    return item


def _present_character_names(assignment: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for character in _object_list(assignment.get("characters")):
        if _text(character.get("presence")) not in {"", "present"}:
            continue
        name = _text(character.get("asset_name"))
        if name:
            names.append(name)
    return names


def _assemble_prompt(
    *,
    image_prompt: str,
    aspect_ratio: str,
    resolution: str,
    generation_rules: str,
    negative_prompt: str,
    reference_images: list[Mapping[str, Any]],
) -> str:
    _ = aspect_ratio, resolution
    reference_context = _reference_context(reference_images)
    image_prompt = _description_with_reference_numbers(image_prompt, reference_images)
    style_text, requirement_text = _split_generation_rules(generation_rules)
    parts: list[str] = []
    if style_text:
        parts.append(f"画风：\n{style_text}")
    if reference_context:
        parts.append(f"参考图：\n{reference_context}")
    parts.append(f"画面：\n{image_prompt}")
    if requirement_text:
        parts.append(f"要求：\n{requirement_text}")
    if negative_prompt:
        parts.append(f"Negative Prompt： {negative_prompt}")
    return "\n\n".join(parts)


def _image_prompt_text(value: Any) -> str:
    return _text(value)


def _reference_context(reference_images: list[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for reference in reference_images:
        name = _text(reference.get("asset_name")) or _text(reference.get("label"))
        index = _int(reference.get("reference_index"), len(lines) + 1)
        if name:
            type_label = _reference_type_label(_text(reference.get("asset_type")))
            lines.append(f"图{index}是{type_label}{name}")
    return "\n".join(lines)


def _reference_type_label(asset_type: str) -> str:
    return {
        "character": "角色",
        "scene": "场景",
        "location": "场景",
        "prop": "道具",
    }.get(asset_type, "")


def _split_generation_rules(generation_rules: str) -> tuple[str, str]:
    style_lines: list[str] = []
    requirement_lines: list[str] = []
    for raw_line in generation_rules.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("风格指令："):
            style_lines.append(line.removeprefix("风格指令：").strip())
        elif line.startswith("画面风格关键词："):
            style_lines.append(line.removeprefix("画面风格关键词：").strip())
        elif line.startswith(("角色一致性：", "时代背景：", "透视与构图：", "场景建筑比例：")):
            requirement_lines.append(line.split("：", 1)[1].strip())
        else:
            style_lines.append(line)
    return "\n".join(style_lines).strip(), "\n".join(requirement_lines).strip()


def _description_with_reference_numbers(
    description: str,
    reference_images: list[Mapping[str, Any]],
) -> str:
    result = description
    references = sorted(
        [
            (
                _text(reference.get("asset_name")) or _text(reference.get("label")),
                _int(reference.get("reference_index"), index + 1),
                _text(reference.get("asset_type")),
            )
            for index, reference in enumerate(reference_images)
        ],
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for name, index, asset_type in references:
        if not name:
            continue
        result = _annotate_reference_name(
            result,
            name=name,
            reference_index=index,
            asset_type=asset_type,
        )
    return result


def _annotate_reference_name(
    text: str,
    *,
    name: str,
    reference_index: int,
    asset_type: str,
) -> str:
    pattern = re.compile(rf"{re.escape(name)}(?!（参考图\d+）)")
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        parts.append(text[cursor:match.start()])
        if asset_type == "character" and _inside_location_phrase(text, match.start(), match.end()):
            parts.append(match.group(0))
        else:
            parts.append(f"{match.group(0)}（参考图{reference_index}）")
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)


_LOCATION_SUFFIXES = (
    "庄院",
    "宅院",
    "院内",
    "村",
    "庄",
    "院",
    "宅",
    "府",
    "馆",
    "楼",
    "寺",
    "庙",
    "堂",
    "寨",
    "营",
    "城",
    "门",
    "街",
    "巷",
    "桥",
    "岸",
    "湖",
    "港",
    "泊",
    "岛",
    "山",
    "林",
    "屋",
    "房",
)


def _inside_location_phrase(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 6):start]
    suffix = text[end:end + 6]
    if any(suffix.startswith(item) for item in _LOCATION_SUFFIXES):
        return True
    if any(item in suffix for item in _LOCATION_SUFFIXES) and any(item in prefix for item in ("村", "庄", "府", "院", "宅", "寺", "庙", "店", "寨")):
        return True
    return False


def _default_generation_rules() -> str:
    return (
        "风格指令：请参考《罗小黑战记》的线条、色彩逻辑和视觉质感生成高质量，细节丰富，富有张力的漫画，线条是典型的矢量图风格，干净且流畅，色彩无复杂渐变，轮廓线利落，阴影较浅，边缘锐利，阴影偏冷色调，注意，所有角色都是胶囊形设计（达摩式 / 蛋形），下半身是个球，没有腿。strict perspective with foreshortening, near objects large far objects small, strong depth of field, layered foreground-midground-background composition. digital illustration, chibi style, children's book art style, manhwa style, clean lineart, soft cel shading, vibrant colors, dynamic action atmosphere, masterpiece, best quality, 8k\n"
        "角色一致性：保持人物武器和参考完全一致，人物比例不变，所有角色为达摩/不倒翁体型：上半身正常比例，下半身为圆润饱满的半球形底部，完全没有腿部、没有膝盖、没有脚踝、没有足部。\n"
        "时代背景：场景细节丰富，注意！时代背景在中国古代，以水浒传为背景，请根据时代背景和当前情景设计环境和物件，使装饰和场景内的物体丰富，并和角色风格一致。\n"
        "透视与构图：严格遵守近大远小的透视关系，透视线在体现强烈的空间纵深感，前景遮挡感强烈，注意，每个分格的消失点必须统一，如果有超过一个分格，分格应该采用不规则的梯形与矩形组合排版，打破平庸的视觉节奏。\n"
        "场景建筑比例：场景建筑比例也要符合 chibi style。"
    )


def _default_negative_prompt() -> str:
    return "low quality, bad anatomy, worst quality, text, watermark, signature, realistic, legs, feet, shoes"


def _image_ref_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["kind"],
        "properties": {
            "kind": {"type": "string", "enum": ["asset", "data_uri"]},
            "asset_id": {"type": "string", "minLength": 1},
            "data": {"type": "string", "minLength": 1},
            "role": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _object_list(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _error_text(value: Any) -> str:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, Mapping):
        message = _text(value.get("message"))
        code = _text(value.get("code"))
        if message and code:
            return f"{message}（{code}）"
        return message or code
    return ""


def _int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _normalise_name(value: str) -> str:
    return value.strip().casefold()
