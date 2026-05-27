from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from xiagent.core.errors import NotFoundError, PermissionDeniedError, ValidationError, XiAgentError
from xiagent.core.ids import new_id
from xiagent.core.schemas import validate_json_value
from xiagent.core.services import AssetService, UserService
from xiagent.infrastructure.database import connect_db
from xiagent.nodes.base import AssetRef, NodeContext
from xiagent.nodes.registry import NodeRegistry
from xiagent.runtime.execution_store import (
    SqliteExecutionStore,
    dump_asset_refs,
    dump_json,
    insert_event,
    node_execution_from_row,
    task_from_row,
)
from xiagent.runtime.input_resolver import resolve_node_inputs, resolve_path
from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord
from xiagent.runtime.task_view import build_current_view
from xiagent.workflows.validator import validate_workflow_contract

_START = "START"
_END = "END"


class SqliteRuntimeService:
    def __init__(
        self,
        *,
        database_path: Path,
        user_service: UserService,
        node_registry: NodeRegistry,
        asset_service: AssetService | None = None,
    ) -> None:
        self._database_path = database_path
        self._user_service = user_service
        self._node_registry = node_registry
        self._asset_service = asset_service
        self._store = SqliteExecutionStore(database_path)

    async def create_task_from_contract(
        self,
        *,
        user_id: str,
        project_id: str,
        contract: dict[str, Any],
        input_data: dict[str, Any],
    ) -> TaskRecord:
        await self._user_service.ensure_project_access(
            user_id=user_id,
            project_id=project_id,
            action="task:create",
        )
        validate_workflow_contract(contract, self._node_registry)
        _validate_workflow_project_scope(contract["workflow"], project_id=project_id)
        validate_json_value(contract["workflow"]["input_schema"], input_data)

        workflow = contract["workflow"]
        now = _utc_now()
        task_id = new_id("task")
        async with connect_db(self._database_path) as db:
            template_id = await _find_or_create_workflow_template(
                db,
                workflow=workflow,
                project_id=project_id,
                contract=contract,
                now=now,
            )
            await db.execute(
                """
                insert into tasks (
                  task_id, workflow_template_id, workflow_id, workflow_version, user_id,
                  project_id, input_json, status, current_view_json, created_at, started_at,
                  finished_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    template_id,
                    workflow["id"],
                    workflow["version"],
                    user_id,
                    project_id,
                    dump_json(input_data),
                    "running",
                    dump_json(build_current_view("running", [])),
                    now,
                    now,
                    None,
                    now,
                ),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="task_created",
                payload={"workflow_id": workflow["id"]},
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="task_started",
                payload={},
                created_at=now,
            )

        try:
            return await self._continue_task(
                task_id=task_id,
                user_id=user_id,
                project_id=project_id,
                contract=contract,
                workflow_input=input_data,
                start_node_id=_START,
            )
        except XiAgentError as exc:
            await self._fail_task(
                task_id,
                {"code": exc.code, "message": exc.message, "details": exc.details},
            )
            raise exc.__class__(
                code=exc.code,
                message=exc.message,
                details=exc.details | {"task_id": task_id},
            ) from exc
        except Exception as exc:
            await self._fail_task(
                task_id,
                {"code": "task_execution_failed", "message": str(exc), "details": {}},
            )
            raise

    async def resume_task(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
        node_id: str,
        output: dict[str, Any],
    ) -> TaskRecord:
        await self._user_service.ensure_project_access(
            user_id=user_id,
            project_id=project_id,
            action="task:resume",
        )
        task, contract = await self._get_task_and_contract(task_id)
        _ensure_task_belongs_to_project(task, user_id=user_id, project_id=project_id)
        if task.status != "waiting":
            raise ValidationError(
                code="task_not_waiting",
                message="Task is not waiting for resume input",
                details={"task_id": task_id, "status": task.status},
            )

        node_def = _node_by_id(contract, node_id)
        validate_json_value(node_def["outputs"], output)
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                update node_executions
                set output_snapshot_json = ?, status = ?, finished_at = ?, updated_at = ?
                where task_id = ? and node_id = ? and status = 'waiting'
                """,
                (dump_json(output), "succeeded", now, now, task_id, node_id),
            )
            if cursor.rowcount != 1:
                await cursor.close()
                raise ValidationError(
                    code="node_not_waiting",
                    message="Node is not waiting for resume input",
                    details={"task_id": task_id, "node_id": node_id},
                )
            await cursor.close()
            waiting_execution = await _fetch_execution_by_task_node_status(
                db,
                task_id=task_id,
                node_id=node_id,
                status="succeeded",
            )
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, updated_at = ?
                where task_id = ?
                """,
                ("running", dump_json(task.current_view | {"status": "running"}), now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="task_resumed",
                payload={"node_id": node_id},
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_succeeded",
                payload={
                    "node_id": node_id,
                    "node_execution_id": waiting_execution.node_execution_id,
                },
                created_at=now,
            )

        try:
            return await self._continue_task(
                task_id=task_id,
                user_id=user_id,
                project_id=project_id,
                contract=contract,
                workflow_input=task.input_data,
                start_node_id=node_id,
            )
        except XiAgentError as exc:
            await self._fail_task(
                task_id,
                {"code": exc.code, "message": exc.message, "details": exc.details},
            )
            raise exc.__class__(
                code=exc.code,
                message=exc.message,
                details=exc.details | {"task_id": task_id},
            ) from exc
        except Exception as exc:
            await self._fail_task(
                task_id,
                {"code": "task_execution_failed", "message": str(exc), "details": {}},
            )
            raise

    async def list_node_executions(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
    ) -> list[NodeExecutionRecord]:
        await self._authorize_task_read(user_id=user_id, project_id=project_id, task_id=task_id)
        return await self._store.list_node_executions(task_id)

    async def list_events(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
    ) -> list[TaskEventRecord]:
        await self._authorize_task_read(user_id=user_id, project_id=project_id, task_id=task_id)
        return await self._store.list_events(task_id)

    async def list_tasks(self, *, user_id: str, project_id: str) -> list[TaskRecord]:
        await self._user_service.ensure_project_access(
            user_id=user_id,
            project_id=project_id,
            action="task:list",
        )
        return await self._store.list_tasks(user_id=user_id, project_id=project_id)

    async def get_task(self, *, user_id: str, project_id: str, task_id: str) -> TaskRecord:
        await self._authorize_task_read(user_id=user_id, project_id=project_id, task_id=task_id)
        return await self._get_task_by_id(task_id)

    async def get_task_workflow_snapshot(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        await self._authorize_task_read(user_id=user_id, project_id=project_id, task_id=task_id)
        snapshot = await self._store.fetch_task_workflow_snapshot(task_id)
        if snapshot is None:
            raise NotFoundError("workflow_snapshot_not_found", "Workflow snapshot was not found")
        return snapshot

    async def rerun_node(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
        node_id: str,
    ) -> TaskRecord:
        await self._user_service.ensure_project_access(
            user_id=user_id,
            project_id=project_id,
            action="task:rerun",
        )
        task, contract = await self._get_task_and_contract(task_id)
        _ensure_task_belongs_to_project(task, user_id=user_id, project_id=project_id)
        _node_by_id(contract, node_id)

        affected_node_ids = {node_id, *_downstream_node_ids(contract, node_id)}
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            executions = await _fetch_node_executions(db, task_id)
            current_execution_ids = _latest_execution_ids_for_nodes(executions, affected_node_ids)
            if current_execution_ids:
                placeholders = ", ".join("?" for _ in current_execution_ids)
                await db.execute(
                    f"""
                    update node_executions
                    set status = ?, updated_at = ?
                    where node_execution_id in ({placeholders})
                    """,
                    ("superseded", now, *current_execution_ids),
                )
            refreshed_executions = await _fetch_node_executions(db, task_id)
            current_view = build_current_view("running", refreshed_executions)
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, finished_at = ?, updated_at = ?
                where task_id = ?
                """,
                ("running", dump_json(current_view), None, now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_rerun_started",
                payload={"node_id": node_id},
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="downstream_cleared",
                payload={"node_id": node_id, "cleared_node_ids": sorted(affected_node_ids)},
                created_at=now,
            )

        return await self._continue_task(
            task_id=task_id,
            user_id=user_id,
            project_id=project_id,
            contract=contract,
            workflow_input=task.input_data,
            start_node_id=node_id,
        )

    async def _get_task_by_id(self, task_id: str) -> TaskRecord:
        task = await self._store.fetch_task(task_id)
        if task is None:
            raise NotFoundError("task_not_found", "Task was not found", {"task_id": task_id})
        return task

    async def _authorize_task_read(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
    ) -> None:
        await self._user_service.ensure_project_access(
            user_id=user_id,
            project_id=project_id,
            action="task:read",
        )
        task = await self._get_task_by_id(task_id)
        _ensure_task_belongs_to_project(task, user_id=user_id, project_id=project_id)

    async def _continue_task(
        self,
        *,
        task_id: str,
        user_id: str,
        project_id: str,
        contract: dict[str, Any],
        workflow_input: dict[str, Any],
        start_node_id: str,
    ) -> TaskRecord:
        _ = start_node_id
        while True:
            executions = await self._store.list_node_executions(task_id)
            if any(execution.status == "failed" for execution in executions):
                return await self._get_task_by_id(task_id)
            node_outputs = await self._load_node_outputs(task_id)
            ready_node_ids = _ready_node_ids(
                contract,
                workflow_input,
                node_outputs,
                executions,
            )
            if not ready_node_ids:
                if any(execution.status == "waiting" for execution in executions):
                    return await self._get_task_by_id(task_id)
                return await self._finish_task(task_id, "succeeded")

            for next_node_id in ready_node_ids:
                execution = await self._start_node_execution(
                    task_id=task_id,
                    user_id=user_id,
                    project_id=project_id,
                    contract=contract,
                    node_id=next_node_id,
                    workflow_input=workflow_input,
                    node_outputs=node_outputs,
                )
                if execution.status == "waiting":
                    return await self._get_task_by_id(task_id)
                if execution.status == "failed":
                    return await self._get_task_by_id(task_id)

    async def _start_node_execution(
        self,
        *,
        task_id: str,
        user_id: str,
        project_id: str,
        contract: dict[str, Any],
        node_id: str,
        workflow_input: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> NodeExecutionRecord:
        node_def = _node_by_id(contract, node_id)
        node = self._node_registry.get(node_def["ref"])
        inputs = resolve_node_inputs(node_def.get("inputs", {}), workflow_input, node_outputs)
        now = _utc_now()
        attempt = await self._next_attempt(task_id, node_id)
        node_execution_id = new_id("node_execution")

        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                insert into node_executions (
                  node_execution_id, task_id, node_id, node_ref, attempt, input_snapshot_json,
                  output_snapshot_json, status, error_json, metadata_json, asset_refs_json,
                  started_at, finished_at, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_execution_id,
                    task_id,
                    node_id,
                    node_def["ref"],
                    attempt,
                    dump_json(inputs),
                    dump_json({}),
                    "running",
                    None,
                    dump_json({}),
                    dump_asset_refs([]),
                    now,
                    None,
                    now,
                    now,
                ),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_started",
                payload={"node_id": node_id, "node_execution_id": node_execution_id},
                created_at=now,
            )

        ctx = NodeContext(
            user_id=user_id,
            project_id=project_id,
            task_id=task_id,
            node_id=node_id,
            node_execution_id=node_execution_id,
            config=dict(node_def.get("config", {})),
            output_schema=dict(node_def["outputs"]),
            asset_service=self._asset_service,
            event_sink=None,
            logger=None,
        )
        try:
            result = await node.run(ctx, inputs)
            if result.status == "waiting":
                return await self._mark_node_waiting(
                    task_id=task_id,
                    node_execution_id=node_execution_id,
                    node_id=node_id,
                    metadata=result.metadata,
                )
            if result.status != "succeeded":
                raise ValidationError(
                    code="unsupported_node_result_status",
                    message="Node returned an unsupported status",
                    details={"status": result.status, "node_id": node_id},
                )
            validate_json_value(node_def["outputs"], result.output)
            return await self._mark_node_succeeded(
                task_id=task_id,
                node_execution_id=node_execution_id,
                node_id=node_id,
                output=result.output,
                metadata=result.metadata,
                asset_refs=result.asset_refs,
            )
        except XiAgentError as exc:
            return await self._mark_node_failed(
                task_id=task_id,
                node_execution_id=node_execution_id,
                node_id=node_id,
                error={"code": exc.code, "message": exc.message, "details": exc.details},
            )
        except Exception as exc:
            return await self._mark_node_failed(
                task_id=task_id,
                node_execution_id=node_execution_id,
                node_id=node_id,
                error={"code": "node_execution_failed", "message": str(exc), "details": {}},
            )

    async def _mark_node_waiting(
        self,
        *,
        task_id: str,
        node_execution_id: str,
        node_id: str,
        metadata: dict[str, Any],
    ) -> NodeExecutionRecord:
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                update node_executions
                set status = ?, metadata_json = ?, updated_at = ?
                where node_execution_id = ?
                """,
                ("waiting", dump_json(metadata), now, node_execution_id),
            )
            executions = await _fetch_node_executions(db, task_id)
            current_view = build_current_view("waiting", executions)
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, updated_at = ?
                where task_id = ?
                """,
                ("waiting", dump_json(current_view), now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_waiting",
                payload={"node_id": node_id, "node_execution_id": node_execution_id},
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="human_input_requested",
                payload={"node_id": node_id, "node_execution_id": node_execution_id},
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="task_waiting",
                payload={"node_id": node_id},
                created_at=now,
            )
        return (await self._get_execution(node_execution_id))  # noqa: RET504

    async def _mark_node_succeeded(
        self,
        *,
        task_id: str,
        node_execution_id: str,
        node_id: str,
        output: dict[str, Any],
        metadata: dict[str, Any],
        asset_refs: list[AssetRef],
    ) -> NodeExecutionRecord:
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                update node_executions
                set output_snapshot_json = ?, status = ?, metadata_json = ?, asset_refs_json = ?,
                    finished_at = ?, updated_at = ?
                where node_execution_id = ?
                """,
                (
                    dump_json(output),
                    "succeeded",
                    dump_json(metadata),
                    dump_asset_refs(asset_refs),
                    now,
                    now,
                    node_execution_id,
                ),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_succeeded",
                payload={"node_id": node_id, "node_execution_id": node_execution_id},
                created_at=now,
            )
        return await self._get_execution(node_execution_id)

    async def _mark_node_failed(
        self,
        *,
        task_id: str,
        node_execution_id: str,
        node_id: str,
        error: dict[str, Any],
    ) -> NodeExecutionRecord:
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            await db.execute(
                """
                update node_executions
                set status = ?, error_json = ?, finished_at = ?, updated_at = ?
                where node_execution_id = ?
                """,
                ("failed", dump_json(error), now, now, node_execution_id),
            )
            executions = await _fetch_node_executions(db, task_id)
            current_view = build_current_view("failed", executions)
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, finished_at = ?, updated_at = ?
                where task_id = ?
                """,
                ("failed", dump_json(current_view), now, now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_failed",
                payload={
                    "node_id": node_id,
                    "node_execution_id": node_execution_id,
                    "error": error,
                },
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="task_failed",
                payload={"node_id": node_id, "error": error},
                created_at=now,
            )
        return await self._get_execution(node_execution_id)

    async def _fail_task(self, task_id: str, error: dict[str, Any]) -> None:
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            executions = await _fetch_node_executions(db, task_id)
            current_view = build_current_view("failed", executions)
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, finished_at = ?, updated_at = ?
                where task_id = ? and status != 'failed'
                """,
                ("failed", dump_json(current_view), now, now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="task_failed",
                payload={"error": error},
                created_at=now,
            )

    async def _finish_task(self, task_id: str, status: str) -> TaskRecord:
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            executions = await _fetch_node_executions(db, task_id)
            final_output = _latest_node_outputs(executions)
            current_view = build_current_view(status, executions, final_output=final_output)
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, finished_at = ?, updated_at = ?
                where task_id = ?
                """,
                (status, dump_json(current_view), now, now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type=f"task_{status}",
                payload={},
                created_at=now,
            )
        return await self._get_task_by_id(task_id)

    async def _load_node_outputs(self, task_id: str) -> dict[str, dict[str, Any]]:
        executions = await self._store.list_node_executions(task_id)
        return _latest_node_outputs(executions)

    async def _next_attempt(self, task_id: str, node_id: str) -> int:
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                select coalesce(max(attempt), 0) + 1 as attempt
                from node_executions
                where task_id = ? and node_id = ?
                """,
                (task_id, node_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return int(row["attempt"])

    async def _get_execution(self, node_execution_id: str) -> NodeExecutionRecord:
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                "select * from node_executions where node_execution_id = ?",
                (node_execution_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise NotFoundError(
                "node_execution_not_found",
                "Node execution was not found",
                {"node_execution_id": node_execution_id},
            )
        return node_execution_from_row(row)

    async def _get_waiting_execution(self, task_id: str, node_id: str) -> NodeExecutionRecord:
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                select *
                from node_executions
                where task_id = ? and node_id = ? and status = 'waiting'
                order by created_at desc
                limit 1
                """,
                (task_id, node_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise ValidationError(
                code="waiting_node_not_found",
                message="Waiting node execution was not found",
                details={"task_id": task_id, "node_id": node_id},
            )
        return node_execution_from_row(row)

    async def _get_task_and_contract(self, task_id: str) -> tuple[TaskRecord, dict[str, Any]]:
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                select t.*, wt.contract_json
                from tasks t
                join workflow_templates wt on wt.template_id = t.workflow_template_id
                where t.task_id = ?
                """,
                (task_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise NotFoundError("task_not_found", "Task was not found", {"task_id": task_id})
        return task_from_row(row), _loads_contract(row["contract_json"])


def _ready_node_ids(
    contract: dict[str, Any],
    workflow_input: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    executions: list[NodeExecutionRecord],
) -> list[str]:
    active_nodes, active_edges, potential_nodes = _activation_state(
        contract,
        workflow_input,
        node_outputs,
    )
    started_node_ids = {
        execution.node_id for execution in executions if execution.status != "superseded"
    }
    ready: list[str] = []
    for node in contract["nodes"]:
        node_id = node["id"]
        if node_id in started_node_ids or node_id not in active_nodes:
            continue
        if _node_is_ready(
            contract,
            node_id,
            workflow_input,
            node_outputs,
            active_nodes,
            active_edges,
            potential_nodes,
        ):
            ready.append(node_id)
    return ready


def _activation_state(
    contract: dict[str, Any],
    workflow_input: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
) -> tuple[set[str], set[tuple[str, str]], set[str]]:
    completed_node_ids = set(node_outputs)
    active_nodes: set[str] = set()
    active_edges: set[tuple[str, str]] = set()

    for edge in contract["edges"]:
        from_node = edge["from"]
        if from_node != _START and from_node not in completed_node_ids:
            continue
        if not _edge_matches(edge, workflow_input, node_outputs):
            continue
        to_node = edge["to"]
        active_edges.add((from_node, to_node))
        if to_node != _END:
            active_nodes.add(to_node)

    potential_nodes = _potential_downstream_nodes(
        contract,
        active_nodes.difference(completed_node_ids),
    )
    return active_nodes, active_edges, potential_nodes


def _potential_downstream_nodes(
    contract: dict[str, Any],
    unresolved_active_nodes: set[str],
) -> set[str]:
    potential_nodes: set[str] = set()
    stack = list(unresolved_active_nodes)
    while stack:
        from_node = stack.pop()
        for edge in contract["edges"]:
            if edge["from"] != from_node or edge["to"] == _END:
                continue
            to_node = edge["to"]
            if to_node in potential_nodes:
                continue
            potential_nodes.add(to_node)
            stack.append(to_node)
    return potential_nodes


def _node_is_ready(
    contract: dict[str, Any],
    node_id: str,
    workflow_input: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    active_nodes: set[str],
    active_edges: set[tuple[str, str]],
    potential_nodes: set[str],
) -> bool:
    has_active_incoming = False
    for edge in contract["edges"]:
        if edge["to"] != node_id:
            continue
        from_node = edge["from"]
        if (from_node, node_id) in active_edges:
            has_active_incoming = True
            continue
        if from_node == _START:
            continue
        if from_node in node_outputs:
            if _edge_matches(edge, workflow_input, node_outputs):
                has_active_incoming = True
            continue
        if from_node in active_nodes or from_node in potential_nodes:
            return False
    return has_active_incoming


def _edge_matches(
    edge: Mapping[str, Any],
    workflow_input: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
) -> bool:
    condition = edge.get("when")
    if condition is None:
        return True
    actual = resolve_path(
        condition.get("path"),
        workflow_input=workflow_input,
        node_outputs=node_outputs,
    )
    if "equals" in condition:
        return actual == condition["equals"]
    raise ValidationError(
        code="unsupported_workflow_condition",
        message="Workflow edge condition is not supported",
        details={"condition": dict(condition)},
    )


def _validate_workflow_project_scope(workflow: dict[str, Any], *, project_id: str) -> None:
    if workflow["scope"] != "project":
        return
    contract_project_id = workflow.get("project_id")
    if contract_project_id is not None and contract_project_id != project_id:
        raise ValidationError(
            code="workflow_project_mismatch",
            message="Workflow project_id does not match the task project scope",
            details={"contract_project_id": contract_project_id, "project_id": project_id},
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


async def _fetch_node_executions(
    db: aiosqlite.Connection,
    task_id: str,
) -> list[NodeExecutionRecord]:
    cursor = await db.execute(
        """
        select *
        from node_executions
        where task_id = ?
        order by created_at asc, rowid asc
        """,
        (task_id,),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [node_execution_from_row(row) for row in rows]


async def _fetch_execution_by_task_node_status(
    db: aiosqlite.Connection,
    *,
    task_id: str,
    node_id: str,
    status: str,
) -> NodeExecutionRecord:
    cursor = await db.execute(
        """
        select *
        from node_executions
        where task_id = ? and node_id = ? and status = ?
        order by updated_at desc, rowid desc
        limit 1
        """,
        (task_id, node_id, status),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise ValidationError(
            code="node_execution_not_found",
            message="Node execution was not found",
            details={"task_id": task_id, "node_id": node_id, "status": status},
        )
    return node_execution_from_row(row)


async def _find_or_create_workflow_template(
    db: aiosqlite.Connection,
    *,
    workflow: dict[str, Any],
    project_id: str,
    contract: dict[str, Any],
    now: str,
) -> str:
    template_project_id = None
    if workflow["scope"] == "project":
        template_project_id = project_id
    cursor = await db.execute(
        """
        select template_id
        from workflow_templates
        where workflow_id = ?
          and version = ?
          and scope = ?
          and (
            (? is null and project_id is null)
            or project_id = ?
          )
        order by created_at asc
        limit 1
        """,
        (
            workflow["id"],
            workflow["version"],
            workflow["scope"],
            template_project_id,
            template_project_id,
        ),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is not None:
        return str(row["template_id"])

    template_id = new_id("workflow_template")
    await db.execute(
        """
        insert into workflow_templates (
          template_id, workflow_id, version, scope, project_id, name, description,
          contract_json, status, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            template_id,
            workflow["id"],
            workflow["version"],
            workflow["scope"],
            template_project_id,
            workflow["name"],
            workflow.get("description"),
            dump_json(contract),
            "active",
            now,
            now,
        ),
    )
    return template_id


