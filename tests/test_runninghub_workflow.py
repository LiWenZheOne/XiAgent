from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.models.types import ChatMessage, ChatRequest, RunningHubWorkflowModelConfig


class FakeWorkflowHttpClient:
    """Mocks _UrllibJsonClient.post_json for workflow provider tests."""

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


# ---------------------------------------------------------------------------
# Test 1: api_key=None → ValidationError
# ---------------------------------------------------------------------------
async def test_workflow_provider_requires_api_key() -> None:
    from xiagent.models.providers.runninghub import RunningHubWorkflowProvider

    provider = RunningHubWorkflowProvider(
        config=RunningHubWorkflowModelConfig(api_key=None),
    )
    request = ChatRequest(
        provider="runninghub_workflow",
        model="2059174216020357122",
        messages=[ChatMessage(role="user", content="a cat in anime style")],
    )

    with pytest.raises(ValidationError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_workflow_api_key_missing"
    assert exc.value.details["provider"] == "runninghub_workflow"


# ---------------------------------------------------------------------------
# Test 2: Images are uploaded via _upload_image before submit
# ---------------------------------------------------------------------------
async def test_workflow_provider_uploads_images() -> None:
    from xiagent.models.providers.runninghub import RunningHubWorkflowProvider

    http_client = FakeWorkflowHttpClient(
        [
            {
                "taskId": "workflow-task-1",
                "status": "RUNNING",
                "results": None,
            },
            {
                "taskId": "workflow-task-1",
                "status": "SUCCESS",
                "results": [{"url": "https://cdn.test/output.png"}],
            },
        ]
    )
    provider = RunningHubWorkflowProvider(
        config=RunningHubWorkflowModelConfig(
            api_key="test-key",
            base_url="https://runninghub.test",
            workflow_id="wf-001",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )

    # Patch _upload_image to return predictable filenames
    upload_mock = AsyncMock()
    upload_mock.side_effect = lambda url: {
        "https://example.test/lineart.png": "uploaded_lineart.png",
        "https://example.test/ref1.png": "uploaded_ref1.png",
        "https://example.test/ref2.png": "uploaded_ref2.png",
    }[url]
    provider._upload_image = upload_mock  # type: ignore[method-assign]

    request = ChatRequest(
        provider="runninghub_workflow",
        model="wf-001",
        messages=[ChatMessage(role="user", content="anime cat")],
        metadata={
            "node_mapping": {
                "images": ["141", "139", "140"],
                "text": {"nodeId": "150", "fieldName": "text"},
            },
            "image_urls": [
                "https://example.test/lineart.png",
                "https://example.test/ref1.png",
                "https://example.test/ref2.png",
            ],
        },
    )

    await provider.chat(request)

    # Verify upload was called for each image
    assert upload_mock.call_count == 3
    upload_mock.assert_any_call("https://example.test/lineart.png")
    upload_mock.assert_any_call("https://example.test/ref1.png")
    upload_mock.assert_any_call("https://example.test/ref2.png")


# ---------------------------------------------------------------------------
# Test 3: nodeInfoList structure is built correctly
# ---------------------------------------------------------------------------
async def test_workflow_provider_builds_nodeinfo_list() -> None:
    from xiagent.models.providers.runninghub import RunningHubWorkflowProvider

    http_client = FakeWorkflowHttpClient(
        [
            {
                "taskId": "workflow-task-2",
                "status": "RUNNING",
                "results": None,
            },
            {
                "taskId": "workflow-task-2",
                "status": "SUCCESS",
                "results": [{"url": "https://cdn.test/output2.png"}],
            },
        ]
    )
    provider = RunningHubWorkflowProvider(
        config=RunningHubWorkflowModelConfig(
            api_key="test-key",
            base_url="https://runninghub.test",
            workflow_id="wf-002",
            instance_type="gpu",
            use_personal_queue=True,
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )

    upload_mock = AsyncMock()
    upload_mock.side_effect = lambda url: {
        "https://example.test/lineart.png": "up_lineart.png",
        "https://example.test/ref1.png": "up_ref1.png",
        "https://example.test/ref3.png": "up_ref3.png",
    }[url]
    provider._upload_image = upload_mock  # type: ignore[method-assign]

    request = ChatRequest(
        provider="runninghub_workflow",
        model="wf-002",
        messages=[ChatMessage(role="user", content="dramatic landscape")],
        metadata={
            "node_mapping": {
                "images": ["141", "139", "140"],
                "text": {"nodeId": "150", "fieldName": "text"},
            },
            "image_urls": [
                "https://example.test/lineart.png",
                "https://example.test/ref1.png",
                "https://example.test/ref3.png",
            ],
        },
    )

    await provider.chat(request)

    assert len(http_client.calls) == 2  # submit + poll
    submit_payload = http_client.calls[0]["payload"]

    # Verify top-level fields
    assert submit_payload["instanceType"] == "gpu"
    assert submit_payload["usePersonalQueue"] == "true"

    # Verify nodeInfoList structure
    node_list = submit_payload["nodeInfoList"]
    assert isinstance(node_list, list)

    # Should contain: line_art (141), ref1 (139), ref3 (140), caption (150)
    node_ids = [n["nodeId"] for n in node_list]
    assert "141" in node_ids  # line_art
    assert "150" in node_ids  # caption/text
    assert "139" in node_ids  # ref_image_0 (ref1)
    assert "140" in node_ids  # ref_image_1 (ref3)

    # Verify line_art node
    line_art_node = next(n for n in node_list if n["nodeId"] == "141")
    assert line_art_node["fieldName"] == "image"
    assert line_art_node["fieldValue"] == "up_lineart.png"

    # Verify caption node
    caption_node = next(n for n in node_list if n["nodeId"] == "150")
    assert caption_node["fieldName"] == "text"
    assert caption_node["fieldValue"] == "dramatic landscape"

    # Verify ref node 0
    ref0_node = next(n for n in node_list if n["nodeId"] == "139")
    assert ref0_node["fieldValue"] == "up_ref1.png"

    # Verify ref node 1
    ref1_node = next(n for n in node_list if n["nodeId"] == "140")
    assert ref1_node["fieldValue"] == "up_ref3.png"


# ---------------------------------------------------------------------------
# Test 4: Submit → poll → return ChatResponse
# ---------------------------------------------------------------------------
async def test_workflow_provider_submits_and_polls() -> None:
    from xiagent.models.providers.runninghub import RunningHubWorkflowProvider

    http_client = FakeWorkflowHttpClient(
        [
            {
                "taskId": "workflow-task-3",
                "status": "RUNNING",
                "results": None,
            },
            {
                "taskId": "workflow-task-3",
                "status": "SUCCESS",
                "results": [
                    {"url": "https://cdn.test/final.png", "outputType": "png"}
                ],
                "usage": {"consumeCoins": "5"},
            },
        ]
    )
    provider = RunningHubWorkflowProvider(
        config=RunningHubWorkflowModelConfig(
            api_key="test-key",
            base_url="https://runninghub.test",
            workflow_id="wf-003",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )

    upload_mock = AsyncMock(return_value="uploaded_file.png")
    provider._upload_image = upload_mock  # type: ignore[method-assign]

    request = ChatRequest(
        provider="runninghub_workflow",
        model="wf-003",
        messages=[ChatMessage(role="user", content="samurai cat")],
        metadata={
            "node_mapping": {
                "images": ["141", "139"],
                "text": {"nodeId": "150", "fieldName": "text"},
            },
            "image_urls": [
                "https://example.test/line.png",
                "https://example.test/ref.png",
            ],
        },
    )

    response = await provider.chat(request)

    # Verify submit call URL
    assert http_client.calls[0]["url"] == (
        "https://runninghub.test/openapi/v2/run/ai-app/wf-003"
    )
    assert http_client.calls[0]["headers"]["Authorization"] == "Bearer test-key"

    # Verify poll call
    assert http_client.calls[1]["url"] == "https://runninghub.test/openapi/v2/query"
    assert http_client.calls[1]["payload"] == {"taskId": "workflow-task-3"}

    # Verify ChatResponse
    assert response.text == "https://cdn.test/final.png"
    assert response.model == "wf-003"
    assert response.usage == {"consumeCoins": "5"}
    assert response.metadata["provider"] == "runninghub_workflow"
    assert response.metadata["task_id"] == "workflow-task-3"
    assert response.metadata["status"] == "SUCCESS"
    assert response.metadata["results"] == [
        {"url": "https://cdn.test/final.png", "outputType": "png"}
    ]
    assert "test-key" not in str(response.metadata)


# ---------------------------------------------------------------------------
# Test 5: Upload failure raises ExternalServiceError
# ---------------------------------------------------------------------------
async def test_workflow_provider_handles_upload_failure() -> None:
    from xiagent.models.providers.runninghub import RunningHubWorkflowProvider

    provider = RunningHubWorkflowProvider(
        config=RunningHubWorkflowModelConfig(
            api_key="test-key",
            base_url="https://runninghub.test",
            workflow_id="wf-004",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
    )

    upload_mock = AsyncMock(
        side_effect=ExternalServiceError(
            code="runninghub_workflow_upload_failed",
            message="Failed to upload image to RunningHub",
        )
    )
    provider._upload_image = upload_mock  # type: ignore[method-assign]

    request = ChatRequest(
        provider="runninghub_workflow",
        model="wf-004",
        messages=[ChatMessage(role="user", content="test")],
        metadata={
            "node_mapping": {
                "images": ["141", "139"],
                "text": {"nodeId": "150", "fieldName": "text"},
            },
            "image_urls": [
                "https://example.test/broken.png",
                "https://example.test/ref.png",
            ],
        },
    )

    with pytest.raises(ExternalServiceError) as exc:
        await provider.chat(request)

    assert exc.value.code == "runninghub_workflow_upload_failed"


# ---------------------------------------------------------------------------
# Test 6: V3 node integration — full submit → poll → result via provider chain
# ---------------------------------------------------------------------------
async def test_v3_integration_full_submit_poll_flow() -> None:
    from xiagent.models.providers.runninghub import RunningHubWorkflowProvider
    from xiagent.models.router import ChatModelRouter
    from xiagent.models.types import RunningHubWorkflowModelConfig
    from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNodeV3

    http_client = FakeWorkflowHttpClient(
        [
            {
                "taskId": "v3-integration-task",
                "status": "RUNNING",
                "results": None,
                "usage": None,
            },
            {
                "taskId": "v3-integration-task",
                "status": "SUCCESS",
                "results": [
                    {"url": "https://cdn.test/v3_integrated_output.png", "outputType": "png"}
                ],
                "usage": {"consumeCoins": "8"},
            },
        ]
    )
    provider = RunningHubWorkflowProvider(
        config=RunningHubWorkflowModelConfig(
            api_key="test-key",
            base_url="https://runninghub.test",
            workflow_id="wf-v3-integration",
            poll_interval_seconds=0,
            poll_timeout_seconds=1,
        ),
        http_client=http_client,
    )

    upload_mock = AsyncMock()
    upload_mock.side_effect = lambda url: {
        "https://example.test/lineart_v3.png": "up_lineart_v3.png",
        "https://example.test/ref_v3.png": "up_ref_v3.png",
    }[url]
    provider._upload_image = upload_mock  # type: ignore[method-assign]

    router = ChatModelRouter()
    router.register_provider("runninghub_workflow", provider)

    node = RunningHubImageToImageNodeV3(
        model_router=router,
        provider="runninghub_workflow",
        model="wf-v3-integration",
    )

    result = await node.run(
        None,
        {
            "prompt": "anime cat in V3 workflow style",
            "image_urls": ["https://example.test/ref_v3.png"],
            "line_art_url": "https://example.test/lineart_v3.png",
            "poll_interval_seconds": 0,
            "poll_timeout_seconds": 1,
        },
    )

    # Verify node result
    assert result.status == "succeeded"
    assert result.output["image_url"] == "https://cdn.test/v3_integrated_output.png"
    assert result.output["model"] == "wf-v3-integration"
    assert result.output["usage"] == {"consumeCoins": "8"}
    assert result.output["task_id"] == "v3-integration-task"
    assert result.output["status"] == "SUCCESS"
    assert result.output["results"] == [
        {"url": "https://cdn.test/v3_integrated_output.png", "output_type": "png"}
    ]
    assert result.metadata["provider"] == "runninghub_workflow"

    # Verify HTTP chain: submit → poll
    assert len(http_client.calls) == 2
    submit_url = http_client.calls[0]["url"]
    poll_url = http_client.calls[1]["url"]
    assert submit_url.endswith("/openapi/v2/run/ai-app/wf-v3-integration")
    assert "/openapi/v2/query" in poll_url

    # Verify upload was called for both line_art_url and image_urls
    assert upload_mock.call_count == 2

    # Verify nodeInfoList payload
    submit_payload = http_client.calls[0]["payload"]
    node_ids = [n["nodeId"] for n in submit_payload["nodeInfoList"]]
    assert "81" in node_ids  # line_art (first image slot in default mapping)
    assert "141" in node_ids  # ref image (second image slot)
    assert "150" in node_ids  # caption/text
