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

    @abstractmethod
    async def get_asset_thumbnail(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
        size: int = 256,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def search_assets(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        keyword: str | None = None,
        asset_type: str | None = None,
        mime_type: str | None = None,
        names: list[str] | None = None,
        tag_ids: list[str] | None = None,
        tag_names: list[str] | None = None,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def create_text_asset(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        name: str,
        text: str,
        metadata: dict[str, Any],
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def update_text_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        name: str,
        text: str,
        metadata: dict[str, Any],
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def import_file_asset(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        file_name: str,
        content_type: str | None,
        content: bytes,
        metadata: dict[str, Any],
        publish: bool = False,
        collection_ids: list[str] | None = None,
        tag_ids: list[str] | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def copy_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        target_scope: str,
        target_project_id: str | None,
        source_project_id: str | None = None,
        copy_tags: bool = True,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def move_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        target_scope: str,
        target_project_id: str | None,
        source_project_id: str | None = None,
        copy_tags: bool = True,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def update_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def replace_asset_file(
        self,
        *,
        user_id: str,
        asset_id: str,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def create_collection_node(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        parent_id: str | None,
        name: str,
        description: str | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def list_collection_nodes(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def update_collection_node(
        self,
        *,
        user_id: str,
        collection_id: str,
        name: str,
        description: str | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def delete_collection_node(
        self,
        *,
        user_id: str,
        collection_id: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def create_tag(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        name: str,
        description: str | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def list_tags(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def update_tag(
        self,
        *,
        user_id: str,
        tag_id: str,
        name: str,
        description: str | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def delete_tag(
        self,
        *,
        user_id: str,
        tag_id: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_asset_tags(
        self,
        *,
        user_id: str,
        asset_id: str,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def attach_asset_tag(
        self,
        *,
        user_id: str,
        asset_id: str,
        tag_id: str,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def detach_asset_tag(
        self,
        *,
        user_id: str,
        asset_id: str,
        tag_id: str,
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
