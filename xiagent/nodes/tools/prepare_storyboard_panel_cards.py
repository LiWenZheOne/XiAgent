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

            description = _text(segment.get("description")) or "分镜画面"
            visible_characters = _present_character_names(assignment)
            reference_images = _reference_images(assignment, visible_characters=visible_characters)
            prompt = _assemble_prompt(
                description=description,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                generation_rules=generation_rules,
                reference_images=reference_images,
            )
            cards.append(
                {
                    "card_id": f"segment-{segment_index}",
                    "segment_index": segment_index,
                    "panel_index": 0,
                    "segment_title": segment_title,
                    "description": description,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "reference_images": reference_images,
                    "visible_characters": visible_characters,
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
    description: str,
    aspect_ratio: str,
    resolution: str,
    generation_rules: str,
    reference_images: list[Mapping[str, Any]],
) -> str:
    _ = aspect_ratio, resolution
    reference_context = _reference_context(reference_images)
    description = _description_with_reference_numbers(description, reference_images)
    parts = [
        f"画面风格约束\n{generation_rules}",
    ]
    if reference_context:
        parts.append(f"参考图对应关系\n{reference_context}")
    parts.extend(
        [
            f"分镜描述\n{description}",
        ]
    )
    return "\n\n".join(parts)


def _reference_context(reference_images: list[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for reference in reference_images:
        name = _text(reference.get("asset_name")) or _text(reference.get("label"))
        index = _int(reference.get("reference_index"), len(lines) + 1)
        if name:
            lines.append(f"- {name}：参考图{index}")
    return "\n".join(lines)


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
        "风格指令：参考《罗小黑战记》的线条、色彩逻辑和视觉质感生成高质量漫画。\n"
        "角色一致性：保持参考图人物比例、武器和关键服饰一致。\n"
        "时代背景：中国古代，以水浒传为背景。\n"
        "透视与构图：强纵深、前中后景分层、漫画分格画面。"
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


def _int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _normalise_name(value: str) -> str:
    return value.strip().casefold()
