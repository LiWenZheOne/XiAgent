from __future__ import annotations

import pytest

from xiagent.nodes.tools.merge_segment_storyboard_descriptions import (
    MergeSegmentStoryboardDescriptionsNode,
)
from xiagent.nodes.tools.prepare_segment_storyboard_inputs import (
    PrepareSegmentStoryboardInputsNode,
)


@pytest.mark.asyncio
async def test_prepare_segment_storyboard_inputs_builds_one_item_per_segment() -> None:
    node = PrepareSegmentStoryboardInputsNode()

    result = await node.run(
        None,
        {
            "source_script": "完整剧本",
            "world_background": "水浒世界，北宋末年。",
            "segments": [
                {"index": 0, "text": "第一段", "panel_hint": "1", "panel_count_min": 1, "panel_count_max": 1},
                {"index": 1, "text": "第二段", "panel_hint": "3-4", "panel_count_min": 3, "panel_count_max": 4},
                {"index": 2, "text": "第三段", "panel_hint": "1", "panel_count_min": 1, "panel_count_max": 1},
            ],
            "segment_assignments": [
                {
                    "segment_index": 1,
                    "characters": [
                        {
                            "asset_type": "character",
                            "asset_name": "林冲",
                            "asset_tags": ["囚服", "毡笠"],
                            "appearance_description": "戴毡笠、穿囚服。",
                            "presence": "present",
                            "visibility": "in_frame",
                            "reason": "本段正面描写林冲踏雪。",
                            "image_ref": {"kind": "asset", "asset_id": "asset-linchong"},
                            "image_url": "https://cdn.test/linchong.png",
                        }
                    ],
                    "key_props": ["花枪"],
                    "location": "野猪林",
                    "location_asset": {
                        "asset_type": "scene",
                        "asset_name": "野猪林",
                        "description": "雪地林道狭窄，两侧密林压迫，前景树干可遮挡视线。",
                        "image_ref": {"kind": "asset", "asset_id": "asset-forest"},
                    },
                },
            ],
            "storyboard_options": {"no_material": True, "enrich_description": True},
        },
    )

    assert result.status == "succeeded"
    items = result.output["items"]
    assert [item["index"] for item in items] == [0, 1, 2]
    assert items[1]["paragraph_text"] == "第二段"
    assert items[1]["panel_count"] == "3-4"
    assert "panel_count_instruction" not in items[1]
    assert items[1]["present_characters"] == ["林冲"]
    assert items[1]["location"] == "野猪林"
    assert items[1]["scene_description"] == "雪地林道狭窄，两侧密林压迫，前景树干可遮挡视线。"
    assert items[1]["key_props"] == ["花枪"]
    assert "current_segment" not in items[1]
    assert "neighbor_segments" not in items[1]
    assert items[1]["segment_assignment"] == {
        "segment_index": 1,
        "characters": [
                {
                    "asset_name": "林冲",
                    "asset_tags": ["囚服", "毡笠"],
                    "appearance_description": "戴毡笠、穿囚服。",
                    "presence": "present",
                }
        ],
        "key_props": ["花枪"],
        "location": "野猪林",
    }
    assert "full_script" not in items[1]
    assert "all_segments" not in items[1]
    assert result.output["shared_context"]["full_script"] == "完整剧本"
    assert result.output["shared_context"]["world_background"] == "水浒世界，北宋末年。"
    assert "all_segments" not in result.output["shared_context"]
    assert result.output["shared_context"]["storyboard_options"] == {
        "no_material": True,
        "enrich_description": True,
    }
    assert result.output["shared_context"]["prompt_rules"]["material_rule"].startswith(
        "- 删除所有材质和质感审查"
    )
    assert "额外落实" in result.output["shared_context"]["prompt_rules"]["enrich_rule"]
    assert "不讨论材质" in result.output["shared_context"]["prompt_rules"]["material_thinking"]
    assert "逐项补充遮挡物" in result.output["shared_context"]["prompt_rules"]["enrich_thinking"]


@pytest.mark.asyncio
async def test_prepare_segment_storyboard_inputs_defaults_storyboard_options() -> None:
    node = PrepareSegmentStoryboardInputsNode()

    result = await node.run(
        None,
        {
            "source_script": "完整剧本",
            "segments": [{"index": 0, "text": "第一段"}],
            "segment_assignments": [{"segment_index": 0, "characters": [], "key_props": []}],
        },
    )

    assert result.output["shared_context"]["storyboard_options"] == {
        "no_material": False,
        "enrich_description": False,
    }
    assert "可以描述对画面叙事必要的材质" in result.output["shared_context"]["prompt_rules"]["material_rule"]
    assert "保持描述清晰克制" in result.output["shared_context"]["prompt_rules"]["enrich_rule"]


@pytest.mark.asyncio
async def test_merge_segment_storyboard_descriptions_sorts_by_index() -> None:
    node = MergeSegmentStoryboardDescriptionsNode()

    result = await node.run(
        None,
        {
            "results": [
                {
                    "index": 2,
                    "segment_title": "第三段",
                    "thinking": "三",
                    "description": "c",
                },
                {
                    "index": 0,
                    "segment_title": "第一段",
                    "thinking": "一",
                    "description": "a",
                },
            ],
        },
    )

    assert result.output == {
        "segment_descriptions": [
            {
                "index": 0,
                "segment_title": "第一段",
                "thinking": "一",
                "description": "a",
            },
            {
                "index": 2,
                "segment_title": "第三段",
                "thinking": "三",
                "description": "c",
            },
        ]
    }
