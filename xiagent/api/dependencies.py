from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from xiagent.assets.service import SqliteAssetService
from xiagent.infrastructure.config import Settings
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.service import SqliteUserService
from xiagent.workflows.service import WorkflowCatalog


@dataclass(slots=True)
class ApiServices:
    users: SqliteUserService
    assets: SqliteAssetService
    node_registry: NodeRegistry
    runtime: SqliteRuntimeService
    workflows: WorkflowCatalog


def build_services(settings: Settings) -> ApiServices:
    users = SqliteUserService(settings.database_path)
    assets = SqliteAssetService(
        database_path=settings.database_path,
        storage_dir=settings.asset_storage_dir,
        user_service=users,
    )
    node_registry = NodeRegistry()
    node_registry.register(HumanApprovalNode())
    node_registry.register(EchoToolNode())
    node_registry.register(
        DeepSeekChatNode(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    )
    runtime = SqliteRuntimeService(
        database_path=settings.database_path,
        user_service=users,
        node_registry=node_registry,
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
