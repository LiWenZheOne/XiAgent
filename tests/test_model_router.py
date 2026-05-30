from __future__ import annotations

from typing import Any

import pytest

from xiagent.core.errors import ExternalServiceError, NotFoundError
from xiagent.models import ChatModelProvider


class RecordingProvider(ChatModelProvider):
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> Any:
        from xiagent.models import ChatResponse

        self.requests.append(request)
        return ChatResponse(
            text="fake response",
            model=request.model,
            usage={"prompt_tokens": 1, "completion_tokens": 2},
            metadata={"provider": request.provider},
        )


class FakeUsage:
    def model_dump(self) -> dict[str, int]:
        return {"prompt_tokens": 3, "completion_tokens": 5}


class FakeMessage:
    content = "deepseek response"


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    model = "deepseek-test-model"
    usage = FakeUsage()
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> FakeResponse:
        self.kwargs = kwargs
        if self.should_fail:
            raise RuntimeError("upstream unavailable")
        return FakeResponse()


class FakeChat:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.completions = FakeCompletions(should_fail=should_fail)


class FakeClient:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.chat = FakeChat(should_fail=should_fail)
        self.closed = False

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


class FakeRunningHubHttpClient:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def test_chat_model_router_registers_provider_and_routes_chat() -> None:
    from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest

    provider = RecordingProvider()
    router = ChatModelRouter()
    router.register_provider("fake", provider)
    request = ChatRequest(
        provider="fake",
        model="fake-model",
        messages=[ChatMessage(role="user", content="hello")],
    )

    response = await router.chat(request)

    assert provider.requests == [request]
    assert response.text == "fake response"
    assert response.model == "fake-model"
    assert response.usage == {"prompt_tokens": 1, "completion_tokens": 2}
    assert response.metadata == {"provider": "fake"}


async def test_chat_model_router_rejects_unknown_provider() -> None:
    from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest

    router = ChatModelRouter()
    request = ChatRequest(
        provider="missing",
        model="fake-model",
        messages=[ChatMessage(role="user", content="hello")],
    )

    with pytest.raises(NotFoundError) as exc:
        await router.chat(request)

    assert exc.value.code == "model_provider_not_found"
    assert exc.value.details == {"provider": "missing"}


def test_chat_model_router_rejects_non_provider() -> None:
    from xiagent.models import ChatModelRouter

    router = ChatModelRouter()

    with pytest.raises(TypeError):
        router.register_provider("bad", object())  # type: ignore[arg-type]


async def test_deepseek_provider_uses_client_factory_and_disables_thinking() -> None:
    from xiagent.models import ChatMessage, ChatRequest, DeepSeekModelConfig
    from xiagent.models.providers.deepseek import DeepSeekChatProvider

    fake_client = FakeClient()
    captured_factory_kwargs: dict[str, Any] = {}

    def client_factory(**kwargs: Any) -> FakeClient:
        captured_factory_kwargs.update(kwargs)
        return fake_client

    provider = DeepSeekChatProvider(
        config=DeepSeekModelConfig(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-test-model",
        ),
        client_factory=client_factory,
    )
    request = ChatRequest(
        provider="deepseek",
        model="deepseek-test-model",
        messages=[
            ChatMessage(role="system", content="be brief"),
            ChatMessage(role="user", content="hello"),
        ],
    )

    response = await provider.chat(request)

    assert captured_factory_kwargs == {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }
    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["model"] == "deepseek-test-model"
    assert fake_client.chat.completions.kwargs["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
    ]
    assert fake_client.chat.completions.kwargs["stream"] is False
    assert fake_client.chat.completions.kwargs["extra_body"] == {
        "thinking": {"type": "disabled"},
    }
    assert "thinking" not in fake_client.chat.completions.kwargs
    assert fake_client.closed is True
    assert response.text == "deepseek response"
    assert response.model == "deepseek-test-model"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 5}


