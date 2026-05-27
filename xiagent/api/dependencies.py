from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request

from xiagent.assets.service import SqliteAssetService
from xiagent.core.errors import AuthenticationError, NotFoundError, ValidationError
from xiagent.infrastructure.config import Settings
from xiagent.infrastructure.object_storage import (
    DisabledObjectStorageService,
    LocalPublicUrlObjectStorageService,
    ObjectStorageRouter,
    load_object_storage_config,
)
from xiagent.infrastructure.object_storage.qiniu import QiniuObjectStorageService
from xiagent.nodes import build_node_registry
from xiagent.nodes.registry import NodeRegistry
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.models import UserRecord
from xiagent.users.service import SqliteUserService
from xiagent.workflows.service import WorkflowCatalog


@dataclass(slots=True)
class ApiServices:
    users: SqliteUserService
    assets: SqliteAssetService
    node_registry: NodeRegistry
    runtime: SqliteRuntimeService
    workflows: WorkflowCatalog
    access_tokens: dict[str, str] = field(default_factory=dict)

    def issue_access_token(self, *, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.access_tokens[token] = user_id
        return token


def build_services(settings: Settings) -> ApiServices:
    users = SqliteUserService(settings.database_path)
    object_storage_config = load_object_storage_config()
    object_storage = ObjectStorageRouter(
        provider=object_storage_config.provider,
        services={
            "local_none": DisabledObjectStorageService(),
            "local_public_url": LocalPublicUrlObjectStorageService(),
            "qiniu": QiniuObjectStorageService(object_storage_config.qiniu),
        },
    )
    assets = SqliteAssetService(
        database_path=settings.database_path,
        storage_dir=settings.asset_storage_dir,
        user_service=users,
        object_storage=object_storage,
    )
    node_registry = build_node_registry(settings)
    runtime = SqliteRuntimeService(
        database_path=settings.database_path,
        user_service=users,
        node_registry=node_registry,
        asset_service=assets,
    )
    workflows = WorkflowCatalog(node_registry)
    if settings.workflow_dir.exists():
        workflows.load_directory(settings.workflow_dir)
    return ApiServices(
        users=users,
        assets=assets,
        node_registry=node_registry,
        runtime=runtime,
        workflows=workflows,
    )


def get_services(request: Request) -> ApiServices:
    return request.app.state.services


async def get_current_user(
    request: Request,
    services: Annotated[ApiServices, Depends(get_services)],
    authorization: Annotated[str | None, Header()] = None,
) -> UserRecord:
    if "user_id" in request.query_params:
        raise ValidationError(
            code="unsupported_user_id_parameter",
            message="user_id query parameter is not supported for protected routes",
            details={},
        )
    token = _bearer_token(authorization)
    user_id = services.access_tokens.get(token)
    if user_id is None:
        raise _invalid_access_token()
    try:
        return await services.users.get_user(user_id=user_id)
    except NotFoundError as exc:
        raise _invalid_access_token() from exc


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _invalid_access_token()
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise _invalid_access_token()
    return token.strip()


def _invalid_access_token() -> AuthenticationError:
    return AuthenticationError(
        code="invalid_access_token",
        message="Access token is missing or invalid",
    )
