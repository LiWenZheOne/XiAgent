from __future__ import annotations

from typing import Any

import pytest

from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.base import NodeContext
from xiagent.nodes.ai.storyboard_review_refine import StoryboardReviewRefineNode


class FakeStoryboardReviewRouter(ChatModelRouter):
    def __init__(self, responses: list[str]) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._responses = responses

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            text=self._responses.pop(0),
            model=request.model,
            usage={"completion_tokens": 1},
            metadata={"provider": request.provider},
        )


REVIEW_SYSTEM = "仅返回合法 JSON。审查当前分镜。"
REVIEW_TEMPLATE = (
    "当前段落：{item.paragraph_text}\n"
    "场景布局：{segment.scene_layout}\n"
    "分镜描述：{segment.description}\n"
    "审查问题：是否合格？"
)
REVISION_SYSTEM = "仅返回合法 JSON。按意见修订分镜。"
REVISION_TEMPLATE = (
    "当前段落：{item.paragraph_text}\n"
    "原分镜描述：{segment.description}\n"
    "修改意见：{review.revision_instructions}"
)


def test_storyboard_review_refine_descriptor() -> None:
    node = StoryboardReviewRefineNode(
        model_router=FakeStoryboardReviewRouter([]),
        provider="deepseek",
        model="test-model",
    )

    descriptor = node.describe()

    assert descriptor.ref == "ai.storyboard_review_refine.v1"
    assert descriptor.kind == "ai"
    assert descriptor.input_schema["required"] == [
        "items",
        "review_system",
        "review_prompt_template",
        "revision_system",
        "revision_prompt_template",
    ]
    assert descriptor.output_schema["required"] == ["results"]
    assert "required_input_fields" in descriptor.input_schema["properties"]


@pytest.mark.asyncio
async def test_storyboard_review_refine_keeps_passed_description() -> None:
    router = FakeStoryboardReviewRouter(
        [
            """
            {
              "think": "当前描述符合单格分镜要求。",
              "passed": true,
              "issues": [],
              "revision_instructions": "",
              "revision_summary": "无需修改"
            }
            """
        ]
    )
    node = StoryboardReviewRefineNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [
                {
                    "index": 0,
                    "segment_title": "雪夜",
                    "scene_layout": {"location_summary": "野猪林雪地"},
                    "panel_plan": {"panel_count": 1, "panels": []},
                    "thinking": "单格压迫。",
                    "description": "单个大分格。林冲背对镜头在雪中前行。",
                }
            ],
            "storyboard_items": [
                {
                    "index": 0,
                    "paragraph_text": "林冲踏雪而行。",
                    "panel_count": "1",
                    "present_characters": ["林冲"],
                    "location": "野猪林",
                    "key_props": [],
                }
            ],
            "shared_context": {"full_script": "完整剧本"},
            "review_system": REVIEW_SYSTEM,
            "review_prompt_template": REVIEW_TEMPLATE,
            "revision_system": REVISION_SYSTEM,
            "revision_prompt_template": REVISION_TEMPLATE,
            "review_output_field": "custom_review",
            "review_history_output_field": "custom_review_history",
            "max_revision_rounds": 2,
        },
    )

    refined = result.output["results"][0]
    assert refined["description"] == "单个大分格。林冲背对镜头在雪中前行。"
    assert refined["custom_review"]["passed"] is True
    assert refined["custom_review"]["rounds"] == 1
    assert refined["custom_review_history"][0]["passed"] is True
    assert "review" not in refined
    assert "review_history" not in refined
    assert len(router.requests) == 1
    assert router.requests[0].metadata == {"response_format": {"type": "json_object"}}
    assert "林冲踏雪而行" in router.requests[0].messages[-1].content


