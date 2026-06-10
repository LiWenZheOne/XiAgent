from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.password import hash_password
from xiagent.users.global_project import (
    GLOBAL_PROJECT_DESCRIPTION,
    GLOBAL_PROJECT_ID,
    GLOBAL_PROJECT_NAME,
    GLOBAL_PROJECT_OWNER_PASSWORD,
    GLOBAL_PROJECT_OWNER_USER_ID,
    GLOBAL_PROJECT_OWNER_USERNAME,
)

SCHEMA_SQL = """
create table if not exists users (
  user_id text primary key,
  username text not null unique,
  password_hash text not null,
  status text not null,
  created_at text not null,
  updated_at text not null
);

create table if not exists projects (
  project_id text primary key,
  owner_user_id text not null references users(user_id),
  name text not null,
  description text,
  status text not null,
  created_at text not null,
  updated_at text not null
);

create table if not exists assets (
  asset_id text primary key,
  scope text not null,
  project_id text references projects(project_id),
  asset_type text not null,
  name text not null,
  mime_type text,
  content_hash text,
  size_bytes integer,
  storage_uri text,
  text_content text,
  metadata_json text not null,
  created_by text not null references users(user_id),
  created_at text not null,
  updated_at text not null,
  deleted_at text
);

create table if not exists asset_project_bindings (
  binding_id text primary key,
  project_id text not null references projects(project_id),
  asset_id text not null references assets(asset_id),
  display_name text,
  usage_note text,
  metadata_json text not null,
  created_by text not null references users(user_id),
  created_at text not null,
  updated_at text not null,
  unique(project_id, asset_id)
);

create table if not exists asset_collections (
  collection_id text primary key,
  scope text not null,
  project_id text references projects(project_id),
  parent_id text references asset_collections(collection_id),
  name text not null,
  description text,
  sort_order integer not null default 0,
  created_by text not null references users(user_id),
  created_at text not null,
  updated_at text not null
);

create table if not exists asset_tags (
  tag_id text primary key,
  scope text not null,
  project_id text references projects(project_id),
  name text not null,
  description text,
  created_by text not null references users(user_id),
  created_at text not null,
  updated_at text not null
);

create table if not exists asset_index_entries (
  entry_id text primary key,
  scope text not null,
  project_id text references projects(project_id),
  asset_id text not null references assets(asset_id),
  collection_id text references asset_collections(collection_id),
  tag_id text references asset_tags(tag_id),
  search_text text not null,
  created_at text not null,
  updated_at text not null
);

create virtual table if not exists asset_search_fts using fts5(
  asset_id,
  scope,
  project_id,
  search_text
);

create table if not exists workflow_templates (
  template_id text primary key,
  workflow_id text not null,
  version text not null,
  scope text not null,
  project_id text references projects(project_id),
  name text not null,
  description text,
  contract_json text not null,
  status text not null,
  created_at text not null,
  updated_at text not null
);

create table if not exists tasks (
  task_id text primary key,
  workflow_template_id text not null references workflow_templates(template_id),
  workflow_id text not null,
  workflow_version text not null,
  user_id text not null references users(user_id),
  project_id text not null references projects(project_id),
  input_json text not null,
  status text not null,
  current_view_json text not null,
  created_at text not null,
  started_at text,
  finished_at text,
  updated_at text not null
);

create table if not exists node_executions (
  node_execution_id text primary key,
  task_id text not null references tasks(task_id),
  node_id text not null,
  node_ref text not null,
  attempt integer not null,
  input_snapshot_json text not null,
  output_snapshot_json text not null,
  status text not null,
  error_json text,
  metadata_json text not null,
  asset_refs_json text not null default '[]',
  started_at text,
  finished_at text,
  created_at text not null,
  updated_at text not null
);

create table if not exists task_events (
  event_id text primary key,
  task_id text not null references tasks(task_id),
  event_type text not null,
  payload_json text not null,
  created_at text not null
);
"""


async def migrate(path: Path) -> None:
    async with connect_db(path) as db:
        await db.executescript(SCHEMA_SQL)
        await _ensure_column(
            db,
            table_name="node_executions",
            column_name="asset_refs_json",
            definition="asset_refs_json text not null default '[]'",
        )
        await _ensure_global_project(db)
        await _normalize_global_asset_scope(db)
        await _ensure_unique_live_asset_names(db)
        await _ensure_live_asset_name_unique_index(db)
        await _ensure_unique_asset_tag_names(db)
        await _ensure_asset_tag_name_unique_index(db)


