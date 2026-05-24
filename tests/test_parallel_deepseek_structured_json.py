from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.models import ChatModelRouter, ChatResponse
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.base import NodeContext, NodeResult


class FakeParallelRouter(ChatModelRouter):
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


def test_parallel_node_describe() -> None:
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=FakeParallelRouter([]),
        provider="deepseek",
        model="test-model",
    )
    desc = node.describe()
    assert desc.ref == "ai.parallel_deepseek_structured_json.v1"
    assert desc.input_schema["required"] == ["items", "prompt_template"]


@pytest.mark.asyncio
async def test_parallel_node_processes_all_items() -> None:
    responses = [
        '{"result": "a"}',
        '{"result": "b"}',
        '{"result": "c"}',
    ]
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [{"id": 1}, {"id": 2}, {"id": 3}],
            "prompt_template": "Process: {item}",
            "max_attempts": 1,
        },
    )

    assert result.status == "succeeded"
    assert result.output["results"] == [
        {"result": "a"},
        {"result": "b"},
        {"result": "c"},
    ]
    assert len(router.requests) == 3


@pytest.mark.asyncio
async def test_parallel_node_empty_items_raises() -> None:
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=FakeParallelRouter([]),
        provider="deepseek",
        model="test-model",
    )

    with pytest.raises(ValidationError, match="items must be a non-empty array"):
        await node.run(
            None,
            {
                "items": [],
                "prompt_template": "Process: {item}",
            },
        )


@pytest.mark.asyncio
async def test_parallel_node_missing_template_raises() -> None:
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=FakeParallelRouter([]),
        provider="deepseek",
        model="test-model",
    )

    with pytest.raises(ValidationError, match="prompt_template cannot be empty"):
        await node.run(
            None,
            {
                "items": [{"id": 1}],
                "prompt_template": "",
            },
        )


@pytest.mark.asyncio
async def test_parallel_node_template_interpolation() -> None:
    responses = ['{"name": "test"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    await node.run(
        None,
        {
            "items": [{"full_name": "林冲", "age": "中年"}],
            "prompt_template": "角色：{item}",
            "max_attempts": 1,
        },
    )

    request = router.requests[0]
    assert "林冲" in request.messages[-1].content
    assert "中年" in request.messages[-1].content


@pytest.mark.asyncio
async def test_parallel_node_with_system_prompt() -> None:
    responses = ['{"result": "ok"}']
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    await node.run(
        None,
        {
            "items": [{"id": 1}],
            "prompt_template": "Process: {item}",
            "system": "You are a helpful assistant.",
            "max_attempts": 1,
        },
    )

    request = router.requests[0]
    system_msg = request.messages[0]
    assert system_msg.role == "system"
    assert "You are a helpful assistant" in system_msg.content


@pytest.mark.asyncio
async def test_parallel_node_retry_on_parse_failure() -> None:
    responses = [
        "not json",
        '{"result": "ok"}',
    ]
    router = FakeParallelRouter(responses)
    node = ParallelDeepSeekStructuredJsonNode(
        model_router=router,
        provider="deepseek",
        model="test-model",
    )

    result = await node.run(
        None,
        {
            "items": [{"id": 1}],
            "prompt_template": "Process: {item}",
            "max_attempts": 2,
        },
    )

    assert result.status == "succeeded"
    assert result.output["results"] == [{"result": "ok"}]
    assert len(router.requests) == 2
