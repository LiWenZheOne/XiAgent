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
                {"segment_index": 1, "characters": [{"full_name": "林冲"}], "key_props": ["花枪"]},
            ],
        },
    )

    assert result.status == "succeeded"
    items = result.output["items"]
    assert [item["index"] for item in items] == [0, 1, 2]
    assert items[1]["current_segment"]["text"] == "第二段"
    assert [segment["index"] for segment in items[1]["neighbor_segments"]] == [0, 2]
    assert items[1]["segment_assignment"] == {
        "segment_index": 1,
        "characters": [{"full_name": "林冲"}],
        "key_props": ["花枪"],
    }
    assert "full_script" not in items[1]
    assert "all_segments" not in items[1]
    assert result.output["shared_context"]["full_script"] == "完整剧本"
    assert result.output["shared_context"]["all_segments"] == [
        {"index": 0, "text": "第一段", "panel_hint": "1", "panel_count_min": 1, "panel_count_max": 1},
        {"index": 1, "text": "第二段", "panel_hint": "2", "panel_count_min": 1, "panel_count_max": 2},
        {"index": 2, "text": "第三段", "panel_hint": "1", "panel_count_min": 1, "panel_count_max": 1},
    ]


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
