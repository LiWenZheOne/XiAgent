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
    model: str = "nano-banana2-gemini31flash/image-to-image-channel-low-price"
    endpoint: str = "/rhart-image-n-g31-flash/image-to-image"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 180.0


@dataclass(frozen=True, slots=True)
class RunningHubTextToImageModelConfig:
    api_key: str | None = None
    base_url: str = "https://www.runninghub.ai"
    model: str = "nano-banana-pro/text-to-image-channel-low-price"
    endpoint: str = "/rhart-image-n-pro/text-to-image"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 180.0


@dataclass(frozen=True, slots=True)
class GeminiModelConfig:
    api_key: str | None = None
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
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
    gemini: GeminiModelConfig = field(default_factory=GeminiModelConfig)
