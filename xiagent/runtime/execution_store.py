from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from xiagent.core.ids import new_id
from xiagent.infrastructure.database import connect_db
from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord


class SqliteExecutionStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def fetch_task(self, task_id: str) -> TaskRecord | None:
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(db, "select * from tasks where task_id = ?", (task_id,))
        return _task_from_row(row) if row is not None else None

    async def list_node_executions(self, task_id: str) -> list[NodeExecutionRecord]:
        async with connect_db(self._database_path) as db:
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
        return [_node_execution_from_row(row) for row in rows]

    async def list_events(self, task_id: str) -> list[TaskEventRecord]:
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                select *
                from task_events
                where task_id = ?
                order by created_at asc, rowid asc
                """,
                (task_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_event_from_row(row) for row in rows]


async def insert_event(
    db: aiosqlite.Connection,
    *,
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    await db.execute(
        """
        insert into task_events (event_id, task_id, event_type, payload_json, created_at)
        values (?, ?, ?, ?, ?)
        """,
        (new_id("event"), task_id, event_type, _dump_json(payload), created_at),
    )


def dump_json(value: Any) -> str:
    return _dump_json(value)


def task_from_row(row: aiosqlite.Row) -> TaskRecord:
    return _task_from_row(row)


def node_execution_from_row(row: aiosqlite.Row) -> NodeExecutionRecord:
    return _node_execution_from_row(row)


async def _fetch_one(
    db: aiosqlite.Connection,
    query: str,
    parameters: tuple[Any, ...],
) -> aiosqlite.Row | None:
    cursor = await db.execute(query, parameters)
    try:
        return await cursor.fetchone()
    finally:
        await cursor.close()


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_json(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def _task_from_row(row: aiosqlite.Row) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"],
        workflow_template_id=row["workflow_template_id"],
        workflow_id=row["workflow_id"],
        workflow_version=row["workflow_version"],
        user_id=row["user_id"],
        project_id=row["project_id"],
        input_data=_load_json(row["input_json"]),
        status=row["status"],
        current_view=_load_json(row["current_view_json"]),
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        updated_at=row["updated_at"],
    )


def _node_execution_from_row(row: aiosqlite.Row) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_execution_id=row["node_execution_id"],
        task_id=row["task_id"],
        node_id=row["node_id"],
        node_ref=row["node_ref"],
        attempt=row["attempt"],
        input_snapshot=_load_json(row["input_snapshot_json"]),
        output_snapshot=_load_json(row["output_snapshot_json"]),
        status=row["status"],
        error=_load_json(row["error_json"]),
        metadata=_load_json(row["metadata_json"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _event_from_row(row: aiosqlite.Row) -> TaskEventRecord:
    return TaskEventRecord(
        event_id=row["event_id"],
        task_id=row["task_id"],
        event_type=row["event_type"],
        payload=_load_json(row["payload_json"]),
        created_at=row["created_at"],
    )
