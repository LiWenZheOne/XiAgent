from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from openai import AsyncOpenAI

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class DeepSeekChatNode(BaseNode):
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client_factory = client_factory or AsyncOpenAI

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="ai.deepseek_chat.v1",
            name="DeepSeek Chat",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "system": {"type": "string"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "model": {"type": "string"},
                    "usage": {"type": "object"},
                },
                "required": ["text", "model", "usage"],
                "additionalProperties": False,
            },
            description="调用 DeepSeek Chat API 生成文本回复。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if not self._api_key:
            raise ValidationError(
                code="deepseek_api_key_missing",
                message="DeepSeek API key 未配置",
            )

        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(
                code="deepseek_prompt_required",
                message="DeepSeek prompt 不能为空",
            )

        messages: list[dict[str, str]] = []
        system = inputs.get("system")
        if isinstance(system, str) and system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with self._client_factory(
                api_key=self._api_key,
                base_url=self._base_url,
            ) as client:
                response = await client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    stream=False,
                    extra_body={"thinking": {"type": "disabled"}},
                )
        except Exception as exc:
            raise ExternalServiceError(
                code="deepseek_request_failed",
                message="DeepSeek 请求失败",
                details={"provider": "deepseek", "base_url": self._base_url},
            ) from exc

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message.content else ""
        usage = response.usage.model_dump() if response.usage else {}
        return NodeResult(
            status="succeeded",
            output={"text": content, "model": response.model, "usage": usage},
            metadata={"provider": "deepseek", "base_url": self._base_url},
        )