def _latest_node_outputs(executions: list[NodeExecutionRecord]) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for execution in executions:
        if execution.status == "succeeded":
            outputs[execution.node_id] = execution.output_snapshot
    return outputs


def _latest_execution_ids_for_nodes(
    executions: list[NodeExecutionRecord],
    node_ids: set[str],
) -> list[str]:
    latest_by_node: dict[str, NodeExecutionRecord] = {}
    for execution in executions:
        if execution.node_id in node_ids and execution.status != "superseded":
            latest_by_node[execution.node_id] = execution
    return [execution.node_execution_id for execution in latest_by_node.values()]


def _downstream_node_ids(contract: dict[str, Any], node_id: str) -> set[str]:
    downstream: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        for edge in contract["edges"]:
            if edge["from"] != current or edge["to"] == _END:
                continue
            next_node_id = edge["to"]
            if next_node_id in downstream:
                continue
            downstream.add(next_node_id)
            stack.append(next_node_id)
    return downstream


def _loads_contract(value: str) -> dict[str, Any]:
    import json

    loaded = json.loads(value)
    if not isinstance(loaded, dict):
        raise ValidationError("invalid_workflow_contract", "Workflow contract must be an object")
    return loaded


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_task_belongs_to_project(
    task: TaskRecord,
    *,
    user_id: str,
    project_id: str,
) -> None:
    if task.user_id == user_id and task.project_id == project_id:
        return
    raise PermissionDeniedError(
        code="project_access_denied",
        message="User does not have access to this project",
        details={"action": "task:read", "project_id": project_id},
    )