@pytest.mark.asyncio
async def test_storyboard_review_refine_revises_until_passed() -> None:
    router = FakeStoryboardReviewRouter(
        [
            """
            {
              "think": "描述加入不在场角色，需要收束。",
              "passed": false,
              "issues": ["描述加入了不在场角色"],
              "revision_instructions": "删除不在场角色，只保留林冲。",
              "revision_summary": "需要收束入画对象"
            }
            """,
            """
            {
              "index": 0,
              "segment_title": "雪夜",
              "thinking": "删除不在场角色，保留单格雪夜压迫。",
              "description": "单个大分格。林冲背对镜头穿过雪林，前景树干遮住画面一侧。"
            }
            """,
            """
            {
              "think": "修订后只保留当前段落角色。",
              "passed": true,
              "issues": [],
              "revision_instructions": "",
              "revision_summary": "修订后通过"
            }
            """,
        ]
    )
    node = StoryboardReviewRefineNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [
                {
                    "index": 0,
                    "segment_title": "雪夜",
                    "scene_layout": {"location_summary": "野猪林雪地"},
                    "panel_plan": {"panel_count": 1, "panels": []},
                    "thinking": "单格压迫。",
                    "description": "单个大分格。林冲和鲁智深在雪中同行。",
                }
            ],
            "storyboard_items": [
                {
                    "index": 0,
                    "paragraph_text": "林冲踏雪而行。",
                    "panel_count": "1",
                    "present_characters": ["林冲"],
                    "location": "野猪林",
                    "key_props": [],
                }
            ],
            "shared_context": {"full_script": "完整剧本"},
            "review_system": REVIEW_SYSTEM,
            "review_prompt_template": REVIEW_TEMPLATE,
            "revision_system": REVISION_SYSTEM,
            "revision_prompt_template": REVISION_TEMPLATE,
            "review_output_field": "review",
            "review_history_output_field": "review_history",
            "max_revision_rounds": 2,
        },
    )

    refined = result.output["results"][0]
    assert refined["description"] == "单个大分格。林冲背对镜头穿过雪林，前景树干遮住画面一侧。"
    assert refined["review"]["passed"] is True
    assert refined["review"]["rounds"] == 2
    assert refined["review"]["revision_summary"] == "修订后通过"
    assert refined["review_history"][0]["issues"] == ["描述加入了不在场角色"]
    assert len(router.requests) == 3
    assert "修改意见" in router.requests[1].messages[-1].content


@pytest.mark.asyncio
async def test_storyboard_review_refine_inherits_identity_fields_for_partial_revision() -> None:
    router = FakeStoryboardReviewRouter(
        [
            """
            {
              "think": "提示词遗漏完整分格内容。",
              "passed": false,
              "issues": ["提示词遗漏分格"],
              "revision_instructions": "补齐完整画面内容。",
              "revision_summary": "需要修订提示词"
            }
            """,
            """
            {
              "index": 999,
              "segment_title": "错误标题",
              "image_prompt": "## 整体情节\\n林冲踏雪而行。\\n\\n## 分格\\n单个大分格。"
            }
            """,
            """
            {
              "think": "修订后覆盖当前计划。",
              "passed": true,
              "issues": [],
              "revision_instructions": "",
              "revision_summary": "修订后通过"
            }
            """,
        ]
    )
    node = StoryboardReviewRefineNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )
    ctx = NodeContext(
        user_id="user",
        project_id="project",
        task_id="task",
        node_id="review_and_refine_image_prompt",
        node_execution_id="exec",
        config={},
        output_schema={
            "type": "object",
            "required": ["results"],
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "index",
                            "segment_title",
                            "paragraph_text",
                            "panel_count",
                            "present_characters",
                            "location",
                            "key_props",
                            "segment_assignment",
                            "scene_layout",
                            "panel_plan",
                            "image_prompt",
                            "review",
                            "review_history",
                            "prompt_review",
                            "prompt_review_history",
                        ],
                        "properties": {
                            "index": {"type": "integer", "minimum": 0},
                            "segment_title": {"type": "string", "minLength": 1},
                            "paragraph_text": {"type": "string"},
                            "panel_count": {"type": "string"},
                            "present_characters": {"type": "array", "items": {"type": "string"}},
                            "location": {"type": "string"},
                            "key_props": {"type": "array", "items": {"type": "string"}},
                            "segment_assignment": {"type": "object", "additionalProperties": True},
                            "scene_layout": {"type": "object", "additionalProperties": True},
                            "panel_plan": {"type": "object", "additionalProperties": True},
                            "image_prompt": {"type": "string", "minLength": 1},
                            "review": {"type": "object", "additionalProperties": True},
                            "review_history": {
                                "type": "array",
                                "items": {"type": "object", "additionalProperties": True},
                            },
                            "prompt_review": {"type": "object", "additionalProperties": True},
                            "prompt_review_history": {
                                "type": "array",
                                "items": {"type": "object", "additionalProperties": True},
                            },
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "additionalProperties": False,
        },
        asset_service=None,
        event_sink=None,
        logger=None,
    )

    result = await node.run(
        ctx,
        {
            "items": [
                {
                    "index": 0,
                    "segment_title": "雪夜",
                    "paragraph_text": "林冲踏雪而行。",
                    "panel_count": "1",
                    "present_characters": ["林冲"],
                    "location": "野猪林",
                    "key_props": [],
                    "segment_assignment": {"segment_index": 0},
                    "scene_layout": {"location_summary": "野猪林雪地"},
                    "panel_plan": {"panel_count": 1, "panels": []},
                    "image_prompt": "林冲在雪中前行。",
                    "review": {"passed": True},
                    "review_history": [],
                }
            ],
            "storyboard_items": [
                {
                    "index": 0,
                    "paragraph_text": "林冲踏雪而行。",
                    "panel_count": "1",
                    "present_characters": ["林冲"],
                    "location": "野猪林",
                    "key_props": [],
                }
            ],
            "shared_context": {"full_script": "完整剧本"},
            "review_system": REVIEW_SYSTEM,
            "review_prompt_template": "画面提示词：{source.image_prompt}",
            "revision_system": REVISION_SYSTEM,
            "revision_prompt_template": "修改意见：{review.revision_instructions}",
            "review_output_field": "prompt_review",
            "review_history_output_field": "prompt_review_history",
            "max_revision_rounds": 1,
        },
    )

    refined = result.output["results"][0]
    assert refined["index"] == 0
    assert refined["segment_title"] == "雪夜"
    assert refined["paragraph_text"] == "林冲踏雪而行。"
    assert refined["scene_layout"] == {"location_summary": "野猪林雪地"}
    assert refined["panel_plan"] == {"panel_count": 1, "panels": []}
    assert refined["image_prompt"].startswith("## 整体情节")
    assert refined["prompt_review"]["passed"] is True
    assert len(router.requests) == 3


