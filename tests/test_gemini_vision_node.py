from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.models.router import ChatModelRouter
from xiagent.models.types import ChatMessage, ChatRequest, ChatResponse
from xiagent.nodes.ai.gemini_vision import GeminiVisionNode


def _make_vision_node(
    *,
    model_router: ChatModelRouter | None = None,
    provider: str = "gemini",
    model: str = "gemini-3-flash-preview",
) -> GeminiVisionNode:
    if model_router is None:
        model_router = ChatModelRouter()
    return GeminiVisionNode(model_router=model_router, provider=provider, model=model)


def _mock_chat_response(text: str, model: str = "gemini-3-flash-preview") -> ChatResponse:
    return ChatResponse(
        text=text,
        model=model,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        metadata={"provider": "gemini"},
    )


# ---------------------------------------------------------------------------
# Test 1: image_urls=[] → ValidationError
# ---------------------------------------------------------------------------
async def test_gemini_vision_node_rejects_empty_image_urls() -> None:
    node = _make_vision_node()

    with pytest.raises(ValidationError) as exc_info:
        await node.run(
            ctx=None,
            inputs={"prompt": "Describe this image", "image_urls": []},
        )

    assert exc_info.value.code == "gemini_vision_image_urls_empty"


# ---------------------------------------------------------------------------
# Test 2: prompt="" → ValidationError
# ---------------------------------------------------------------------------
async def test_gemini_vision_node_rejects_empty_prompt() -> None:
    node = _make_vision_node()

    with pytest.raises(ValidationError) as exc_info:
        await node.run(
            ctx=None,
            inputs={"prompt": "", "image_urls": ["https://example.com/img.png"]},
        )

    assert exc_info.value.code == "gemini_vision_prompt_empty"


# ---------------------------------------------------------------------------
# Test 3: mock 返回 <think>/<caption> → output.caption 正确提取
# ---------------------------------------------------------------------------
async def test_gemini_vision_node_extracts_caption() -> None:
    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(
        return_value=_mock_chat_response(
            text="<think>第零步·漫画分格与布局分析...</think>\n<caption>这是一幅描述两位角色对话的中文漫画。</caption>"
        )
    )

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    assert result.output["caption"] == "这是一幅描述两位角色对话的中文漫画。"
    assert "第零步·漫画分格与布局分析" in result.output["think"]
    assert result.output["model"] == "gemini-3-flash-preview"
    assert result.output["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}

    # 验证 multimodal content 构造正确
    mock_router.chat.assert_called_once()
    call_arg = mock_router.chat.call_args.args[0]
    assert isinstance(call_arg, ChatRequest)
    assert call_arg.provider == "gemini"
    assert len(call_arg.messages) >= 1
    user_msg = call_arg.messages[-1]
    assert user_msg.role == "user"
    assert isinstance(user_msg.content, list)
    assert user_msg.content[0] == {"type": "text", "text": "请描述这张漫画"}
    assert user_msg.content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/comic.png"},
    }


# ---------------------------------------------------------------------------
# Test 4: 无 <caption> 标签 → fallback 到全文
# ---------------------------------------------------------------------------
async def test_gemini_vision_node_handles_missing_caption() -> None:
    plain_text = "这是一幅描绘两位角色对话的漫画。画面采用暖色调..."

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(return_value=_mock_chat_response(text=plain_text))

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    assert result.output["caption"] == plain_text
    assert result.output["think"] == ""


# ---------------------------------------------------------------------------
# Test 5: mock API 超时异常 → 正确传播错误
# ---------------------------------------------------------------------------
async def test_gemini_vision_node_handles_api_timeout() -> None:
    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(
        side_effect=ExternalServiceError(
            code="gemini_request_failed",
            message="API request timed out",
        )
    )

    node = _make_vision_node(model_router=mock_router)

    with pytest.raises(ExternalServiceError) as exc_info:
        await node.run(
            ctx=None,
            inputs={
                "prompt": "请描述这张漫画",
                "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
            },
        )

    assert exc_info.value.code == "gemini_request_failed"