async def test_deepseek_provider_wraps_request_failures() -> None:
    from xiagent.models import ChatMessage, ChatRequest, DeepSeekModelConfig
    from xiagent.models.providers.deepseek import DeepSeekChatProvider

    provider = DeepSeekChatProvider(
        config=DeepSeekModelConfig(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-test-model",
        ),
        client_factory=lambda **_: FakeClient(should_fail=True),
    )
    request = ChatRequest(
        provider="deepseek",
        model="deepseek-test-model",
        messages=[ChatMessage(role="user", content="hello")],
    )

    with pytest.raises(ExternalServiceError) as exc:
        await provider.chat(request)

    assert exc.value.code == "deepseek_request_failed"
    assert exc.value.details["provider"] == "deepseek"


async def test_runninghub_image_provider_submits_and_polls_generation() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    http_client = FakeRunningHubHttpClient(
        [
            {
                "taskId": "task-1",
                "status": "RUNNING",
                "errorCode": "",
                "errorMessage": "",
                "results": None,
                "clientId": "client-1",
                "promptTips": "",
            },
            {
                "taskId": "task-1",
                "status": "SUCCESS",
                "errorCode": "",
                "errorMessage": "",
                "results": [{"url": "https://example.test/output.png", "outputType": "png"}],
                "usage": {"consumeCoins": "1"},
                "clientId": "client-1",
                "promptTips": "",
            },
        ]
    )
    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-image-test-model",
            endpoint="/test/image-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="turn the sketch into ink wash art")],
        metadata={
            "images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
            "aspect_ratio": "1:1",
            "resolution": "2k",
        },
    )

    response = await provider.chat(request)

    assert http_client.calls == [
        {
            "url": "https://runninghub.test/openapi/v2/test/image-to-image",
            "headers": {
                "Authorization": "Bearer test-runninghub-key",
                "Content-Type": "application/json",
            },
            "payload": {
                "imageUrls": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
                "prompt": "turn the sketch into ink wash art",
                "aspectRatio": "1:1",
                "resolution": "2k",
            },
        },
        {
            "url": "https://runninghub.test/openapi/v2/query",
            "headers": {
                "Authorization": "Bearer test-runninghub-key",
                "Content-Type": "application/json",
            },
            "payload": {"taskId": "task-1"},
        },
    ]
    assert response.text == "https://example.test/output.png"
    assert response.model == "runninghub-image-test-model"
    assert response.usage == {"consumeCoins": "1"}
    assert response.metadata == {
        "provider": "runninghub_image",
        "task_id": "task-1",
        "status": "SUCCESS",
        "results": [{"url": "https://example.test/output.png", "outputType": "png"}],
    }
    assert "test-runninghub-key" not in str(response.metadata)


async def test_runninghub_image_provider_accepts_wrapped_data_response() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    http_client = FakeRunningHubHttpClient(
        [
            {
                "code": 0,
                "msg": "success",
                "data": {
                    "taskId": "wrapped-task-1",
                    "status": "RUNNING",
                    "results": None,
                },
            },
            {
                "code": 0,
                "msg": "success",
                "data": {
                    "taskId": "wrapped-task-1",
                    "status": "SUCCESS",
                    "results": [{"url": "https://example.test/wrapped-output.png"}],
                    "usage": {"consumeCoins": "1"},
                },
            },
        ]
    )
    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-image-test-model",
            endpoint="/test/image-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
        metadata={"images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]},
    )

    response = await provider.chat(request)

    assert response.text == "https://example.test/wrapped-output.png"
    assert response.usage == {"consumeCoins": "1"}
    assert response.metadata["task_id"] == "wrapped-task-1"
    assert response.metadata["status"] == "SUCCESS"
    assert [call["payload"] for call in http_client.calls] == [
        {
            "imageUrls": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
            "prompt": "paint it",
            "aspectRatio": "9:16",
            "resolution": "1k",
        },
        {"taskId": "wrapped-task-1"},
    ]


