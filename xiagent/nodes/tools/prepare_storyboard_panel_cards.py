from __future__ import annotations

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
            segment_context = _segment_context(assignment)
            source_item = items_by_index.get(segment_index, {})

            for panel_index, panel in enumerate(_object_list(segment.get("panels"))):
                description = _text(panel.get("description")) or "分镜画面"
                style = _text(panel.get("style")) or "高质量漫画分镜"
                constraints = _text(panel.get("constraints")) or "保持角色、服装、道具和场景连续性。"
                visible_characters = _visible_character_names(panel.get("visible_characters"))
                reference_images = _reference_images(assignment, visible_characters=visible_characters)
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
            "style",
            "constraints",
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
            "style": {"type": "string", "minLength": 1},
            "constraints": {"type": "string", "minLength": 1},
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
                "source": "asset",
            }
            asset_tags = _string_list(normalized.get("asset_tags"))
            if asset_tags:
                item["asset_tags"] = asset_tags
            image_url = _text(character.get("image_url"))
            if image_url:
                item["preview_url"] = image_url
            references.append(item)
    return references


def _visible_character_names(value: Any) -> list[str]:
    return _string_list(value)


def _segment_context(assignment: Mapping[str, Any]) -> str:
    parts: list[str] = []
    characters = []
    for character in _object_list(assignment.get("characters")):
        name = _text(character.get("asset_name"))
        tags = _string_list(character.get("asset_tags"))
        if name:
            characters.append(f"{name}（{'、'.join(tags)}）" if tags else name)
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
