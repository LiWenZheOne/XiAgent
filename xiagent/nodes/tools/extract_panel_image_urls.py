from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class ExtractPanelImageUrlsNode(BaseNode):
    """从段落在场资产中自动提取目标分格的 image_url 数组。

    接收 segment_asset_assignments（段落级资产分配）和 storyboard_target，
    定位目标段落，收集所有在场资产的 image_url，返回纯 URL 字符串数组。
    """

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.extract_panel_image_urls.v1",
            name="Extract Panel Image URLs",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "properties": {
                    "segment_asset_assignments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "segment_index": {
                                    "type": "integer",
                                    "minimum": 0,
                                },
                                "characters": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "asset_name": {"type": "string"},
                                            "asset_tags": {"type": "array", "items": {"type": "string"}},
                                            "image_url": {"type": "string"},
                                        },
                                        "required": ["asset_name", "image_url"],
                                        "additionalProperties": False,
                                    },
                                },
                                "key_props": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["segment_index", "characters"],
                            "additionalProperties": False,
                        },
                    },
                    "storyboard_target": {
                        "type": "object",
                        "properties": {
                            "segment_index": {
                                "type": "integer",
                                "minimum": 0,
                                "default": 0,
                            },
                            "panel_index": {
                                "type": "integer",
                                "minimum": 0,
                                "default": 0,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["segment_asset_assignments"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "target_segment": {"type": "integer", "minimum": 0},
                    "target_panel": {"type": "integer", "minimum": 0},
                },
                "required": ["image_urls", "target_segment", "target_panel"],
                "additionalProperties": False,
            },
            description="从段落在场资产中自动提取目标分格的 image_url 数组。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        segment_assignments = inputs.get("segment_asset_assignments")
        if not isinstance(segment_assignments, list) or not segment_assignments:
            raise ValidationError(
                code="invalid_segment_asset_assignments",
                message="segment_asset_assignments must be a non-empty array",
            )

        storyboard_target = inputs.get("storyboard_target", {})
        if not isinstance(storyboard_target, dict):
            storyboard_target = {}

        target_segment = storyboard_target.get("segment_index", 0)
        target_panel = storyboard_target.get("panel_index", 0)

        if not isinstance(target_segment, int) or target_segment < 0:
            target_segment = 0
        if not isinstance(target_panel, int) or target_panel < 0:
            target_panel = 0

        # Locate the target segment by segment_index
        found_segment: dict[str, Any] | None = None
        for seg in segment_assignments:
            if isinstance(seg, dict) and seg.get("segment_index") == target_segment:
                found_segment = seg
                break

        if found_segment is None:
            raise ValidationError(
                code="segment_not_found",
                message=(
                    f"Segment index {target_segment} not found "
                    f"in segment_asset_assignments"
                ),
            )

        # Extract image_url from each present_asset (characters array)
        present_assets = found_segment.get("characters", [])
        if not isinstance(present_assets, list) or not present_assets:
            raise ValidationError(
                code="empty_present_assets",
                message=(
                    f"No present assets found for segment {target_segment}"
                ),
            )

        image_urls: list[str] = []
        for asset in present_assets:
            if isinstance(asset, dict):
                url = asset.get("image_url")
                if isinstance(url, str) and url.strip():
                    image_urls.append(url.strip())

        if not image_urls:
            raise ValidationError(
                code="no_image_urls",
                message=(
                    f"No valid image_urls found in present assets "
                    f"for segment {target_segment}"
                ),
            )

        return NodeResult(
            status="succeeded",
            output={
                "image_urls": image_urls,
                "target_segment": target_segment,
                "target_panel": target_panel,
            },
        )
