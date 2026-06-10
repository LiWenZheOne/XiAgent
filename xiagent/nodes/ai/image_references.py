from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from xiagent.core.services import AssetService
from xiagent.core.errors import ValidationError
from xiagent.nodes.base import NodeContext


def image_ref_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["asset", "data_uri"]},
            "asset_id": {"type": "string", "minLength": 1},
            "project_id": {"type": "string", "minLength": 1},
            "data": {"type": "string", "minLength": 1},
            "role": {"type": "string", "minLength": 1},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }


def image_refs_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": image_ref_schema(),
        "minItems": 1,
    }


async def resolve_image_ref(ctx: NodeContext | None, image_ref: Any) -> str:
    if ctx is None or ctx.asset_service is None:
        asset_service = None
        user_id = None
        project_id = None
    else:
        asset_service = ctx.asset_service
        user_id = ctx.user_id
        project_id = ctx.project_id
    return await resolve_image_ref_with_asset_service(
        user_id=user_id,
        project_id=project_id,
        asset_service=asset_service,
        image_ref=image_ref,
    )


async def resolve_image_ref_with_asset_service(
    *,
    user_id: str | None,
    project_id: str | None,
    asset_service: AssetService | None,
    image_ref: Any,
) -> str:
    if not isinstance(image_ref, Mapping):
        raise ValidationError(
            code="image_ref_invalid",
            message="Image reference must be an object",
        )
    kind = image_ref.get("kind")
    if kind == "data_uri":
        data = image_ref.get("data")
        if isinstance(data, str) and data.startswith("data:image/"):
            return data
        raise ValidationError(
            code="image_ref_data_uri_invalid",
            message="Image data URI must start with data:image/",
        )
    if kind == "asset":
        return await _resolve_asset_ref(
            user_id=user_id,
            project_id=project_id,
            asset_service=asset_service,
            image_ref=image_ref,
        )
    raise ValidationError(
        code="image_ref_invalid",
        message="Image reference kind must be asset or data_uri",
        details={"kind": kind},
    )


async def resolve_image_refs(ctx: NodeContext | None, image_refs: Any) -> list[str]:
    if not isinstance(image_refs, list) or not image_refs:
        raise ValidationError(
            code="image_refs_required",
            message="Image references must be a non-empty array",
        )
    return [await resolve_image_ref(ctx, image_ref) for image_ref in image_refs]


async def _resolve_asset_ref(
    *,
    user_id: str | None,
    project_id: str | None,
    asset_service: AssetService | None,
    image_ref: Mapping[str, Any],
) -> str:
    asset_id = image_ref.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ValidationError(
            code="image_ref_invalid",
            message="Asset image reference requires asset_id",
        )
    reference_project_id = image_ref.get("project_id")
    project_id_for_read = reference_project_id.strip() if isinstance(reference_project_id, str) and reference_project_id.strip() else project_id
    return await _asset_id_to_data_uri(
        user_id=user_id,
        project_id=project_id_for_read,
        asset_service=asset_service,
        asset_id=asset_id.strip(),
    )


async def _asset_id_to_data_uri(
    *,
    user_id: str | None,
    project_id: str | None,
    asset_service: AssetService | None,
    asset_id: str,
) -> str:
    if asset_service is None or user_id is None:
        raise ValidationError(
            code="image_ref_service_missing",
            message="AssetService is required to resolve asset image references",
        )
    asset = await asset_service.get_asset(
        user_id=user_id,
        asset_id=asset_id,
        project_id=project_id,
    )
    if project_id is None and getattr(asset, "scope", None) == "project":
        raise ValidationError(
            code="image_ref_project_scope_required",
            message="Project asset image references require project_id",
            details={"asset_id": asset_id},
        )
    content = await asset_service.get_asset_content(
        user_id=user_id,
        asset_id=asset_id,
        project_id=project_id,
    )
    bytes_content = getattr(content, "bytes_content", None)
    if not isinstance(bytes_content, bytes) or not bytes_content:
        raise ValidationError(
            code="image_ref_content_missing",
            message="Asset image reference does not contain file bytes",
            details={"asset_id": asset_id},
        )
    content_type = getattr(content, "content_type", None)
    mime_type = content_type if isinstance(content_type, str) and content_type.startswith("image/") else "image/png"
    encoded = base64.b64encode(bytes_content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
