from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.nodes.base import AssetRef, BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.tools.asset_identity import normalize_asset_record


class EpisodeMetadataFinalizeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.episode_metadata_finalize.v1",
            name="Finalize Episode Metadata",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["episode_name", "episode_summary", "source_script", "asset_catalog"],
                "properties": {
                    "episode_name": {"type": "string", "minLength": 1},
                    "episode_summary": {"type": "string", "minLength": 1},
                    "source_script": {"type": "string", "minLength": 1},
                    "background": {"type": "string"},
                    "asset_catalog": {"type": "object"},
                    "asset_images": {"type": "array", "items": {"type": "object"}},
                    "prompt_results": {"type": "array", "items": {"type": "object"}},
                    "generation_summary": {"type": "object"},
                    "decision": {"type": "string"},
                    "scope": {"type": "string", "enum": ["global", "project"]},
                },
                "additionalProperties": True,
            },
            output_schema=_episode_output_schema(),
            description="保存集剧情概括、原剧本内容和完整资产目录为集元数据文字资产。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None or ctx.asset_service is None:
            raise ValidationError(
                code="episode_metadata_no_context",
                message="AssetService is not available in context",
            )

        episode_name = _required_text(inputs.get("episode_name"), "episode_name_required", "集名称不能为空。")
        episode_summary = _required_text(inputs.get("episode_summary"), "episode_summary_required", "集剧情概括不能为空。")
        source_script = _required_text(inputs.get("source_script"), "episode_source_script_required", "原剧本内容不能为空。")
        scope = _scope(inputs.get("scope"))
        asset_catalog = _normalize_asset_catalog(_object(inputs.get("asset_catalog")))
        asset_images = _normalize_records(_object_list(inputs.get("asset_images")))
        prompt_results = _normalize_records(_object_list(inputs.get("prompt_results")))
        generation_summary = _object(inputs.get("generation_summary"))

        complete_asset_catalog = {
            "approved_assets": asset_catalog,
            "asset_images": asset_images,
            "prompt_results": prompt_results,
            "generation_summary": generation_summary,
        }
        background = _optional_text(inputs.get("background"))
        payload = {
            "episode_name": episode_name,
            "episode_summary": episode_summary,
            "source_script": source_script,
            "background": background,
            "asset_catalog": complete_asset_catalog,
            "source_task_id": ctx.task_id,
            "source_workflow_node_id": ctx.node_id,
        }
        metadata = {
            "type": "episode_metadata",
            "episode_name": episode_name,
            "episode_summary": episode_summary,
            "source_task_id": ctx.task_id,
        }
        record = await _save_episode_metadata_asset(
            ctx,
            scope=scope,
            episode_name=episode_name,
            text=json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            metadata=metadata,
        )
        output = {
            "episode_name": episode_name,
            "episode_summary": episode_summary,
            "source_script": source_script,
            "background": background,
            "asset_catalog": complete_asset_catalog,
            "asset_images": asset_images,
            "generation_summary": generation_summary,
            "episode_asset_id": record.asset_id,
        }
        return NodeResult(
            status="succeeded",
            output=output,
            asset_refs=[AssetRef(asset_id=record.asset_id, usage_type="episode_metadata", source=ctx.node_id)],
        )


async def _save_episode_metadata_asset(
    ctx: NodeContext,
    *,
    scope: str,
    episode_name: str,
    text: str,
    metadata: dict[str, Any],
) -> Any:
    project_id = ctx.project_id if scope == "project" else None
    existing = await _find_episode_metadata_asset(ctx, scope=scope, project_id=project_id, episode_name=episode_name)
    if existing is not None:
        return await ctx.asset_service.update_text_asset(
            user_id=ctx.user_id,
            asset_id=existing.asset_id,
            name=episode_name,
            text=text,
            metadata=metadata,
        )
    return await ctx.asset_service.create_text_asset(
        user_id=ctx.user_id,
        scope=scope,
        project_id=project_id,
        name=episode_name,
        text=text,
        metadata=metadata,
    )


async def _find_episode_metadata_asset(
    ctx: NodeContext,
    *,
    scope: str,
    project_id: str | None,
    episode_name: str,
) -> Any | None:
    result = await ctx.asset_service.search_assets(
        user_id=ctx.user_id,
        scope=scope,
        project_id=project_id,
        keyword=episode_name,
        asset_type="text",
        limit=20,
    )
    for asset in getattr(result, "items", []):
        if getattr(asset, "name", "") != episode_name:
            continue
        metadata = getattr(asset, "metadata", {})
        if isinstance(metadata, dict) and metadata.get("type") == "episode_metadata":
            return asset
    return None


class EpisodeMetadataFromAssetNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.episode_metadata_from_asset.v1",
            name="Load Episode Metadata",
            version="1.0.0",
            kind="tool",
            input_schema={
                "type": "object",
                "required": ["episode_asset_id"],
                "properties": {
                    "episode_asset_id": {"type": "string", "minLength": 1},
                    "no_material": {"type": "boolean"},
                    "enrich_description": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            output_schema=_episode_output_schema(),
            description="从集元数据文字资产读取集名称、剧情概括、原剧本和资产目录。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None or ctx.asset_service is None:
            raise ValidationError(
                code="episode_metadata_no_context",
                message="AssetService is not available in context",
            )
        episode_asset_id = _required_text(inputs.get("episode_asset_id"), "episode_asset_id_required", "集信息资产不能为空。")
        asset = await ctx.asset_service.get_asset(
            user_id=ctx.user_id,
            asset_id=episode_asset_id,
            project_id=ctx.project_id,
        )
        content = await ctx.asset_service.get_asset_content(
            user_id=ctx.user_id,
            asset_id=episode_asset_id,
            project_id=ctx.project_id,
        )
        payload = _parse_episode_payload(content.text_content, asset.metadata)
        output = {
            "episode_name": _text(payload.get("episode_name")) or asset.name,
            "episode_summary": _text(payload.get("episode_summary")),
            "source_script": _text(payload.get("source_script")),
            "background": _text(payload.get("background")),
            "asset_catalog": _object(payload.get("asset_catalog")),
            "generation_summary": _object(_object(payload.get("asset_catalog")).get("generation_summary")),
            "episode_asset_id": episode_asset_id,
            "storyboard_options": {
                "no_material": _bool(inputs.get("no_material")),
                "enrich_description": _bool(inputs.get("enrich_description")),
            },
        }
        if not output["source_script"]:
            raise ValidationError(
                code="episode_metadata_source_script_missing",
                message="集信息资产缺少原剧本内容。",
                details={"asset_id": episode_asset_id},
            )
        return NodeResult(
            status="succeeded",
            output=output,
            asset_refs=[AssetRef(asset_id=episode_asset_id, usage_type="episode_metadata", source=ctx.node_id)],
        )


def _episode_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["episode_name", "episode_summary", "source_script", "asset_catalog", "episode_asset_id"],
        "properties": {
            "episode_name": {"type": "string", "minLength": 1},
            "episode_summary": {"type": "string"},
            "source_script": {"type": "string", "minLength": 1},
            "background": {"type": "string"},
            "asset_catalog": {"type": "object", "additionalProperties": True},
            "asset_images": {"type": "array", "items": {"type": "object"}},
            "generation_summary": {"type": "object", "additionalProperties": True},
            "episode_asset_id": {"type": "string", "minLength": 1},
            "storyboard_options": {
                "type": "object",
                "properties": {
                    "no_material": {"type": "boolean"},
                    "enrich_description": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _normalize_asset_catalog(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key, default_type in (("characters", "character"), ("assets", "scene"), ("props", "prop")):
        items = result.get(key)
        if isinstance(items, list):
            result[key] = [
                normalize_asset_record(item, default_asset_type=default_type)
                if isinstance(item, Mapping)
                else item
                for item in items
            ]
    return result


def _normalize_records(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_asset_record(item) for item in items]


def _parse_episode_payload(text: str | None, metadata: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(text, str) and text.strip():
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                code="episode_metadata_json_invalid",
                message="集信息资产内容不是合法 JSON。",
            ) from exc
        if isinstance(parsed, dict):
            return parsed
    return dict(metadata)


def _required_text(value: Any, code: str, message: str) -> str:
    text = _text(value)
    if not text:
        raise ValidationError(code=code, message=message)
    return text


def _optional_text(value: Any) -> str:
    return _text(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _bool(value: Any) -> bool:
    return value is True


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _scope(value: Any) -> str:
    if value is None:
        return "project"
    if value in {"global", "project"}:
        return str(value)
    raise ValidationError(
        code="episode_metadata_scope_invalid",
        message="scope must be global or project",
        details={"scope": value},
    )
