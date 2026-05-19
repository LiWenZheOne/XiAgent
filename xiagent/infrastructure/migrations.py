from __future__ import annotations

from pathlib import Path

from xiagent.infrastructure.database import connect_db

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