@pytest.mark.asyncio
async def test_storyboard_review_refine_skips_failed_items_when_continue_enabled() -> None:
    router = FakeStoryboardReviewRouter(
        [
            """
            {
              "think": "分镜描述符合要求。",
              "passed": true,
              "issues": [],
              "revision_instructions": "",
              "revision_summary": "通过"
            }
            """
        ]
    )
    node = StoryboardReviewRefineNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [
                {
                    "index": 0,
                    "segment_title": "成功段",
                    "scene_layout": {"location_summary": "雪地"},
                    "panel_plan": {"panel_count": 1, "panels": []},
                    "description": "林冲踏雪前行。",
                },
                {
                    "index": 1,
                    "segment_title": "失败段",
                    "status": "failed",
                    "error": {"code": "structured_json_parse_failed", "message": "DeepSeek response is not valid JSON"},
                },
            ],
            "storyboard_items": [
                {"index": 0, "paragraph_text": "林冲踏雪而行。"},
                {"index": 1, "paragraph_text": "鲁智深伏在林中。"},
            ],
            "shared_context": {"full_script": "完整剧本"},
            "review_system": REVIEW_SYSTEM,
            "review_prompt_template": REVIEW_TEMPLATE,
            "revision_system": REVISION_SYSTEM,
            "revision_prompt_template": REVISION_TEMPLATE,
            "review_output_field": "review",
            "review_history_output_field": "review_history",
            "max_revision_rounds": 1,
            "continue_on_item_error": True,
        },
    )

    passed, failed = result.output["results"]
    assert passed["review"]["passed"] is True
    assert failed["index"] == 1
    assert failed["segment_title"] == "失败段"
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "structured_json_parse_failed"


@pytest.mark.asyncio
async def test_storyboard_review_refine_fails_item_when_required_input_missing() -> None:
    router = FakeStoryboardReviewRouter([])
    node = StoryboardReviewRefineNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [
                {
                    "index": 0,
                    "segment_title": "缺计划",
                    "paragraph_text": "林冲踏雪而行。",
                }
            ],
            "storyboard_items": [{"index": 0, "paragraph_text": "林冲踏雪而行。"}],
            "review_system": REVIEW_SYSTEM,
            "review_prompt_template": REVIEW_TEMPLATE,
            "revision_system": REVISION_SYSTEM,
            "revision_prompt_template": REVISION_TEMPLATE,
            "required_input_fields": ["scene_layout", "panel_plan"],
            "continue_on_item_error": True,
        },
    )

    failed = result.output["results"][0]
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "storyboard_review_required_input_missing"
    assert failed["error"]["details"]["missing_fields"] == ["scene_layout", "panel_plan"]
    assert router.requests == []
