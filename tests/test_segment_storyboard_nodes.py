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
            "segments": [
                {"index": 0, "text": "第一段", "panel_hint": "1", "panel_count_min": 1, "panel_count_max": 1},
                {"index": 1, "text": "第二段", "panel_hint": "2", "panel_count_min": 1, "panel_count_max": 2},
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
                },
            ],
            "storyboard_options": {"no_material": True, "enrich_description": True},
        },
    )

    assert result.status == "succeeded"
    items = result.output["items"]
    assert [item["index"] for item in items] == [0, 1, 2]
    assert items[1]["current_segment"]["text"] == "第二段"
    assert "neighbor_segments" not in items[1]
    assert items[1]["segment_assignment"] == {
        "segment_index": 1,
        "characters": [
            {
                "asset_name": "林冲",
                "asset_tags": ["囚服", "毡笠"],
                "appearance_description": "戴毡笠、穿囚服。",
                "presence": "present",
                "visibility": "in_frame",
                "reason": "本段正面描写林冲踏雪。",
            }
        ],
        "key_props": ["花枪"],
    }
    assert "full_script" not in items[1]
    assert "all_segments" not in items[1]
    assert result.output["shared_context"]["full_script"] == "完整剧本"
    assert "all_segments" not in result.output["shared_context"]
    assert result.output["shared_context"]["storyboard_options"] == {
        "no_material": True,
        "enrich_description": True,
    }


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
                    "panels": [{"description": "c", "style": "s", "constraints": "x"}],
                },
                {
                    "index": 0,
                    "segment_title": "第一段",
                    "thinking": "一",
                    "panels": [{"description": "a", "style": "s", "constraints": "x"}],
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
                "panels": [{"description": "a", "style": "s", "constraints": "x"}],
            },
            {
                "index": 2,
                "segment_title": "第三段",
                "thinking": "三",
                "panels": [{"description": "c", "style": "s", "constraints": "x"}],
            },
        ]
    }
