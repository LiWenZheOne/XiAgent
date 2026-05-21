from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.request import Request, urlopen

from xiagent.core.errors import ExternalServiceError, ValidationError, XiAgentError
from xiagent.models.router import ChatModelProvider
from xiagent.models.types import (
    ChatRequest,
    ChatResponse,
    RunningHubImageModelConfig,
    RunningHubTextToImageModelConfig,
)

IMAGE_PROVIDER_NAME = "runninghub_image"
TEXT_TO_IMAGE_PROVIDER_NAME = "runninghub_text_to_image"


class _UrllibJsonClient:
    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._post_json_sync,
            url,
            headers=headers,
            payload=payload,
        )

    def _post_json_sync(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            raw = response.read()
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("RunningHub response must be a JSON object")
        return decoded


class RunningHubImageProvider(ChatModelProvider):
    _provider_name = IMAGE_PROVIDER_NAME
    _invalid_response_code = "runninghub_image_invalid_response"
    _request_failed_code = "runninghub_image_request_failed"
    _result_missing_code = "runninghub_image_result_missing"
    _timeout_code = "runninghub_image_timeout"

    def __init__(
        self,
        *,
        config: RunningHubImageModelConfig,
        http_client: Any | None = None,
    ) -> None:
        self._config = config
        self._http_client = http_client or _UrllibJsonClient()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._validate_config()
        payload = self._request_payload(request)

        try:
            submission = await self._post_json(self._task_url(), payload)
            result = await self._poll_until_complete(submission, request.metadata)
        except XiAgentError:
            raise
        except Exception as exc:
            raise ExternalServiceError(
                code=self._request_failed_code,
                message="RunningHub image request failed",
                details={"provider": self._provider_name, "endpoint": self._config.endpoint},
            ) from exc

        return self._chat_response(request=request, result=result)

    def _validate_config(self) -> None:
        if not self._config.api_key:
            raise ValidationError(
                code="runninghub_api_key_missing",
                message="RunningHub API key is not configured",
                details={"provider": self._provider_name},
            )

    def _request_payload(self, request: ChatRequest) -> dict[str, Any]:
        prompt = self._prompt(request)
        image_urls = self._image_urls(request.metadata)
        aspect_ratio = self._metadata_text(request.metadata, "aspect_ratio")
        aspect_ratio = (
            aspect_ratio or self._metadata_text(request.metadata, "aspectRatio") or "9:16"
        )
        resolution = self._metadata_text(request.metadata, "resolution") or "1k"
        return {
            "imageUrls": image_urls,
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
        }

    def _prompt(self, request: ChatRequest) -> str:
        metadata_prompt = self._metadata_text(request.metadata, "prompt")
        if metadata_prompt:
            return metadata_prompt
        prompt = "\n".join(
            message.content.strip() for message in request.messages if message.content.strip()
        )
        if not prompt:
            raise ValidationError(
                code="runninghub_prompt_missing",
                message="RunningHub image prompt is required",
                details={"provider": self._provider_name},
            )
        return prompt

    def _image_urls(self, metadata: dict[str, Any]) -> list[str]:
        value = metadata.get("image_urls", metadata.get("imageUrls"))
        if isinstance(value, str) and value:
            return [value]
        if isinstance(value, list):
            image_urls = [item for item in value if isinstance(item, str) and item]
            if image_urls:
                return image_urls
        image_url = self._metadata_text(metadata, "image_url")
        if image_url:
            return [image_url]
        raise ValidationError(
            code="runninghub_image_urls_missing",
            message="RunningHub image URLs are required",
            details={"provider": self._provider_name},
        )

    def _metadata_text(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) and value else None

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._http_client.post_json(
            url,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )

    async def _poll_until_complete(
        self,
        response: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        task_id = self._task_id(response)
        poll_timeout_seconds = self._metadata_float(
            metadata,
            "poll_timeout_seconds",
            self._config.poll_timeout_seconds,
        )
        poll_interval_seconds = self._metadata_float(
            metadata,
            "poll_interval_seconds",
            self._config.poll_interval_seconds,
        )
        deadline = time.monotonic() + max(0.0, poll_timeout_seconds)
        current = response
        while True:
            status = self._status(current)
            if status == "SUCCESS":
                return current
            if status == "FAILED":
                self._raise_failed(current)
            if current.get("results"):
                return current
            if not task_id:
                raise ExternalServiceError(
                    code=self._invalid_response_code,
                    message="RunningHub image response did not include a task id",
                    details={"provider": self._provider_name},
                )
            if time.monotonic() >= deadline:
                raise ExternalServiceError(
                    code=self._timeout_code,
                    message="RunningHub image request timed out",
                    details={
                        "provider": self._provider_name,
                        "task_id": task_id,
                        "poll_timeout_seconds": poll_timeout_seconds,
                        "last_status": status,
                    },
                )
            await asyncio.sleep(max(0.0, poll_interval_seconds))
            current = await self._post_json(self._query_url(), {"taskId": task_id})

    def _metadata_float(
        self,
        metadata: dict[str, Any],
        key: str,
        default: float,
    ) -> float:
        value = metadata.get(key)
        if isinstance(value, bool) or value is None:
            return default
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str) and value:
            try:
                return float(value)
            except ValueError:
                return default
        return default

    def _raise_failed(self, response: dict[str, Any]) -> None:
        details: dict[str, Any] = {
            "provider": self._provider_name,
            "status": "FAILED",
        }
        error_code = response.get("errorCode")
        if isinstance(error_code, str) and error_code:
            details["error_code"] = error_code
        raise ExternalServiceError(
            code=self._request_failed_code,
            message="RunningHub image request failed",
            details=details,
        )

    def _chat_response(self, *, request: ChatRequest, result: dict[str, Any]) -> ChatResponse:
        results = result.get("results")
        if not isinstance(results, list) or not results:
            raise ExternalServiceError(
                code=self._result_missing_code,
                message="RunningHub image response did not include results",
                details={"provider": self._provider_name, "task_id": self._task_id(result)},
            )
        first_result = results[0] if isinstance(results[0], dict) else {}
        text = self._result_text(result, first_result)
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        return ChatResponse(
            text=text,
            model=request.model or self._config.model,
            usage=usage,
            metadata={
                "provider": self._provider_name,
                "task_id": self._task_id(result),
                "status": self._status(result),
                "results": results,
            },
        )

    def _result_text(
        self,
        response: dict[str, Any],
        first_result: dict[str, Any],
    ) -> str:
        for key in ("url", "text"):
            value = first_result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        raise ExternalServiceError(
            code=self._result_missing_code,
            message="RunningHub image response result did not include a usable url or text",
            details={"provider": self._provider_name, "task_id": self._task_id(response)},
        )

    def _task_id(self, response: dict[str, Any]) -> str | None:
        task_id = response.get("taskId")
        return task_id if isinstance(task_id, str) and task_id else None

    def _status(self, response: dict[str, Any]) -> str:
        status = response.get("status")
        return status.upper() if isinstance(status, str) else ""

    def _task_url(self) -> str:
        endpoint = self._config.endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        if endpoint.startswith("/openapi/v2/"):
            return f"{self._base_url()}{endpoint}"
        return f"{self._base_url()}/openapi/v2{endpoint}"

    def _query_url(self) -> str:
        return f"{self._base_url()}/openapi/v2/query"

    def _base_url(self) -> str:
        return self._config.base_url.rstrip("/")


class RunningHubTextToImageProvider(RunningHubImageProvider):
    _provider_name = TEXT_TO_IMAGE_PROVIDER_NAME
    _invalid_response_code = "runninghub_text_to_image_invalid_response"
    _request_failed_code = "runninghub_text_to_image_request_failed"
    _result_missing_code = "runninghub_text_to_image_result_missing"
    _timeout_code = "runninghub_text_to_image_timeout"

    def __init__(
        self,
        *,
        config: RunningHubTextToImageModelConfig,
        http_client: Any | None = None,
    ) -> None:
        self._config = config
        self._http_client = http_client or _UrllibJsonClient()

    def _request_payload(self, request: ChatRequest) -> dict[str, Any]:
        aspect_ratio = self._metadata_text(request.metadata, "aspect_ratio")
        aspect_ratio = (
            aspect_ratio or self._metadata_text(request.metadata, "aspectRatio") or "9:16"
        )
        resolution = self._metadata_text(request.metadata, "resolution") or "1k"
        return {
            "prompt": self._prompt(request),
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
        }
