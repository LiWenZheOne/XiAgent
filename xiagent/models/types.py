from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str | list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ChatRequest:
    provider: str
    model: str
    messages: list[ChatMessage]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChatResponse:
    text: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeepSeekModelConfig:
    api_key: str | None = None
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


@dataclass(frozen=True, slots=True)
class RunningHubImageModelConfig:
    api_key: str | None = None
    base_url: str = "https://www.runninghub.ai"
    model: str = "nano-banana-pro/edit"
    endpoint: str = "/rhart-image-n-pro/edit"
    default_aspect_ratio: str = "9:16"
    default_resolution: str = "1k"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 180.0


@dataclass(frozen=True, slots=True)
class RunningHubTextToImageModelConfig:
    api_key: str | None = None
    base_url: str = "https://www.runninghub.ai"
    model: str = "nano-banana-pro/text-to-image-channel-low-price"
    endpoint: str = "/rhart-image-n-pro/text-to-image"
    default_aspect_ratio: str = "9:16"
    default_resolution: str = "1k"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 180.0


@dataclass(frozen=True, slots=True)
class RunningHubWorkflowModelConfig:
    api_key: str | None = None
    base_url: str = "https://www.runninghub.ai"
    workflow_id: str | None = None
    api_prefix: str = "/openapi/v2"
    http_timeout_seconds: float = 60.0
    upload_timeout_seconds: float = 30.0
    instance_type: str = "default"
    use_personal_queue: bool = False
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 180.0


@dataclass(frozen=True, slots=True)
class OpenAICompatibleModelConfig:
    api_key: str | None = None
    base_url: str = "https://api.vectorengine.cn"
    model: str = "gemini-3-flash-preview"


@dataclass(frozen=True, slots=True)
class ModelConfig:
    deepseek: DeepSeekModelConfig = field(default_factory=DeepSeekModelConfig)
    runninghub_image: RunningHubImageModelConfig = field(
        default_factory=RunningHubImageModelConfig
    )
    runninghub_text_to_image: RunningHubTextToImageModelConfig = field(
        default_factory=RunningHubTextToImageModelConfig
    )
    runninghub_workflow: RunningHubWorkflowModelConfig = field(
        default_factory=RunningHubWorkflowModelConfig
    )
    openai_compatible: OpenAICompatibleModelConfig = field(default_factory=OpenAICompatibleModelConfig)
