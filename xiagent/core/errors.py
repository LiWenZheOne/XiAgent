from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class XiAgentError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(XiAgentError):
    pass


class NotFoundError(XiAgentError):
    pass


class PermissionDeniedError(XiAgentError):
    pass


class ConflictError(XiAgentError):
    pass


class ExternalServiceError(XiAgentError):
    pass
