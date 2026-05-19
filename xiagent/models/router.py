from __future__ import annotations

from abc import ABC, abstractmethod

from xiagent.core.errors import NotFoundError
from xiagent.models.types import ChatRequest, ChatResponse


class ChatModelProvider(ABC):
    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError


class ChatModelRouter:
    def __init__(self) -> None:
        self._providers: dict[str, ChatModelProvider] = {}

    def register_provider(self, name: str, provider: ChatModelProvider) -> None:
        if not isinstance(provider, ChatModelProvider):
            raise TypeError("provider must inherit ChatModelProvider")
        self._providers[name] = provider

    async def chat(self, request: ChatRequest) -> ChatResponse:
        provider = self._providers.get(request.provider)
        if provider is None:
            raise NotFoundError(
                code="model_provider_not_found",
                message="Model provider not found",
                details={"provider": request.provider},
            )
        return await provider.chat(request)
