from __future__ import annotations

import json
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.asset_draft_from_description import AssetDraftFromDescriptionNode


class FakeAssetDraftRouter(ChatModelRouter):
    def __init__(self, responses: list[str]) -> None:
        super().__init__()
        self.responses = responses
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            text=self.responses.pop(0),
            model=request.model,
            metadata={"provider": request.provider},
        )


async def test_asset_draft_node_builds_prompt_and_returns_multiple_typed_assets() -> None:
    router = FakeAssetDraftRouter([
        json.dumps(
            {
                "assets": [
                    {
                        "asset_type": "character",
                        "asset_name": "官兵",
                        "asset_tags": ["官兵服", "佩刀"],
                        "matched": False,
                        "matched_asset_id": None,
                        "matched_asset_name": "",
                        "aliases": "",
                        "summary": "船上的官府兵丁。",
                        "character_status": "押送途中",
                        "appearance_description": "头戴官兵软巾，上身深色短袍束带，腰侧佩刀，神态警觉，保留押送兵丁的稳定识别特征。",
                    },
                    {
                        "asset_type": "scene",
                        "asset_name": "官兵船",
                        "asset_tags": ["水上", "官船"],
                        "matched": False,
                        "matched_asset_id": None,
                        "matched_asset_name": "",
                        "description": "官兵在水上押送使用的船只，甲板可供多人停留，设低矮船舱、桅杆、缆绳和官府旗号。",
                        "location_type": "水上",
                        "time_of_day": "",
                    },
                    {
                        "asset_type": "prop",
                        "asset_name": "官兵刀",
                        "asset_tags": ["武器", "官兵"],
                        "matched": False,
                        "matched_asset_id": None,
                        "matched_asset_name": "",
                        "description": "官兵押送犯人时随身携带的制式短刀，直背窄身，深色刀柄配铜色护手，刀鞘有磨损，便于近身戒备。",
                        "category": "武器",
                        "related_character": "官兵",
                    },
                ],
                "confidence": 0.82,
                "reasoning": "根据用户描述拆分为角色、地点和道具。",
            },
            ensure_ascii=False,
        )
    ])
    node = AssetDraftFromDescriptionNode(
        model_router=router,
        provider="deepseek",
        model="deepseek-test-model",
    )

    result = await node.run(
        ctx=None,
        inputs={
            "asset_type": "auto",
            "description": "官兵的船、船上的官兵和兵器",
            "script": "官兵押着犯人上船。",
            "background": "水浒传",
            "current_assets": {"characters": []},
        },
    )

    assert result.status == "succeeded"
    assert [item["asset_type"] for item in result.output["assets"]] == ["character", "scene", "prop"]
    request = router.requests[0]
    prompt_text = "\n".join(str(message.content) for message in request.messages)
    assert "用户描述的新资产需求" in prompt_text
    assert "用户要求新增几个资产" in prompt_text
    assert "每个新增资产分别是什么类型：character、scene 还是 prop" in prompt_text
    assert "地点统一输出 scene" in prompt_text
    assert "按对应提取规则补全哪些字段" in prompt_text
    assert "先根据用户描述、原始剧本、世界背景、角色身份、职业/阶层、地点和剧情阶段推断" in prompt_text
    assert "必须从身份、职业/阶层、时代、地点和当前情景推导一个具体稳定造型名" in prompt_text
    assert "禁止填“默认”“基础”“普通”“无特殊造型”" in prompt_text
    assert "至少 40 字的详细稳定视觉设定" in prompt_text
    assert "不要描述任何材质、布料质感、纹理或面料工艺" in prompt_text
    assert "禁止“默认装束，无特殊造型描述”" in prompt_text
    assert "穿戴类外观元素不作为 prop" in prompt_text
    assert "大型载具、建筑、场所或可供角色进入/停留的空间，应归入 scene" in prompt_text
    assert "道具 description 必须同时包含两类信息" in prompt_text
    assert "整体形制、尺寸比例、材质、颜色、装饰、磨损痕迹、用途和可见特征" in prompt_text
    assert "官兵押着犯人上船" in prompt_text


async def test_asset_draft_node_rejects_invalid_asset_type_from_model() -> None:
    router = FakeAssetDraftRouter([
        json.dumps(
            {
                "assets": [
                    {
                        "asset_type": "scene",
                        "asset_name": "官兵船",
                        "asset_tags": [],
                        "matched": False,
                        "matched_asset_id": None,
                        "matched_asset_name": "",
                        "description": "官兵在水上押送使用的船只。",
                        "location_type": "水上",
                        "time_of_day": "",
                    }
                ],
                "confidence": 0.9,
                "reasoning": "bad",
            },
            ensure_ascii=False,
        )
    ])
    node = AssetDraftFromDescriptionNode(
        model_router=router,
        provider="deepseek",
        model="deepseek-test-model",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"asset_type": "character", "description": "官兵", "max_attempts": 1})

    assert exc.value.code == "asset_draft_json_validation_failed"
