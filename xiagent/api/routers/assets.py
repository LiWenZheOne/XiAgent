from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from xiagent.api.dependencies import ApiServices, get_current_user, get_services
from xiagent.core.errors import ValidationError
from xiagent.users.models import UserRecord

router = APIRouter(prefix="/api/assets", tags=["assets"])


class CreateTextAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    name: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    parent_id: str | None = None
    name: str
    description: str | None = None


class CreateTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    project_id: str | None = None
    name: str
    description: str | None = None


@router.post("/text")
async def create_text_asset(
    request: CreateTextAssetRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    asset = await services.assets.create_text_asset(
        user_id=current_user.user_id,
        scope=request.scope,
        project_id=request.project_id,
        name=request.name,
        text=request.text,
        metadata=request.metadata,
    )
    return asdict(asset)


@router.post("/files")
async def import_file_asset(
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    scope: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    collection_ids: Annotated[str | None, Form()] = None,
    tag_ids: Annotated[str | None, Form()] = None,
    publish: Annotated[bool, Form()] = True,
) -> dict:
    metadata = _metadata_from_json(metadata_json)
    content = await file.read()
    asset = await services.assets.import_file_asset(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        file_name=name or file.filename or "asset.bin",
        content_type=file.content_type,
        content=content,
        metadata=metadata,
        publish=publish,
        collection_ids=_split_ids(collection_ids),
        tag_ids=_split_ids(tag_ids),
    )
    return asdict(asset)


@router.post("/collections")
async def create_collection_node(
    request: CreateCollectionRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    collection = await services.assets.create_collection_node(
        user_id=current_user.user_id,
        scope=request.scope,
        project_id=request.project_id,
        parent_id=request.parent_id,
        name=request.name,
        description=request.description,
    )
    return asdict(collection)


@router.get("/collections")
async def list_collection_nodes(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    collections = await services.assets.list_collection_nodes(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
    )
    return {"items": [asdict(collection) for collection in collections]}


@router.post("/tags")
async def create_tag(
    request: CreateTagRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    tag = await services.assets.create_tag(
        user_id=current_user.user_id,
        scope=request.scope,
        project_id=request.project_id,
        name=request.name,
        description=request.description,
    )
    return asdict(tag)


@router.get("/tags")
async def list_tags(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    tags = await services.assets.list_tags(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
    )
    return {"items": [asdict(tag) for tag in tags]}


@router.get("/search")
async def search_assets(
    scope: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
    keyword: str | None = None,
    asset_type: str | None = None,
    mime_type: str | None = None,
    collection_id: str | None = None,
    tag_ids: str | None = None,
) -> dict:
    result = await services.assets.search_assets(
        user_id=current_user.user_id,
        scope=scope,
        project_id=project_id,
        keyword=keyword,
        asset_type=asset_type,
        mime_type=mime_type,
        collection_id=collection_id,
        tag_ids=_split_ids(tag_ids),
    )
    return {"items": [asdict(asset) for asset in result.items], "total": result.total}


@router.get("/{asset_id}")
async def get_asset(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> dict:
    asset = await services.assets.get_asset(
        user_id=current_user.user_id,
        asset_id=asset_id,
        project_id=project_id,
    )
    return asdict(asset)


@router.get("/{asset_id}/content")
async def get_asset_content(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: str | None = None,
) -> Response:
    content = await services.assets.get_asset_content(
        user_id=current_user.user_id,
        asset_id=asset_id,
        project_id=project_id,
    )
    if content.text_content is not None:
        return Response(content.text_content, media_type=content.content_type or "text/plain")
    return Response(content.bytes_content or b"", media_type=content.content_type)


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    await services.assets.delete_asset(user_id=current_user.user_id, asset_id=asset_id)
    return {"deleted": True}


def _metadata_from_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "invalid_asset_metadata",
            "Asset metadata_json must be a valid JSON object",
        ) from exc
    if not isinstance(parsed, dict):
        raise ValidationError(
            "invalid_asset_metadata",
            "Asset metadata_json must be a valid JSON object",
        )
    return parsed


def _split_ids(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
