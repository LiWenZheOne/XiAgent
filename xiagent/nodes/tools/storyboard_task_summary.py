from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class StoryboardTaskSummaryNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.storyboard_task_summary.v1",
            name="Storyboard Task Summary",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["panel_results"],
                "properties": {
                    "panel_results": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                },
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "required": ["asset_images", "generation_summary"],
                "properties": {
                    "asset_images": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "generation_summary": {
                        "type": "object",
                        "required": ["total_panel_count", "completed_panel_count", "missing_panel_count"],
                        "properties": {
                            "total_panel_count": {"type": "integer", "minimum": 0},
                            "completed_panel_count": {"type": "integer", "minimum": 0},
                            "missing_panel_count": {"type": "integer", "minimum": 0},
                            "failed_panels": {
                                "type": "array",
                                "items": {"type": "object", "additionalProperties": True},
                            },
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            description="Summarize reviewed storyboard panels into downloadable image records.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        panel_results = _records(inputs.get("panel_results"))
        asset_images = [_panel_asset_image(panel) for panel in panel_results]
        asset_images = [image for image in asset_images if image is not None]
        generation_summary = {
            "total_panel_count": len(panel_results),
            "completed_panel_count": len(asset_images),
            "missing_panel_count": max(len(panel_results) - len(asset_images), 0),
            "failed_panels": [_failed_panel(panel) for panel in panel_results if _panel_asset_image(panel) is None],
        }
        return NodeResult(
            status="succeeded",
            output={
                "asset_images": asset_images,
                "generation_summary": generation_summary,
            },
        )


def _panel_asset_image(panel: Mapping[str, Any]) -> dict[str, Any] | None:
    image_url = _text(panel.get("selected_image_url"))
    if image_url is None:
        return None
    segment_index = _int(panel.get("segment_index"), default=0)
    panel_index = _int(panel.get("panel_index"), default=0)
    segment_title = _text(panel.get("segment_title")) or f"第{segment_index + 1}段"
    panel_title = _text(panel.get("panel_title")) or _text(panel.get("title")) or f"第{panel_index + 1}格"
    selected_image = _selected_generated_image(panel, image_url)
    image: dict[str, Any] = {
        "asset_type": "storyboard",
        "asset_name": f"{segment_title}_{panel_title}",
        "asset_tags": ["分镜", f"第{segment_index + 1}段", f"第{panel_index + 1}格"],
        "image_url": image_url,
        "source": "storyboard_generated",
        "segment_index": segment_index,
        "panel_index": panel_index,
    }
    asset_id = _text(selected_image.get("asset_id")) if selected_image else None
    if asset_id:
        image["asset_id"] = asset_id
    return image


def _failed_panel(panel: Mapping[str, Any]) -> dict[str, Any]:
    segment_index = _int(panel.get("segment_index"), default=0)
    panel_index = _int(panel.get("panel_index"), default=0)
    failure = {
        "card_id": _text(panel.get("card_id")) or f"segment-{segment_index}-panel-{panel_index}",
        "segment_index": segment_index,
        "panel_index": panel_index,
        "segment_title": _text(panel.get("segment_title")) or f"第{segment_index + 1}段",
        "panel_title": _text(panel.get("panel_title")) or _text(panel.get("title")) or f"第{panel_index + 1}格",
        "reason": "missing_image",
    }
    error = _text(panel.get("error"))
    if error:
        failure["error"] = error
    return failure


def _selected_generated_image(panel: Mapping[str, Any], image_url: str) -> Mapping[str, Any] | None:
    for image in _records(panel.get("generated_images")):
        if _text(image.get("image_url")) == image_url:
            return image
    return None


def _records(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int(value: Any, *, default: int) -> int:
    return value if isinstance(value, int) and value >= 0 else default
