from __future__ import annotations

import json
from typing import Any

from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.asset_metadata_from_upload import AssetMetadataFromUploadNode


class FakeAssetUploadMetadataRouter(ChatModelRouter):
    def __init__(self, response: str) -> None:
        super().__init__()
        self.response = response
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(text=self.response, model=request.model, metadata={"provider": request.provider})


async def test_asset_metadata_from_upload_node_generates_character_metadata_prompt() -> None:
    router = FakeAssetUploadMetadataRouter(
        json.dumps(
            {
                "metadata": {
                    "type": "character",
                    "aliases": "豹子头",
                    "summary": "八十万禁军教头，后因奸臣陷害走上梁山。",
                    "relationships": "与鲁智深、柴进等梁山人物有交集。",
                    "character_status": "流落江湖阶段。",
                    "variant_name": "教头常服",
                    "variant_description": "头戴软巾，上身整洁短袍，腰间束带，神态沉稳，带有武官气质。",
                    "accessories": "长枪",
                    "description": "沉稳威严的武人形象。",
                    "location_type": "",
                    "time_of_day": "",
                    "category": "",
                    "related_character": "",
                },
                "confidence": 0.88,
                "reasoning": "根据资产名和水浒传背景补全角色资料。",
            },
            ensure_ascii=False,
        )
    )
    node = AssetMetadataFromUploadNode(
        model_router=router,
        provider="deepseek",
        model="deepseek-test-model",
    )

    result = await node.run(
        ctx=None,
        inputs={
            "asset_name": "林冲",
            "asset_type": "character",
            "world_background": "水浒传",
            "asset_id": "asset-1",
        },
    )

    assert result.status == "succeeded"
    assert result.output["metadata"]["type"] == "character"
    assert result.output["metadata"]["summary"].startswith("八十万禁军教头")
    assert result.output["confidence"] == 0.88
    prompt = "\n".join(str(message.content) for message in router.requests[0].messages)
    assert "资产名" in prompt
    assert "林冲" in prompt
    assert "世界背景" in prompt
    assert "水浒传" in prompt
    assert "角色资产" in prompt
    assert "生平背景" in prompt
    assert "不要描述材质" in prompt