async def test_runninghub_image_provider_sends_base64_data_uris_as_image_urls() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    http_client = FakeRunningHubHttpClient(
        [
            {
                "taskId": "task-base64-1",
                "status": "SUCCESS",
                "results": [{"url": "https://example.test/base64-output.png"}],
            },
        ]
    )
    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-image-test-model",
            endpoint="/test/image-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )
    data_uri = "data:image/png;base64,aW1hZ2UtYnl0ZXM="
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
        metadata={
            "images": [data_uri],
        },
    )

    response = await provider.chat(request)

    assert response.text == "https://example.test/base64-output.png"
    assert http_client.calls[0]["payload"] == {
        "imageUrls": [data_uri],
        "prompt": "paint it",
        "aspectRatio": "9:16",
        "resolution": "1k",
    }


async def test_runninghub_image_provider_uses_request_polling_overrides() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    http_client = FakeRunningHubHttpClient(
        [
            {
                "taskId": "slow-task-1",
                "status": "RUNNING",
                "results": None,
            },
            {
                "taskId": "slow-task-1",
                "status": "SUCCESS",
                "results": [{"url": "https://example.test/slow-output.png"}],
            },
        ]
    )
    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-image-test-model",
            endpoint="/test/image-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=0,
        ),
        http_client=http_client,
    )
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="turn the sketch into ink wash art")],
        metadata={
            "images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
            "poll_interval_seconds": 0,
            "poll_timeout_seconds": 1,
        },
    )

    response = await provider.chat(request)

    assert response.text == "https://example.test/slow-output.png"
    assert [call["payload"] for call in http_client.calls] == [
        {
            "imageUrls": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="],
            "prompt": "turn the sketch into ink wash art",
            "aspectRatio": "9:16",
            "resolution": "1k",
        },
        {"taskId": "slow-task-1"},
    ]