async def _ensure_column(
    db,
    *,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    cursor = await db.execute(f"pragma table_info({table_name})")
    try:
        columns = {str(row["name"]) for row in await cursor.fetchall()}
    finally:
        await cursor.close()
    if column_name not in columns:
        await db.execute(f"alter table {table_name} add column {definition}")


async def _ensure_unique_live_asset_names(db) -> None:
    duplicate_cursor = await db.execute(
        """
        select scope, coalesce(project_id, '') as project_key, name
        from assets
        where deleted_at is null
        group by scope, coalesce(project_id, ''), name
        having count(*) > 1
        """
    )
    try:
        duplicate_groups = await duplicate_cursor.fetchall()
    finally:
        await duplicate_cursor.close()

    now = datetime.now(UTC).isoformat()
    for group in duplicate_groups:
        project_id = str(group["project_key"]) or None
        asset_cursor = await db.execute(
            """
            select asset_id, name, text_content, metadata_json
            from assets
            where scope = ? and project_id is ? and name = ? and deleted_at is null
            order by created_at asc, asset_id asc
            """,
            (group["scope"], project_id, group["name"]),
        )
        try:
            rows = await asset_cursor.fetchall()
        finally:
            await asset_cursor.close()
        for row in rows[1:]:
            new_name = await _deduplicated_asset_name(
                db,
                scope=str(group["scope"]),
                project_id=project_id,
                base_name=str(row["name"]),
                asset_id=str(row["asset_id"]),
            )
            search_text = f"{new_name}\n{row['text_content'] or ''}\n{row['metadata_json']}"
            await db.execute(
                "update assets set name = ?, updated_at = ? where asset_id = ?",
                (new_name, now, row["asset_id"]),
            )
            await db.execute(
                "update asset_search_fts set search_text = ? where asset_id = ?",
                (search_text, row["asset_id"]),
            )
            await db.execute(
                "update asset_index_entries set search_text = ?, updated_at = ? where asset_id = ?",
                (new_name, now, row["asset_id"]),
            )


async def _deduplicated_asset_name(
    db,
    *,
    scope: str,
    project_id: str | None,
    base_name: str,
    asset_id: str,
) -> str:
    suffix = asset_id[-8:] if len(asset_id) >= 8 else asset_id
    candidate = f"{base_name}_{suffix}"
    counter = 2
    while await _asset_name_exists(db, scope=scope, project_id=project_id, name=candidate):
        candidate = f"{base_name}_{suffix}_{counter}"
        counter += 1
    return candidate


async def _asset_name_exists(
    db,
    *,
    scope: str,
    project_id: str | None,
    name: str,
) -> bool:
    cursor = await db.execute(
        """
        select 1
        from assets
        where scope = ? and project_id is ? and name = ? and deleted_at is null
        limit 1
        """,
        (scope, project_id, name),
    )
    try:
        return await cursor.fetchone() is not None
    finally:
        await cursor.close()


async def _ensure_live_asset_name_unique_index(db) -> None:
    await db.execute(
        """
        create unique index if not exists idx_assets_live_scope_project_name
        on assets(scope, coalesce(project_id, ''), name)
        where deleted_at is null
        """
    )


async def _normalize_global_asset_scope(db) -> None:
    now = datetime.now(UTC).isoformat()
    await _deduplicate_global_assets_for_project_scope(db, now=now)
    await _merge_global_tags_into_global_project(db)
    await db.execute(
        """
        update asset_collections
        set scope = 'project', project_id = ?, updated_at = ?
        where scope = 'global'
        """,
        (GLOBAL_PROJECT_ID, now),
    )
    await db.execute(
        """
        update assets
        set scope = 'project', project_id = ?, updated_at = ?
        where scope = 'global'
        """,
        (GLOBAL_PROJECT_ID, now),
    )
    await db.execute(
        """
        update asset_index_entries
        set scope = 'project', project_id = ?, updated_at = ?
        where scope = 'global'
        """,
        (GLOBAL_PROJECT_ID, now),
    )
    await db.execute(
        """
        update asset_search_fts
        set scope = 'project', project_id = ?
        where scope = 'global'
        """,
        (GLOBAL_PROJECT_ID,),
    )


async def _deduplicate_global_assets_for_project_scope(db, *, now: str) -> None:
    cursor = await db.execute(
        """
        select asset_id, name, text_content, metadata_json
        from assets
        where scope = 'global' and deleted_at is null
        order by created_at asc, asset_id asc
        """
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()

    reserved_names: set[str] = set()
    for row in rows:
        name = str(row["name"])
        if name in reserved_names or await _asset_name_exists(
            db,
            scope="project",
            project_id=GLOBAL_PROJECT_ID,
            name=name,
        ):
            new_name = await _deduplicated_asset_name(
                db,
                scope="project",
                project_id=GLOBAL_PROJECT_ID,
                base_name=name,
                asset_id=str(row["asset_id"]),
            )
            search_text = f"{new_name}\n{row['text_content'] or ''}\n{row['metadata_json']}"
            await db.execute(
                "update assets set name = ?, updated_at = ? where asset_id = ?",
                (new_name, now, row["asset_id"]),
            )
            await db.execute(
                "update asset_search_fts set search_text = ? where asset_id = ?",
                (search_text, row["asset_id"]),
            )
            await db.execute(
                "update asset_index_entries set search_text = ?, updated_at = ? where asset_id = ?",
                (new_name, now, row["asset_id"]),
            )
            reserved_names.add(new_name)
        else:
            reserved_names.add(name)


async def _merge_global_tags_into_global_project(db) -> None:
    cursor = await db.execute(
        """
        select tag_id, name
        from asset_tags
        where scope = 'global'
        order by created_at asc, tag_id asc
        """
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()

    now = datetime.now(UTC).isoformat()
    for row in rows:
        target_id = await _asset_tag_id_by_name(
            db,
            scope="project",
            project_id=GLOBAL_PROJECT_ID,
            name=str(row["name"]),
        )
        if target_id is not None:
            await db.execute(
                "update asset_index_entries set tag_id = ?, updated_at = ? where tag_id = ?",
                (target_id, now, row["tag_id"]),
            )
            await db.execute("delete from asset_tags where tag_id = ?", (row["tag_id"],))
            continue
        await db.execute(
            """
            update asset_tags
            set scope = 'project', project_id = ?, updated_at = ?
            where tag_id = ?
            """,
            (GLOBAL_PROJECT_ID, now, row["tag_id"]),
        )


async def _ensure_unique_asset_tag_names(db) -> None:
    duplicate_cursor = await db.execute(
        """
        select scope, coalesce(project_id, '') as project_key, name
        from asset_tags
        group by scope, coalesce(project_id, ''), name
        having count(*) > 1
        """
    )
    try:
        duplicate_groups = await duplicate_cursor.fetchall()
    finally:
        await duplicate_cursor.close()

    now = datetime.now(UTC).isoformat()
    for group in duplicate_groups:
        project_id = str(group["project_key"]) or None
        tag_cursor = await db.execute(
            """
            select tag_id, name
            from asset_tags
            where scope = ? and project_id is ? and name = ?
            order by created_at asc, tag_id asc
            """,
            (group["scope"], project_id, group["name"]),
        )
        try:
            rows = await tag_cursor.fetchall()
        finally:
            await tag_cursor.close()
        for row in rows[1:]:
            new_name = await _deduplicated_asset_tag_name(
                db,
                scope=str(group["scope"]),
                project_id=project_id,
                base_name=str(row["name"]),
                tag_id=str(row["tag_id"]),
            )
            await db.execute(
                "update asset_tags set name = ?, updated_at = ? where tag_id = ?",
                (new_name, now, row["tag_id"]),
            )


async def _deduplicated_asset_tag_name(
    db,
    *,
    scope: str,
    project_id: str | None,
    base_name: str,
    tag_id: str,
) -> str:
    suffix = tag_id[-8:] if len(tag_id) >= 8 else tag_id
    candidate = f"{base_name}_{suffix}"
    counter = 2
    while await _asset_tag_name_exists(db, scope=scope, project_id=project_id, name=candidate):
        candidate = f"{base_name}_{suffix}_{counter}"
        counter += 1
    return candidate


async def _asset_tag_name_exists(
    db,
    *,
    scope: str,
    project_id: str | None,
    name: str,
) -> bool:
    cursor = await db.execute(
        """
        select 1
        from asset_tags
        where scope = ? and project_id is ? and name = ?
        limit 1
        """,
        (scope, project_id, name),
    )
    try:
        return await cursor.fetchone() is not None
    finally:
        await cursor.close()


async def _asset_tag_id_by_name(
    db,
    *,
    scope: str,
    project_id: str | None,
    name: str,
) -> str | None:
    cursor = await db.execute(
        """
        select tag_id
        from asset_tags
        where scope = ? and project_id is ? and name = ?
        limit 1
        """,
        (scope, project_id, name),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return str(row["tag_id"]) if row is not None else None


async def _ensure_asset_tag_name_unique_index(db) -> None:
    await db.execute(
        """
        create unique index if not exists idx_asset_tags_scope_project_name
        on asset_tags(scope, coalesce(project_id, ''), name)
        """
    )


async def _ensure_global_project(db) -> None:
    now = datetime.now(UTC).isoformat()
    await db.execute(
        """
        insert or ignore into users (
          user_id, username, password_hash, status, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            GLOBAL_PROJECT_OWNER_USER_ID,
            GLOBAL_PROJECT_OWNER_USERNAME,
            hash_password(GLOBAL_PROJECT_OWNER_PASSWORD),
            "system",
            now,
            now,
        ),
    )
    await db.execute(
        """
        update users
        set status = 'system'
        where user_id = ?
        """,
        (GLOBAL_PROJECT_OWNER_USER_ID,),
    )
    await db.execute(
        """
        insert or ignore into projects (
          project_id, owner_user_id, name, description, status, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            GLOBAL_PROJECT_ID,
            GLOBAL_PROJECT_OWNER_USER_ID,
            GLOBAL_PROJECT_NAME,
            GLOBAL_PROJECT_DESCRIPTION,
            "active",
            now,
            now,
        ),
    )
    await db.execute(
        """
        update projects
        set name = ?, description = ?, status = 'active'
        where project_id = ?
        """,
        (GLOBAL_PROJECT_NAME, GLOBAL_PROJECT_DESCRIPTION, GLOBAL_PROJECT_ID),
    )
