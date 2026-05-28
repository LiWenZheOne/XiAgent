from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xiagent.core.errors import ValidationError, XiAgentError
from xiagent.core.schemas import validate_json_value
from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing.artifacts import (
    ImageArtifact,
    collect_image_artifacts,
    generate_html_preview,
    open_artifact_paths,
    open_html_preview,
)
from xiagent.workflows.testing.builder import WorkflowTestSession
from xiagent.workflows.testing.console import ConsoleIO


@dataclass(frozen=True)
class WorkflowTestRunResult:
    task: TaskRecord
    node_executions: list[NodeExecutionRecord]
    events: list[TaskEventRecord]
    artifacts: list[ImageArtifact]
    run_dir: Path
    preview_path: Path | None = None


class WorkflowTestRunner:
    def __init__(self, session: WorkflowTestSession, console: ConsoleIO) -> None:
        self._session = session
        self._console = console

    async def run_workflow_file(
        self,
        workflow_path: Path | str,
        *,
        input_data: dict[str, Any],
        open_images: bool = False,
        preview: Path | str | bool | None = None,
        open_preview: bool = False,
    ) -> WorkflowTestRunResult:
        contract = load_workflow_file(Path(workflow_path))
        return await self.run_contract(
            contract,
            input_data=input_data,
            open_images=open_images,
            preview=preview,
            open_preview=open_preview,
        )

    async def run_workflow_id(
        self,
        workflow_id: str,
        *,
        input_data: dict[str, Any],
        open_images: bool = False,
        preview: Path | str | bool | None = None,
        open_preview: bool = False,
    ) -> WorkflowTestRunResult:
        contract = self._session.workflows.get(workflow_id)
        return await self.run_contract(
            contract,
            input_data=input_data,
            open_images=open_images,
            preview=preview,
            open_preview=open_preview,
        )

    async def run_contract(
        self,
        contract: dict[str, Any],
        *,
        input_data: dict[str, Any],
        open_images: bool = False,
        preview: Path | str | bool | None = None,
        open_preview: bool = False,
    ) -> WorkflowTestRunResult:
        workflow = contract["workflow"]
        self._console.write(f"[01] 加载工作流 {workflow['id']} {workflow['version']}")
        try:
            task = await self._session.runtime.create_task_from_contract(
                user_id=self._session.user.user_id,
                project_id=self._session.project.project_id,
                contract=contract,
                input_data={},
            )
        except XiAgentError as exc:
            task = await self._task_from_persisted_failure(exc)

        pending_user_input: dict[str, Any] | None = dict(input_data)
        while task.status == "waiting":
            executions = await self._list_node_executions(task.task_id)
            waiting_execution = _latest_waiting_execution(executions)
            node_def = _node_by_id(contract, waiting_execution.node_id)
            input_schema = waiting_execution.metadata.get("input_schema")
            uses_node_input = isinstance(input_schema, dict)
            resume_schema = input_schema if uses_node_input else node_def["outputs"]
            self._console.write(f"[等待输入] 节点 {waiting_execution.node_id}")
            if uses_node_input and pending_user_input is not None:
                payload = pending_user_input
                pending_user_input = None
            else:
                payload = self._console.prompt_resume_output(waiting_execution, resume_schema)
            validate_json_value(resume_schema, payload)
            try:
                resume_kwargs = {
                    "user_id": self._session.user.user_id,
                    "project_id": self._session.project.project_id,
                    "task_id": task.task_id,
                    "node_id": waiting_execution.node_id,
                }
                if uses_node_input:
                    task = await self._session.runtime.resume_task(**resume_kwargs, input=payload)
                else:
                    task = await self._session.runtime.resume_task(**resume_kwargs, output=payload)
            except XiAgentError as exc:
                task = await self._task_from_persisted_failure(exc)

        node_executions = await self._list_node_executions(task.task_id)
        events = await self._list_events(task.task_id)
        run_dir = self._session.run_output_dir / task.task_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts = collect_image_artifacts(node_executions, output_dir=run_dir)
        self._show_run_output(events, node_executions, artifacts)

        if open_images:
            open_artifact_paths(artifact.path for artifact in artifacts)

        preview_path = self._maybe_generate_preview(
            preview=preview,
            open_preview=open_preview,
            run_dir=run_dir,
            task=task,
            node_executions=node_executions,
            events=events,
            artifacts=artifacts,
        )
        if preview_path is not None:
            self._console.write(f"preview: {preview_path}")

        return WorkflowTestRunResult(
            task=task,
            node_executions=node_executions,
            events=events,
            artifacts=artifacts,
            run_dir=run_dir,
            preview_path=preview_path,
        )

    async def _list_node_executions(self, task_id: str) -> list[NodeExecutionRecord]:
        return await self._session.runtime.list_node_executions(
            user_id=self._session.user.user_id,
            project_id=self._session.project.project_id,
            task_id=task_id,
        )

    async def _list_events(self, task_id: str) -> list[TaskEventRecord]:
        return await self._session.runtime.list_events(
            user_id=self._session.user.user_id,
            project_id=self._session.project.project_id,
            task_id=task_id,
        )

    async def _task_from_persisted_failure(self, exc: XiAgentError) -> TaskRecord:
        task_id = exc.details.get("task_id")
        if not isinstance(task_id, str):
            raise exc
        return await self._session.runtime.get_task(
            user_id=self._session.user.user_id,
            project_id=self._session.project.project_id,
            task_id=task_id,
        )

    def _maybe_generate_preview(
        self,
        *,
        preview: Path | str | bool | None,
        open_preview: bool,
        run_dir: Path,
        task: TaskRecord,
        node_executions: list[NodeExecutionRecord],
        events: list[TaskEventRecord],
        artifacts: list[ImageArtifact],
    ) -> Path | None:
        if (preview is None or preview is False) and not open_preview:
            return None

        preview_path = run_dir / "preview.html"
        if preview not in (None, True, False):
            preview_path = Path(preview)

        generated_path = generate_html_preview(
            task,
            node_executions,
            events,
            artifacts,
            preview_path,
        )
        if open_preview:
            open_html_preview(generated_path)
        return generated_path

    def _show_run_output(
        self,
        events: list[TaskEventRecord],
        node_executions: list[NodeExecutionRecord],
        artifacts: list[ImageArtifact],
    ) -> None:
        for index, event in enumerate(events, start=1):
            self._console.show_event(index, event)

        for execution in node_executions:
            self._console.write(f"node={execution.node_id} status={execution.status}")
            self._console.show_node_execution(execution)

        for artifact in artifacts:
            self._console.write(
                f"[图片输出] node={artifact.node_id} field={artifact.field_path}"
            )
            self._console.write(f"path: {artifact.path}")
            self._console.write(f"mime: {artifact.mime_type}")


def _latest_waiting_execution(
    node_executions: list[NodeExecutionRecord],
) -> NodeExecutionRecord:
    for execution in reversed(node_executions):
        if execution.status == "waiting":
            return execution
    raise ValidationError(
        code="waiting_node_not_found",
        message="Waiting node execution was not found",
        details={},
    )


def _node_by_id(contract: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in contract["nodes"]:
        if node["id"] == node_id:
            return node
    raise ValidationError(
        code="workflow_node_not_found",
        message="Workflow node was not found",
        details={"node_id": node_id},
    )
