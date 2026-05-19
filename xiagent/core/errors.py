from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class XiAgentError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.code, self.message)

    def __reduce__(self) -> tuple[type[XiAgentError], tuple[str, str, dict[str, Any]]]:
        return (self.__class__, (self.code, self.message, self.details))

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