# ---------------------------------------------------------------------------
# Test 6: max_attempts=2, 第一次 API 失败 → 重试后第二次成功
# ---------------------------------------------------------------------------
async def test_gemini_vision_node_max_attempts_retry() -> None:
    """第一次调用 API 抛出 ExternalServiceError, 重试后第二次返回有效 <caption>。"""
    second_response = _mock_chat_response(
        text="<think>重新分析后...</think>\n<caption>正确的描述内容</caption>"
    )

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(
        side_effect=[
            ExternalServiceError(code="gemini_request_failed", message="API error"),
            second_response,
        ]
    )

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
            "max_attempts": 2,
        },
    )

    assert result.status == "succeeded"
    assert result.output["caption"] == "正确的描述内容"
    assert result.output["think"] == "重新分析后..."
    assert mock_router.chat.call_count == 2


# ============================================================================
# Edge/boundary case tests
# ============================================================================


# ---------------------------------------------------------------------------
# Test 7: malformed XML (misspelled <captio> tag) → fallback to full text
# ---------------------------------------------------------------------------
async def test_gemini_vision_handles_malformed_xml() -> None:
    """标签拼写错误 <captio> → fallback 到全文提取."""
    malformed = "<think>test</think><captio>误拼标签</captio>"

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(return_value=_mock_chat_response(text=malformed))

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    # <think> should still be extracted because spelling is correct
    assert result.output["think"] == "test"
    # <captio> is misspelled → regex does NOT match → fallback to full text
    assert result.output["caption"] == malformed


# ---------------------------------------------------------------------------
# Test 8: empty response text → no crash, caption is empty string
# ---------------------------------------------------------------------------
async def test_gemini_vision_handles_empty_response() -> None:
    """Mock 返回空字符串 → 不崩溃，caption 为空字符串."""

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(return_value=_mock_chat_response(text=""))

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    assert result.output["think"] == ""
    assert result.output["caption"] == ""


# ---------------------------------------------------------------------------
# Test 9: pure text with no XML tags at all → fallback to full text
# ---------------------------------------------------------------------------
async def test_gemini_vision_handles_no_tags_at_all() -> None:
    """Mock 返回纯文本"这是分镜描述" → caption fallback 到全文."""

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(
        return_value=_mock_chat_response(text="这是分镜描述")
    )

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    assert result.output["think"] == ""
    assert result.output["caption"] == "这是分镜描述"


# ---------------------------------------------------------------------------
# Test 10: multiple <caption> tags → take the first one
# ---------------------------------------------------------------------------
async def test_gemini_vision_multiple_caption_tags() -> None:
    """Mock 返回多个 <caption> 标签 → 取第一个 caption."""

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(
        return_value=_mock_chat_response(
            text="<caption>第一段</caption><caption>第二段</caption>"
        )
    )

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    # regex.search() returns the first match by default
    assert result.output["caption"] == "第一段"


# ---------------------------------------------------------------------------
# Test 11: model returns safety-blocked response → content is empty string
# ---------------------------------------------------------------------------
async def test_gemini_vision_handles_safety_blocked_response() -> None:
    """Mock 返回空 content（safety block）→ 不崩溃."""

    mock_router = MagicMock(spec=ChatModelRouter)
    mock_router.chat = AsyncMock(
        return_value=ChatResponse(
            text="",
            model="gemini-3-flash-preview",
            usage={"prompt_tokens": 10, "completion_tokens": 0},
            metadata={"provider": "gemini", "safety_blocked": True},
        )
    )

    node = _make_vision_node(model_router=mock_router)

    result = await node.run(
        ctx=None,
        inputs={
            "prompt": "请描述这张漫画",
            "image_urls": ["https://example.com/comic.png"],
            "system": "test system prompt",
        },
    )

    assert result.status == "succeeded"
    assert result.output["caption"] == ""
    assert result.output["think"] == ""
    assert result.output["model"] == "gemini-3-flash-preview"
