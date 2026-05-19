from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


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
class ModelConfig:
    deepseek: DeepSeekModelConfig = field(default_factory=DeepSeekModelConfig)