async def test_runninghub_image_provider_rejects_empty_result_url() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-image-test-model",
            endpoint="/test/image-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=FakeRunningHubHttpClient(
            [
                {
                    "taskId": "task-empty-result",
                    "status": "SUCCESS",
                    "results": [{"url": "", "text": ""}],
                }
            ]
        ),
    )
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
        metadata={"images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]},
    )

    with pytest.raises(ExternalServiceError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_image_result_missing"
    assert exc.value.details == {
        "provider": "runninghub_image",
        "task_id": "task-empty-result",
    }


async def test_runninghub_image_provider_surfaces_submission_errors_without_task_id() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-image-test-model",
            endpoint="/test/image-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=FakeRunningHubHttpClient(
            [
                {
                    "taskId": "",
                    "status": "",
                    "errorCode": "1007",
                    "errorMessage": "field 'resolution' value 2048x2048 is not in the allowed options",
                    "results": None,
                }
            ]
        ),
    )
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
        metadata={"images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]},
    )

    with pytest.raises(ExternalServiceError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_image_request_failed"
    assert "2048x2048" in exc.value.message
    assert exc.value.details == {
        "provider": "runninghub_image",
        "status": "FAILED",
        "error_code": "1007",
        "error_message": "field 'resolution' value 2048x2048 is not in the allowed options",
    }


async def test_runninghub_text_to_image_provider_submits_and_polls_generation() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubTextToImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubTextToImageProvider

    http_client = FakeRunningHubHttpClient(
        [
            {
                "taskId": "text-task-1",
                "status": "RUNNING",
                "errorCode": "",
                "errorMessage": "",
                "results": None,
                "clientId": "client-1",
                "promptTips": "",
            },
            {
                "taskId": "text-task-1",
                "status": "SUCCESS",
                "errorCode": "",
                "errorMessage": "",
                "results": [{"url": "https://example.test/text-output.png"}],
                "usage": {"consumeCoins": "2"},
                "clientId": "client-1",
                "promptTips": "",
            },
        ]
    )
    provider = RunningHubTextToImageProvider(
        config=RunningHubTextToImageModelConfig(
            api_key="test-runninghub-key",
            base_url="https://runninghub.test",
            model="runninghub-text-image-test-model",
            endpoint="/test/text-to-image",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )
    request = ChatRequest(
        provider="runninghub_text_to_image",
        model="runninghub-text-image-test-model",
        messages=[ChatMessage(role="user", content="paint a lantern street at night")],
        metadata={
            "aspect_ratio": "16:9",
            "resolution": "4k",
        },
    )

    response = await provider.chat(request)

    assert http_client.calls == [
        {
            "url": "https://runninghub.test/openapi/v2/test/text-to-image",
            "headers": {
                "Authorization": "Bearer test-runninghub-key",
                "Content-Type": "application/json",
            },
            "payload": {
                "prompt": "paint a lantern street at night",
                "aspectRatio": "16:9",
                "resolution": "4k",
            },
        },
        {
            "url": "https://runninghub.test/openapi/v2/query",
            "headers": {
                "Authorization": "Bearer test-runninghub-key",
                "Content-Type": "application/json",
            },
            "payload": {"taskId": "text-task-1"},
        },
    ]
    assert response.text == "https://example.test/text-output.png"
    assert response.model == "runninghub-text-image-test-model"
    assert response.usage == {"consumeCoins": "2"}
    assert response.metadata == {
        "provider": "runninghub_text_to_image",
        "task_id": "text-task-1",
        "status": "SUCCESS",
        "results": [{"url": "https://example.test/text-output.png"}],
    }
    assert "test-runninghub-key" not in str(response.metadata)


async def test_runninghub_text_to_image_provider_requires_key_and_prompt() -> None:
    from xiagent.core.errors import ValidationError
    from xiagent.models import ChatMessage, ChatRequest, RunningHubTextToImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubTextToImageProvider

    provider = RunningHubTextToImageProvider(
        config=RunningHubTextToImageModelConfig(api_key=None)
    )
    request = ChatRequest(
        provider="runninghub_text_to_image",
        model="runninghub-text-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
    )

    with pytest.raises(ValidationError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_api_key_missing"
    assert exc.value.details == {"provider": "runninghub_text_to_image"}

    provider = RunningHubTextToImageProvider(
        config=RunningHubTextToImageModelConfig(api_key="test-key")
    )
    request = ChatRequest(
        provider="runninghub_text_to_image",
        model="runninghub-text-image-test-model",
        messages=[ChatMessage(role="user", content="")],
    )

    with pytest.raises(ValidationError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_prompt_missing"
    assert exc.value.details == {"provider": "runninghub_text_to_image"}


async def test_runninghub_image_provider_requires_key_and_images() -> None:
    from xiagent.core.errors import ValidationError
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    provider = RunningHubImageProvider(config=RunningHubImageModelConfig(api_key=None))
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
        metadata={"images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]},
    )

    with pytest.raises(ValidationError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_api_key_missing"
    assert exc.value.details == {"provider": "runninghub_image"}

    provider = RunningHubImageProvider(config=RunningHubImageModelConfig(api_key="test-key"))
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
    )

    with pytest.raises(ValidationError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_images_missing"
    assert exc.value.details == {"provider": "runninghub_image"}


async def test_runninghub_image_provider_wraps_failures_without_secret_details() -> None:
    from xiagent.models import ChatMessage, ChatRequest, RunningHubImageModelConfig
    from xiagent.models.providers.runninghub import RunningHubImageProvider

    provider = RunningHubImageProvider(
        config=RunningHubImageModelConfig(api_key="secret-runninghub-key"),
        http_client=FakeRunningHubHttpClient([RuntimeError("upstream unavailable")]),
    )
    request = ChatRequest(
        provider="runninghub_image",
        model="runninghub-image-test-model",
        messages=[ChatMessage(role="user", content="paint it")],
        metadata={"images": ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]},
    )

    with pytest.raises(ExternalServiceError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_image_request_failed"
    assert exc.value.details == {
        "provider": "runninghub_image",
        "endpoint": "/rhart-image-n-g31-flash/image-to-image",
    }
    assert "secret-runninghub-key" not in str(exc.value.details)
