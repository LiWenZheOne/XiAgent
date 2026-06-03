from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.request import Request, urlopen

from xiagent.core.errors import ExternalServiceError, ValidationError, XiAgentError
from xiagent.infrastructure.api_logging import log_api_request, log_api_response
from xiagent.models.router import ChatModelProvider
from xiagent.models.types import (
    ChatRequest,
    ChatResponse,
    RunningHubImageModelConfig,
    RunningHubTextToImageModelConfig,
    RunningHubWorkflowModelConfig,
)

IMAGE_PROVIDER_NAME = "runninghub_image"
TEXT_TO_IMAGE_PROVIDER_NAME = "runninghub_text_to_image"


class _UrllibJsonClient:
    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout

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
        with urlopen(request, timeout=self._timeout) as response:
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
        timeout = getattr(config, "http_timeout_seconds", 60.0)
        self._http_client = http_client or _UrllibJsonClient(timeout=timeout)

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
        images = self._images(request.metadata)
        if not images:
            raise ValidationError(
                code="runninghub_images_missing",
                message="RunningHub image data URIs are required",
                details={"provider": self._provider_name},
            )
        aspect_ratio = self._metadata_text(request.metadata, "aspect_ratio")
        aspect_ratio = (
            aspect_ratio
            or self._metadata_text(request.metadata, "aspectRatio")
            or getattr(self._config, "default_aspect_ratio", "9:16")
        )
        resolution = (
            self._metadata_text(request.metadata, "resolution")
            or getattr(self._config, "default_resolution", "1k")
        )
        payload = {
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
            "imageUrls": images,
        }
        return payload

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

    def _images(self, metadata: dict[str, Any]) -> list[str]:
        value = metadata.get("images")
        if self._is_supported_image_input(value):
            return [value]
        if isinstance(value, list):
            images = [
                item
                for item in value
                if self._is_supported_image_input(item)
            ]
            if images:
                return images
        return []

    def _is_supported_image_input(self, value: Any) -> bool:
        return isinstance(value, str) and (
            value.startswith("data:image/")
            or value.startswith("http://")
            or value.startswith("https://")
        )

    def _metadata_text(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) and value else None

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        log_api_request(provider=self._provider_name, url=url, payload=payload)
        response = await self._http_client.post_json(
            url,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        log_api_response(provider=self._provider_name, url=url, payload=response)
        return response

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
            if self._error_code(current):
                self._raise_failed(current)
            if self._results(current):
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
            "status": self._status(response) or "FAILED",
        }
        error_code = self._error_code(response)
        if isinstance(error_code, str) and error_code:
            details["error_code"] = error_code
        error_message = self._error_message(response)
        if isinstance(error_message, str) and error_message:
            details["error_message"] = error_message
        raise ExternalServiceError(
            code=self._request_failed_code,
            message=error_message or "RunningHub image request failed",
            details=details,
        )

    def _chat_response(self, *, request: ChatRequest, result: dict[str, Any]) -> ChatResponse:
        results = self._results(result)
        if not isinstance(results, list) or not results:
            raise ExternalServiceError(
                code=self._result_missing_code,
                message="RunningHub image response did not include results",
                details={"provider": self._provider_name, "task_id": self._task_id(result)},
            )
        first_result = results[0] if isinstance(results[0], dict) else {}
        text = self._result_text(result, first_result)
        response_usage = self._response_value(result, "usage")
        usage = response_usage if isinstance(response_usage, dict) else {}
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
        task_id = self._response_value(response, "taskId", "task_id", "task_id_str", "id")
        return task_id if isinstance(task_id, str) and task_id else None

    def _status(self, response: dict[str, Any]) -> str:
        status = self._response_value(response, "status", "taskStatus")
        return status.upper() if isinstance(status, str) else ""

    def _results(self, response: dict[str, Any]) -> Any:
        return self._response_value(response, "results", "result", "outputs")

    def _error_code(self, response: dict[str, Any]) -> str | None:
        value = self._response_value(response, "errorCode", "error_code", "code")
        if value in (0, "0"):
            return None
        if isinstance(value, int):
            return str(value)
        return value if isinstance(value, str) and value else None

    def _error_message(self, response: dict[str, Any]) -> str | None:
        value = self._response_value(response, "errorMessage", "error_message", "message", "msg")
        return value if isinstance(value, str) and value else None

    def _response_value(self, response: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = response.get(key)
            if value not in (None, ""):
                return value
        data = response.get("data")
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if value not in (None, ""):
                    return value
        return None

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
        timeout = getattr(config, "http_timeout_seconds", 60.0)
        self._http_client = http_client or _UrllibJsonClient(timeout=timeout)

    def _request_payload(self, request: ChatRequest) -> dict[str, Any]:
        aspect_ratio = self._metadata_text(request.metadata, "aspect_ratio")
        aspect_ratio = (
            aspect_ratio
            or self._metadata_text(request.metadata, "aspectRatio")
            or getattr(self._config, "default_aspect_ratio", "9:16")
        )
        resolution = (
            self._metadata_text(request.metadata, "resolution")
            or getattr(self._config, "default_resolution", "1k")
        )
        return {
            "prompt": self._prompt(request),
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
        }


class RunningHubWorkflowProvider(ChatModelProvider):
    _provider_name = "runninghub_workflow"
    _request_failed_code = "runninghub_workflow_request_failed"
    _result_missing_code = "runninghub_workflow_result_missing"
    _timeout_code = "runninghub_workflow_timeout"

    def __init__(
        self,
        *,
        config: RunningHubWorkflowModelConfig,
        http_client: Any | None = None,
    ) -> None:
        self._config = config
        self._http_client = http_client or _UrllibJsonClient(timeout=config.http_timeout_seconds)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._validate_config()
        try:
            payload = await self._build_payload(request)
            submission = await self._post_json(self._task_url(), payload)
            result = await self._poll_until_complete(submission, request.metadata)
        except XiAgentError:
            raise
        except Exception as exc:
            raise ExternalServiceError(
                code=self._request_failed_code,
                message="RunningHub workflow request failed",
                details={"provider": self._provider_name},
            ) from exc

        return self._chat_response(request=request, result=result)

    async def _build_payload(self, request: ChatRequest) -> dict[str, Any]:
        mapping = request.metadata.get("node_mapping", {})
        image_ids = mapping.get("images", [])
        text_config = mapping.get("text", {})
        select_config = mapping.get("select", {})

        prompt = request.messages[0].content if request.messages else ""
        if not isinstance(prompt, str):
            prompt = ""

        all_urls = request.metadata.get("image_urls", [])
        if isinstance(all_urls, str):
            all_urls = [all_urls] if all_urls else []

        node_info_list: list[dict[str, Any]] = []

        # Images
        for i, url in enumerate(all_urls):
            if i >= len(image_ids):
                break
            if url:
                filename = await self._upload_image(url)
                node_info_list.append({
                    "nodeId": image_ids[i],
                    "fieldName": "image",
                    "fieldValue": filename,
                    "description": "image",
                })

        # Text
        if text_config:
            node_info_list.append({
                "nodeId": text_config.get("nodeId", ""),
                "fieldName": text_config.get("fieldName", "text"),
                "fieldValue": prompt,
                "description": "text",
            })

        # Select
        if select_config:
            count = str(len([u for u in all_urls if u]))
            for nid in select_config.get("nodeIds", []):
                node_info_list.append({
                    "nodeId": nid,
                    "fieldName": select_config.get("fieldName", "select"),
                    "fieldValue": count,
                    "description": "select",
                })

        return {
            "nodeInfoList": node_info_list,
            "instanceType": self._config.instance_type,
            "usePersonalQueue": "true" if self._config.use_personal_queue else "false",
        }

    async def _upload_image(self, file_url: str) -> str:
        """Upload image to RunningHub and return filename for fieldValue."""
        import httpx

        async with httpx.AsyncClient(timeout=self._config.upload_timeout_seconds) as client:
            # Download image
            resp = await client.get(file_url)
            resp.raise_for_status()
            image_data = resp.content

            # Upload to RunningHub
            upload_url = f"{self._base_url()}{self._config.api_prefix}/media/upload/binary"
            headers: dict[str, str] = {}
            if self._config.api_key:
                headers["Authorization"] = f"Bearer {self._config.api_key}"
            files = {"file": ("image.png", image_data, "image/png")}
            log_api_request(
                provider=self._provider_name,
                url=upload_url,
                payload={"file_name": "image.png", "size_bytes": len(image_data)},
            )
            resp = await client.post(upload_url, headers=headers, files=files)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            log_api_response(provider=self._provider_name, url=upload_url, payload=result)

        download_url = result.get("data", {}).get("download_url", "")
        if not download_url:
            raise ExternalServiceError(
                code="runninghub_workflow_upload_failed",
                message="Failed to upload image to RunningHub",
            )

        return download_url.split("/")[-1] if "/" in download_url else download_url

    def _validate_config(self) -> None:
        if not self._config.api_key:
            raise ValidationError(
                code="runninghub_workflow_api_key_missing",
                message="RunningHub workflow API key missing",
                details={"provider": self._provider_name},
            )
        if not self._config.workflow_id:
            raise ValidationError(
                code="runninghub_workflow_id_missing",
                message="RunningHub workflow ID is not configured",
                details={"provider": self._provider_name},
            )

    def _task_url(self) -> str:
        return f"{self._base_url()}{self._config.api_prefix}/run/ai-app/{self._config.workflow_id}"

    def _query_url(self) -> str:
        return f"{self._base_url()}{self._config.api_prefix}/query"

    def _base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    def _chat_response(
        self, *, request: ChatRequest, result: dict[str, Any]
    ) -> ChatResponse:
        results = result.get("results")
        first_result: dict[str, Any] = (
            results[0] if isinstance(results, list) and results else {}  # type: ignore[index]
        )
        text = ""
        for key in ("url", "text"):
            value = first_result.get(key)
            if isinstance(value, str) and value.strip():
                text = value
                break
        if not text:
            raise ExternalServiceError(
                code=self._result_missing_code,
                message="RunningHub workflow response result did not include a usable url or text",
                details={"provider": self._provider_name, "task_id": result.get("taskId")},
            )
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        return ChatResponse(
            text=text,
            model=request.model or self._config.workflow_id,
            usage=usage,
            metadata={
                "provider": self._provider_name,
                "task_id": self._task_id(result),
                "status": self._status(result),
                "results": results,
            },
        )

    # --- helpers reused from RunningHubImageProvider ---

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        log_api_request(provider=self._provider_name, url=url, payload=payload)
        response = await self._http_client.post_json(
            url,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        log_api_response(provider=self._provider_name, url=url, payload=response)
        return response

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
                    code="runninghub_workflow_invalid_response",
                    message="RunningHub workflow response did not include a task id",
                    details={"provider": self._provider_name},
                )
            if time.monotonic() >= deadline:
                raise ExternalServiceError(
                    code=self._timeout_code,
                    message="RunningHub workflow request timed out",
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
            message="RunningHub workflow request failed",
            details=details,
        )

    def _task_id(self, response: dict[str, Any]) -> str | None:
        task_id = response.get("taskId")
        return task_id if isinstance(task_id, str) and task_id else None

    def _status(self, response: dict[str, Any]) -> str:
        status = response.get("status")
        return status.upper() if isinstance(status, str) else ""

    def _metadata_text(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) and value else None
