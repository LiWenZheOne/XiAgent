from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from xiagent.assets.service import SqliteAssetService
from xiagent.core.errors import ConflictError
from xiagent.infrastructure.config import Settings, load_settings
from xiagent.infrastructure.migrations import migrate
from xiagent.nodes import build_node_registry
from xiagent.nodes.registry import NodeRegistry
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.models import ProjectRecord, UserRecord
from xiagent.users.service import SqliteUserService
from xiagent.workflows.service import WorkflowCatalog


@dataclass(frozen=True)
class WorkflowTestSession:
    settings: Settings
    users: SqliteUserService
    assets: SqliteAssetService
    node_registry: NodeRegistry
    runtime: SqliteRuntimeService
    workflows: WorkflowCatalog
    user: UserRecord
    project: ProjectRecord
    run_output_dir: Path


class WorkflowTestBuilder:
    def __init__(self) -> None:
        self._database_path = Path(".data/workflow-test.sqlite3")
        self._asset_storage_dir = Path(".data/workflow-test-assets")
        self._workflow_dir = Path("workflows")
        self._admin_username = "workflow-test-admin"
        self._admin_password = "secret-123"
        self._project_name = "Workflow Test Project"
        self._project_id: str | None = None
        self._run_output_dir: Path | None = None

    def with_database_path(self, path: Path | str) -> WorkflowTestBuilder:
        self._database_path = Path(path)
        return self

    def with_asset_storage_dir(self, path: Path | str) -> WorkflowTestBuilder:
        self._asset_storage_dir = Path(path)
        return self

    def with_workflow_dir(self, path: Path | str) -> WorkflowTestBuilder:
        self._workflow_dir = Path(path)
        return self

    def with_default_admin(self, *, username: str, password: str) -> WorkflowTestBuilder:
        self._admin_username = username
        self._admin_password = password
        return self

    def with_default_project(self, *, name: str) -> WorkflowTestBuilder:
        self._project_name = name
        self._project_id = None
        return self

    def with_project_id(self, project_id: str) -> WorkflowTestBuilder:
        self._project_id = project_id
        return self

    def with_run_output_dir(self, path: Path | str) -> WorkflowTestBuilder:
        self._run_output_dir = Path(path)
        return self

    async def build(self) -> WorkflowTestSession:
        settings = self._build_settings()
        await migrate(settings.database_path)

        users = SqliteUserService(settings.database_path)
        user = await self._get_or_create_user(users)
        project = await self._get_or_create_project(users, user)

        assets = SqliteAssetService(
            database_path=settings.database_path,
            storage_dir=settings.asset_storage_dir,
            user_service=users,
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

        settings.asset_storage_dir.mkdir(parents=True, exist_ok=True)
        run_output_dir = self._run_output_dir or (
            settings.database_path.parent / "workflow-test-runs"
        )
        run_output_dir.mkdir(parents=True, exist_ok=True)

        return WorkflowTestSession(
            settings=settings,
            users=users,
            assets=assets,
            node_registry=node_registry,
            runtime=runtime,
            workflows=workflows,
            user=user,
            project=project,
            run_output_dir=run_output_dir,
        )

    def _build_settings(self) -> Settings:
        return replace(
            load_settings(),
            database_path=self._database_path,
            asset_storage_dir=self._asset_storage_dir,
            workflow_dir=self._workflow_dir,
        )

    async def _get_or_create_user(self, users: SqliteUserService) -> UserRecord:
        try:
            return await users.create_user(
                username=self._admin_username,
                password=self._admin_password,
            )
        except ConflictError:
            auth = await users.authenticate(
                username=self._admin_username,
                password=self._admin_password,
            )
            return auth.user

    async def _get_or_create_project(
        self,
        users: SqliteUserService,
        user: UserRecord,
    ) -> ProjectRecord:
        if self._project_id is not None:
            return await users.get_project(
                user_id=user.user_id,
                project_id=self._project_id,
            )

        projects = await users.list_projects_for_user(user_id=user.user_id)
        clean_name = self._project_name.strip()
        for project in projects:
            if project.name == clean_name:
                return project

        return await users.create_project(
            owner_user_id=user.user_id,
            name=self._project_name,
        )
