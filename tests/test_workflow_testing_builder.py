from __future__ import annotations

from pathlib import Path

from xiagent.workflows.testing import WorkflowTestBuilder


async def test_builder_creates_default_user_project_and_services(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_default_admin(username="workflow-test-admin", password="secret-123")
        .with_default_project(name="Workflow Test Project")
        .build()
    )

    assert session.user.username == "workflow-test-admin"
    assert session.project.name == "Workflow Test Project"
    assert session.project.owner_user_id == session.user.user_id
    assert session.settings.database_path == tmp_path / "workflow-test.sqlite3"
    assert session.settings.asset_storage_dir == tmp_path / "assets"
    assert session.settings.workflow_dir == workflow_dir
    assert session.run_output_dir == tmp_path / "workflow-test-runs"
    assert session.node_registry.get("tool.echo.v1").describe().ref == "tool.echo.v1"


async def test_builder_reuses_existing_default_user_and_project(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    builder = (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_default_admin(username="workflow-test-admin", password="secret-123")
        .with_default_project(name="Workflow Test Project")
    )

    first = await builder.build()
    second = await builder.build()

    assert second.user.user_id == first.user.user_id
    assert second.project.project_id == first.project.project_id


async def test_builder_uses_existing_project_id(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    first = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_default_admin(username="workflow-test-admin", password="secret-123")
        .with_default_project(name="Workflow Test Project")
        .build()
    )

    second = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_default_admin(username="workflow-test-admin", password="secret-123")
        .with_project_id(first.project.project_id)
        .build()
    )

    assert second.project.project_id == first.project.project_id
