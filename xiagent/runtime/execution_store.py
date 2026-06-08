from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import aiosqlite

from xiagent.core.ids import new_id
from xiagent.infrastructure.database import connect_db
from xiagent.nodes.base import AssetRef
from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord


class SqliteExecutionStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def fetch_task(self, task_id: str) -> TaskRecord | None:
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(db, "select * from tasks where task_id = ?", (task_id,))
        return _task_from_row(row) if row is not None else None

    async def list_tasks(self, *, user_id: str, project_id: str) -> list[TaskRecord]:
        async with connect_db(self._database_path) as db:
            cursor = await db.execute(
                """
                select *
                from tasks
                where user_id = ? and project_id = ? and status != 'archived'
                order by created_at desc, rowid desc
                """,
                (user_id, project_id),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_task_from_row(row) for row in rows]

    async def fetch_task_workflow_snapshot(self, task_id: str) -> dict[str, Any] | None:
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(
                db,
                """
                select wt.contract_json
                from tasks t
                join workflow_templates wt on wt.template_id = t.workflow_template_id
                where t.task_id = ?
                """,
                (task_id,),
            )
        if row is None:
            return None
        loaded = _load_json(row["contract_json"])
        if not isinstance(loaded, dict):
            return None
        return loaded

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

    async def list_event_summaries(
        self,
        task_id: str,
        *,
        since_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        async with connect_db(self._database_path) as db:
            if since_event_id:
                cursor = await db.execute(
                    """
                    select
                        event_id,
                        task_id,
                        event_type,
                        created_at,
                        json_extract(payload_json, '$.node_id') as node_id,
                        json_extract(payload_json, '$.message') as message,
                        json_extract(payload_json, '$.changed_keys') as changed_keys_json
                    from task_events
                    where task_id = ?
                      and rowid > (
                          select rowid
                          from task_events
                          where task_id = ? and event_id = ?
                      )
                    order by created_at asc, rowid asc
                    """,
                    (task_id, task_id, since_event_id),
                )
            else:
                cursor = await db.execute(
                    """
                    select
                        event_id,
                        task_id,
                        event_type,
                        created_at,
                        json_extract(payload_json, '$.node_id') as node_id,
                        json_extract(payload_json, '$.message') as message,
                        json_extract(payload_json, '$.changed_keys') as changed_keys_json
                    from task_events
                    where task_id = ?
                    order by created_at asc, rowid asc
                    """,
                    (task_id,),
                )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_event_summary_from_row(row) for row in rows]

    async def latest_event_id(self, task_id: str) -> str | None:
        async with connect_db(self._database_path) as db:
            row = await _fetch_one(
                db,
                """
                select event_id
                from task_events
                where task_id = ?
                order by created_at desc, rowid desc
                limit 1
                """,
                (task_id,),
            )
        return str(row["event_id"]) if row is not None else None


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


def dump_asset_refs(asset_refs: list[AssetRef]) -> str:
    return _dump_json([asdict(asset_ref) for asset_ref in asset_refs])


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


def _load_asset_refs(value: str | None) -> list[AssetRef]:
    raw_refs = _load_json(value) or []
    return [
        AssetRef(
            asset_id=str(raw_ref["asset_id"]),
            usage_type=str(raw_ref["usage_type"]),
            source=str(raw_ref["source"]),
        )
        for raw_ref in raw_refs
    ]


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
        asset_refs=_load_asset_refs(row["asset_refs_json"]),
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


def _event_summary_from_row(row: aiosqlite.Row) -> dict[str, Any]:
    changed_keys = _load_json(row["changed_keys_json"]) if row["changed_keys_json"] else []
    if not isinstance(changed_keys, list):
        changed_keys = []
    summary = {
        "event_id": row["event_id"],
        "task_id": row["task_id"],
        "event_type": row["event_type"],
        "node_id": row["node_id"],
        "message": row["message"],
        "created_at": row["created_at"],
        "changed_keys": [str(key) for key in changed_keys],
    }
    summary["payload"] = {
        key: value
        for key, value in {
            "node_id": summary["node_id"],
            "message": summary["message"],
            "changed_keys": summary["changed_keys"],
        }.items()
        if value not in (None, "", [])
    }
    return summary
