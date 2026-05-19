from __future__ import annotations

import pytest

from xiagent.core.errors import ValidationError
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode


async def test_deepseek_node_requires_api_key() -> None:
    node = DeepSeekChatNode(
        api_key=None,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": "你好"})
    assert exc.value.code == "deepseek_api_key_missing"


async def test_deepseek_node_requires_non_empty_prompt() -> None:
    node = DeepSeekChatNode(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": " "})

    assert exc.value.code == "deepseek_prompt_required"


def test_deepseek_descriptor_requires_prompt() -> None:
    node = DeepSeekChatNode(
        api_key=None,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    descriptor = node.describe()

    assert descriptor.ref == "ai.deepseek_chat.v1"
    assert descriptor.input_schema["required"] == ["prompt"]
