from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class UserService(ABC):
    @abstractmethod
    async def ensure_project_access(self, *, user_id: str, project_id: str, action: str) -> None:
        raise NotImplementedError


class AssetService(ABC):
    @abstractmethod
    async def get_asset(self, *, user_id: str, asset_id: str, project_id: str | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def get_asset_content(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> Any:
        raise NotImplementedError


class WorkflowService(ABC):
    @abstractmethod
    async def get_template(self, *, template_id: str, user_id: str, project_id: str) -> Any:
        raise NotImplementedError


class RuntimeService(ABC):
    @abstractmethod
    async def create_task(
        self,
        *,
        user_id: str,
        project_id: str,
        template_id: str,
        input_data: dict[str, Any],
    ) -> Any:
        raise NotImplementedError
