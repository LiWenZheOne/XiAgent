# XiAgent 后端 MVP Implementation Plan

> **输入语义更新提示：** 本历史实施计划中涉及 `input_data`、`$workflow.input.*` 和 workflow 级业务输入的片段已被当前 runtime 节点输入规则取代。新实现和评审以 `docs/development/2026-05-28-02-runtime-node-input-cleanup-guidelines.md` 为准，旧术语仅作为历史记录。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 XiAgent 第一版后端闭环：用户和项目、资产库、工作流契约、节点注册、任务执行、人工等待与恢复、DeepSeek 测试 AI 节点、REST API。

**Architecture:** 使用模块化单体。核心接口使用 `ABC` 和 dataclass，不依赖 LangGraph、PydanticAI、FastAPI、SQLite 或 DeepSeek SDK；第三方库放在 adapter、infrastructure、api 或具体节点实现中。任务执行状态使用不可变节点执行记录和事件，当前状态由 `TaskView` 派生。

**Tech Stack:** Python 3.11+、FastAPI、SQLite、aiosqlite、jsonschema、PyYAML、LangGraph、OpenAI Python SDK 兼容 DeepSeek、pytest、pytest-asyncio。

---

## 参考文档

- 项目规则：`AGENTS.md`
- 架构总览：`docs/project-architecture/2026-05-19-01-xiagent-architecture-overview.md`
- 用户模块设计：`docs/design/2026-05-19-02-user-project-module-design.md`
- 资产模块设计：`docs/design/2026-05-19-03-asset-module-design.md`
- 工作流契约设计：`docs/design/2026-05-19-04-workflow-contract-design.md`
- 节点与运行时设计：`docs/design/2026-05-19-05-node-runtime-task-design.md`
- API 设计：`docs/design/2026-05-19-06-api-integration-design.md`
- DeepSeek 官方 API 文档：`https://api-docs.deepseek.com/`
- DeepSeek Chat Completion 文档：`https://api-docs.deepseek.com/api/create-chat-completion`

## 密钥与环境变量

DeepSeek API key 不写入代码、文档、测试数据、提交记录或命令行参数。实现只读取环境变量：

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

用户曾在对话中贴出过 key，执行实现或测试前应在 DeepSeek 控制台轮换密钥，并在本机环境变量中设置新 key。

## 文件结构

```text
pyproject.toml
README.md
.env.example
xiagent/
  __init__.py
  core/
    __init__.py
    errors.py
    ids.py
    schemas.py
    services.py
    types.py
  users/
    __init__.py
    models.py
    service.py
    sqlite_repository.py
  assets/
    __init__.py
    models.py
    service.py
    sqlite_repository.py
    local_storage.py
  nodes/
    __init__.py
    base.py
    registry.py
    system/
      __init__.py
      human_approval.py
    ai/
      __init__.py
      deepseek_chat.py
    tools/
      __init__.py
      echo_tool.py
  workflows/
    __init__.py
    models.py
    loader.py
    validator.py
    service.py
  runtime/
    __init__.py
    models.py
    execution_store.py
    input_resolver.py
    service.py
    task_view.py
  adapters/
    __init__.py
    langgraph/
      __init__.py
      adapter.py
  infrastructure/
    __init__.py
    config.py
    database.py
    migrations.py
    password.py
  api/
    __init__.py
    app.py
    dependencies.py
    error_handlers.py
    routers/
      __init__.py
      auth.py
      projects.py
      assets.py
      workflows.py
      nodes.py
      tasks.py
workflows/
  global/
    deepseek_echo.workflow.yaml
storage/
  assets/
tests/
  conftest.py
  test_users_service.py
  test_assets_service.py
  test_node_registry.py
  test_workflow_validator.py
  test_runtime_service.py
  test_api_smoke.py
```

## Task 1: 项目骨架、配置和基础工具

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `xiagent/__init__.py`
- Create: `xiagent/infrastructure/config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建依赖和测试配置**

Create `pyproject.toml`:

```toml
[project]
name = "xiagent"
version = "0.1.0"
description = "Contract-driven agent workflow backend platform"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "aiosqlite>=0.20.0",
  "jsonschema>=4.23.0",
  "PyYAML>=6.0.2",
  "langgraph>=1.0.0",
  "openai>=1.0.0",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "pytest-asyncio>=0.23.0",
  "httpx>=0.27.0",
  "ruff>=0.6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: 创建环境变量样例**

Create `.env.example`:

```text
XIAGENT_DATABASE_PATH=.data/xiagent.sqlite3
XIAGENT_ASSET_STORAGE_DIR=storage/assets
XIAGENT_WORKFLOW_DIR=workflows
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

- [ ] **Step 3: 创建配置对象**

Create `xiagent/infrastructure/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    asset_storage_dir: Path
    workflow_dir: Path
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.getenv("XIAGENT_DATABASE_PATH", ".data/xiagent.sqlite3")),
        asset_storage_dir=Path(os.getenv("XIAGENT_ASSET_STORAGE_DIR", "storage/assets")),
        workflow_dir=Path(os.getenv("XIAGENT_WORKFLOW_DIR", "workflows")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    )
```

- [ ] **Step 4: 创建测试 fixture**

Create `tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from xiagent.infrastructure.config import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "xiagent-test.sqlite3",
        asset_storage_dir=tmp_path / "assets",
        workflow_dir=tmp_path / "workflows",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
    )
```

- [ ] **Step 5: 运行基础检查**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with no tests collected or all existing tests passing.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml .env.example README.md xiagent tests
git commit -m "chore: scaffold backend project"
```

## Task 2: 核心类型、错误和服务接口

**Files:**
- Create: `xiagent/core/errors.py`
- Create: `xiagent/core/types.py`
- Create: `xiagent/core/schemas.py`
- Create: `xiagent/core/services.py`
- Create: `xiagent/core/ids.py`
- Create: `tests/test_core_contracts.py`

- [ ] **Step 1: 写核心契约测试**

Create `tests/test_core_contracts.py`:

```python
from __future__ import annotations

from xiagent.core.ids import new_id
from xiagent.core.schemas import validate_json_schema
from xiagent.core.types import Scope


def test_new_id_has_prefix() -> None:
    value = new_id("task")
    assert value.startswith("task_")
    assert len(value) > len("task_")


def test_validate_json_schema_accepts_object_schema() -> None:
    validate_json_schema({"type": "object", "properties": {"name": {"type": "string"}}})


def test_scope_values_are_stable() -> None:
    assert Scope.GLOBAL == "global"
    assert Scope.PROJECT == "project"
    assert Scope.COMBINED == "combined"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_core_contracts.py -q
```

Expected: FAIL because `xiagent.core` modules do not exist.

- [ ] **Step 3: 实现核心错误、ID 和 schema 校验**

Create `xiagent/core/errors.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class XiAgentError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(XiAgentError):
    pass


class NotFoundError(XiAgentError):
    pass


class PermissionDeniedError(XiAgentError):
    pass


class ConflictError(XiAgentError):
    pass


class ExternalServiceError(XiAgentError):
    pass
```

Create `xiagent/core/ids.py`:

```python
from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    clean_prefix = prefix.strip().lower().replace("-", "_")
    if not clean_prefix:
        raise ValueError("prefix must not be empty")
    return f"{clean_prefix}_{uuid4().hex}"
```

Create `xiagent/core/schemas.py`:

```python
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from xiagent.core.errors import ValidationError


def validate_json_schema(schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(
            code="invalid_json_schema",
            message="JSON Schema 格式无效",
            details={"error": str(exc)},
        ) from exc


def validate_json_value(schema: dict[str, Any], value: Any) -> None:
    validate_json_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: item.path)
    if errors:
        first = errors[0]
        raise ValidationError(
            code="json_value_validation_failed",
            message="数据不满足 JSON Schema",
            details={"path": list(first.path), "error": first.message},
        )
```

Create `xiagent/core/types.py`:

```python
from __future__ import annotations

from typing import Literal

Scope = Literal["global", "project", "combined"]
StoredScope = Literal["global", "project"]

TaskStatus = Literal["created", "running", "waiting", "succeeded", "failed", "canceled"]
NodeExecutionStatus = Literal["created", "running", "waiting", "succeeded", "failed"]
NodeResultStatus = Literal["succeeded", "waiting", "failed"]
AssetType = Literal["file", "text"]
```

- [ ] **Step 4: 定义服务接口**

Create `xiagent/core/services.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class UserService(ABC):
    @abstractmethod
    async def ensure_project_access(self, *, user_id: str, project_id: str, action: str) -> None:
        raise NotImplementedError


class AssetService(ABC):
    @abstractmethod
    async def get_asset(self, *, user_id: str, asset_id: str, project_id: str | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def get_asset_content(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> Any:
        raise NotImplementedError


class WorkflowService(ABC):
    @abstractmethod
    async def get_template(self, *, template_id: str, user_id: str, project_id: str) -> Any:
        raise NotImplementedError


class RuntimeService(ABC):
    @abstractmethod
    async def create_task(
        self,
        *,
        user_id: str,
        project_id: str,
        template_id: str,
        input_data: dict[str, Any],
    ) -> Any:
        raise NotImplementedError
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```powershell
python -m pytest tests/test_core_contracts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add xiagent/core tests/test_core_contracts.py
git commit -m "feat: add core contracts"
```

## Task 3: SQLite 基础设施和迁移

**Files:**
- Create: `xiagent/infrastructure/database.py`
- Create: `xiagent/infrastructure/migrations.py`
- Create: `tests/test_database_migrations.py`

- [ ] **Step 1: 写迁移测试**

Create `tests/test_database_migrations.py`:

```python
from __future__ import annotations

import aiosqlite

from xiagent.infrastructure.migrations import migrate


async def test_migrate_creates_core_tables(test_settings) -> None:
    await migrate(test_settings.database_path)
    async with aiosqlite.connect(test_settings.database_path) as db:
        cursor = await db.execute(
            "select name from sqlite_master where type='table' and name='users'"
        )
        row = await cursor.fetchone()
    assert row == ("users",)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_database_migrations.py -q
```

Expected: FAIL because migration module does not exist.

- [ ] **Step 3: 实现数据库连接和迁移**

Create `xiagent/infrastructure/database.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


@asynccontextmanager
async def connect_db(path: Path) -> AsyncIterator[aiosqlite.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("pragma foreign_keys = on")
    try:
        yield db
        await db.commit()
    finally:
        await db.close()
```

Create `xiagent/infrastructure/migrations.py` with tables for users, projects, assets, asset bindings, collections, tags, workflows, tasks, node executions and task events. Use `text` for JSON fields and store timestamps as ISO strings. Include this first table exactly:

```python
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
  project_id text,
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
  project_id text,
  parent_id text,
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
  project_id text,
  name text not null,
  description text,
  created_by text not null references users(user_id),
  created_at text not null,
  updated_at text not null
);

create table if not exists asset_index_entries (
  entry_id text primary key,
  scope text not null,
  project_id text,
  asset_id text not null references assets(asset_id),
  collection_id text,
  tag_id text,
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
  project_id text,
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
```

- [ ] **Step 4: 运行迁移测试**

Run:

```powershell
python -m pytest tests/test_database_migrations.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/infrastructure/database.py xiagent/infrastructure/migrations.py tests/test_database_migrations.py
git commit -m "feat: add sqlite migrations"
```

## Task 4: 用户与项目模块

**Files:**
- Create: `xiagent/infrastructure/password.py`
- Create: `xiagent/users/models.py`
- Create: `xiagent/users/sqlite_repository.py`
- Create: `xiagent/users/service.py`
- Create: `tests/test_users_service.py`

- [ ] **Step 1: 写用户服务测试**

Create `tests/test_users_service.py`:

```python
from __future__ import annotations

import pytest

from xiagent.core.errors import PermissionDeniedError
from xiagent.infrastructure.migrations import migrate
from xiagent.users.service import SqliteUserService


async def test_user_can_create_project_and_access_it(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    user = await service.create_user(username="alice", password="secret-123")
    auth = await service.authenticate(username="alice", password="secret-123")
    project = await service.create_project(owner_user_id=user.user_id, name="漫画项目A")

    assert auth.user.user_id == user.user_id
    assert project.owner_user_id == user.user_id
    await service.ensure_project_access(
        user_id=user.user_id,
        project_id=project.project_id,
        action="task:create",
    )


async def test_user_cannot_access_other_users_project(test_settings) -> None:
    await migrate(test_settings.database_path)
    service = SqliteUserService(test_settings.database_path)
    alice = await service.create_user(username="alice", password="secret-123")
    bob = await service.create_user(username="bob", password="secret-456")
    project = await service.create_project(owner_user_id=alice.user_id, name="漫画项目A")

    with pytest.raises(PermissionDeniedError):
        await service.ensure_project_access(
            user_id=bob.user_id,
            project_id=project.project_id,
            action="task:create",
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_users_service.py -q
```

Expected: FAIL because user service modules do not exist.

- [ ] **Step 3: 实现密码工具**

Create `xiagent/infrastructure/password.py`:

```python
from __future__ import annotations

import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    algorithm, salt, expected = password_hash.split("$", 2)
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return hmac.compare_digest(digest.hex(), expected)
```

- [ ] **Step 4: 实现用户模型**

Create `xiagent/users/models.py` with frozen dataclasses:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserRecord:
    user_id: str
    username: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: str
    owner_user_id: str
    name: str
    description: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: UserRecord
```

- [ ] **Step 5: 实现 SqliteUserService**

Create `xiagent/users/service.py` using `connect_db`, `new_id`, `hash_password`, `verify_password`. Required behavior:

```text
create_user: duplicate username raises ConflictError(code="username_exists")
authenticate: wrong username or password raises PermissionDeniedError(code="invalid_credentials")
create_project: project owner must exist
ensure_project_access: only owner can access active project in first version
```

Expose class:

```python
class SqliteUserService(UserService):
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
```

- [ ] **Step 6: 运行用户测试**

Run:

```powershell
python -m pytest tests/test_users_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add xiagent/infrastructure/password.py xiagent/users tests/test_users_service.py
git commit -m "feat: add user and project service"
```

## Task 5: 资产模块最小闭环

**Files:**
- Create: `xiagent/assets/models.py`
- Create: `xiagent/assets/local_storage.py`
- Create: `xiagent/assets/service.py`
- Create: `tests/test_assets_service.py`

- [ ] **Step 1: 写资产服务测试**

Create `tests/test_assets_service.py`:

```python
from __future__ import annotations

from xiagent.assets.service import SqliteAssetService
from xiagent.infrastructure.migrations import migrate
from xiagent.users.service import SqliteUserService


async def test_create_text_asset_and_search_project_scope(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="女主设定",
        text="女主是调查记者，冷静、敏锐。",
        metadata={"kind": "character"},
    )
    result = await assets.search_assets(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        keyword="调查记者",
    )

    assert asset.asset_type == "text"
    assert [item.asset_id for item in result.items] == [asset.asset_id]


async def test_import_file_asset_deduplicates_by_hash(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )

    first = await assets.import_file_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        file_name="role.txt",
        content_type="text/plain",
        content=b"shared asset",
        metadata={},
    )
    second = await assets.import_file_asset(
        user_id=user.user_id,
        scope="global",
        project_id=None,
        file_name="role-copy.txt",
        content_type="text/plain",
        content=b"shared asset",
        metadata={},
    )

    assert first.content_hash == second.content_hash
    assert first.storage_uri == second.storage_uri
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_assets_service.py -q
```

Expected: FAIL because asset modules do not exist.

- [ ] **Step 3: 实现资产模型**

Create `xiagent/assets/models.py` with dataclasses:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AssetRecord:
    asset_id: str
    scope: str
    project_id: str | None
    asset_type: str
    name: str
    mime_type: str | None
    content_hash: str | None
    size_bytes: int | None
    storage_uri: str | None
    text_content: str | None
    metadata: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str
    deleted_at: str | None


@dataclass(frozen=True, slots=True)
class AssetContent:
    asset_id: str
    asset_type: str
    content_type: str | None
    bytes_content: bytes | None = None
    text_content: str | None = None


@dataclass(frozen=True, slots=True)
class AssetSearchResult:
    items: list[AssetRecord] = field(default_factory=list)
    total: int = 0
```

- [ ] **Step 4: 实现本地文件存储**

Create `xiagent/assets/local_storage.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path


class LocalAssetStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def put_bytes(self, *, file_name: str, content: bytes) -> tuple[str, str, int]:
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(file_name).suffix
        target = self._root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        return digest, target.relative_to(self._root).as_posix(), len(content)

    def read_bytes(self, storage_uri: str) -> bytes:
        return (self._root / storage_uri).read_bytes()
```

- [ ] **Step 5: 实现 SqliteAssetService**

Create `xiagent/assets/service.py`. Required behavior:

```text
scope="global": project_id must be None
scope="project": project_id must be provided and UserService.ensure_project_access is called
create_text_asset: insert asset and FTS row
import_file_asset: write content through LocalAssetStorage, insert asset and FTS row
search_assets: support keyword, scope=global/project/combined, project_id, asset_type
delete_asset: soft delete by setting deleted_at
```

The class constructor:

```python
class SqliteAssetService(AssetService):
    def __init__(self, *, database_path: Path, storage_dir: Path, user_service: UserService) -> None:
        self._database_path = database_path
        self._storage = LocalAssetStorage(storage_dir)
        self._user_service = user_service
```

- [ ] **Step 6: 运行资产测试**

Run:

```powershell
python -m pytest tests/test_assets_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add xiagent/assets tests/test_assets_service.py
git commit -m "feat: add asset service"
```

## Task 6: 节点基类、注册表、人工节点和 DeepSeek 测试节点

**Files:**
- Create: `xiagent/nodes/base.py`
- Create: `xiagent/nodes/registry.py`
- Create: `xiagent/nodes/system/human_approval.py`
- Create: `xiagent/nodes/tools/echo_tool.py`
- Create: `xiagent/nodes/ai/deepseek_chat.py`
- Create: `tests/test_node_registry.py`
- Create: `tests/test_deepseek_node.py`

- [ ] **Step 1: 写节点注册测试**

Create `tests/test_node_registry.py`:

```python
from __future__ import annotations

import pytest

from xiagent.core.errors import ConflictError
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode


def test_register_and_get_node() -> None:
    registry = NodeRegistry()
    node = HumanApprovalNode()
    registry.register(node)
    assert registry.get("system.human_approval.v1") is node


def test_duplicate_node_ref_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    with pytest.raises(ConflictError):
        registry.register(HumanApprovalNode())
```

- [ ] **Step 2: 写 DeepSeek 节点无密钥测试**

Create `tests/test_deepseek_node.py`:

```python
from __future__ import annotations

import pytest

from xiagent.core.errors import ValidationError
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode


async def test_deepseek_node_requires_api_key() -> None:
    node = DeepSeekChatNode(api_key=None, base_url="https://api.deepseek.com", model="deepseek-v4-flash")
    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": "你好"})
    assert exc.value.code == "deepseek_api_key_missing"
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_node_registry.py tests/test_deepseek_node.py -q
```

Expected: FAIL because node modules do not exist.

- [ ] **Step 4: 实现节点基类**

Create `xiagent/nodes/base.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class NodeDescriptor:
    ref: str
    name: str
    version: str
    kind: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any] | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class AssetRef:
    asset_id: str
    usage_type: str
    source: str


@dataclass(frozen=True, slots=True)
class NodeResult:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    asset_refs: list[AssetRef] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NodeContext:
    user_id: str
    project_id: str
    task_id: str
    node_id: str
    node_execution_id: str
    config: dict[str, Any]
    asset_service: Any
    event_sink: Any
    logger: Any


class BaseNode(ABC):
    @abstractmethod
    def describe(self) -> NodeDescriptor:
        raise NotImplementedError

    @abstractmethod
    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        raise NotImplementedError
```

- [ ] **Step 5: 实现注册表和内置节点**

Create `xiagent/nodes/registry.py`:

```python
from __future__ import annotations

from xiagent.core.errors import ConflictError, NotFoundError
from xiagent.core.schemas import validate_json_schema
from xiagent.nodes.base import BaseNode


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, BaseNode] = {}

    def register(self, node: BaseNode) -> None:
        if not isinstance(node, BaseNode):
            raise TypeError("node must inherit BaseNode")
        descriptor = node.describe()
        if descriptor.ref in self._nodes:
            raise ConflictError(
                code="node_ref_exists",
                message="节点 ref 已存在",
                details={"ref": descriptor.ref},
            )
        validate_json_schema(descriptor.input_schema)
        validate_json_schema(descriptor.output_schema)
        self._nodes[descriptor.ref] = node

    def get(self, ref: str) -> BaseNode:
        try:
            return self._nodes[ref]
        except KeyError as exc:
            raise NotFoundError(
                code="node_not_found",
                message="节点不存在",
                details={"ref": ref},
            ) from exc

    def list(self) -> list[BaseNode]:
        return list(self._nodes.values())
```

Create `xiagent/nodes/system/human_approval.py`:

```python
from __future__ import annotations

from typing import Any, Mapping

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class HumanApprovalNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="system.human_approval.v1",
            name="人工确认",
            version="1.0.0",
            kind="system",
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "required": ["decision"],
                "properties": {"decision": {"type": "string"}},
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="waiting", output={}, metadata={"requested_inputs": dict(inputs)})
```

Create `xiagent/nodes/tools/echo_tool.py`:

```python
from __future__ import annotations

from typing import Any, Mapping

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class EchoToolNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="tool.echo.v1",
            name="Echo Tool",
            version="1.0.0",
            kind="tool",
            input_schema={"type": "object"},
            output_schema={"type": "object", "properties": {"echo": {"type": "object"}}},
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="succeeded", output={"echo": dict(inputs)})
```

- [ ] **Step 6: 实现 DeepSeek 测试节点**

Create `xiagent/nodes/ai/deepseek_chat.py`:

```python
from __future__ import annotations

from typing import Any, Mapping

from openai import AsyncOpenAI

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class DeepSeekChatNode(BaseNode):
    def __init__(self, *, api_key: str | None, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="ai.deepseek_chat.v1",
            name="DeepSeek Chat",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "system": {"type": "string"},
                    "prompt": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string"},
                    "model": {"type": "string"},
                    "usage": {"type": "object"},
                },
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if not self._api_key:
            raise ValidationError(
                code="deepseek_api_key_missing",
                message="未配置 DEEPSEEK_API_KEY",
                details={},
            )
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(
                code="deepseek_prompt_required",
                message="DeepSeek 节点需要非空 prompt",
                details={},
            )
        messages: list[dict[str, str]] = []
        system = inputs.get("system")
        if isinstance(system, str) and system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=False,
                thinking={"type": "disabled"},
            )
        except Exception as exc:
            raise ExternalServiceError(
                code="deepseek_request_failed",
                message="DeepSeek API 调用失败",
                details={"error": str(exc)},
            ) from exc

        choice = response.choices[0]
        return NodeResult(
            status="succeeded",
            output={
                "text": choice.message.content or "",
                "model": response.model,
                "usage": response.usage.model_dump() if response.usage else {},
            },
            metadata={"provider": "deepseek", "base_url": self._base_url},
        )
```

- [ ] **Step 7: 运行节点测试**

Run:

```powershell
python -m pytest tests/test_node_registry.py tests/test_deepseek_node.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add xiagent/nodes tests/test_node_registry.py tests/test_deepseek_node.py
git commit -m "feat: add node registry and deepseek node"
```

## Task 7: 工作流契约加载和校验

**Files:**
- Create: `xiagent/workflows/models.py`
- Create: `xiagent/workflows/loader.py`
- Create: `xiagent/workflows/validator.py`
- Create: `xiagent/workflows/service.py`
- Create: `workflows/global/deepseek_echo.workflow.yaml`
- Create: `tests/test_workflow_validator.py`

- [ ] **Step 1: 写工作流校验测试**

Create `tests/test_workflow_validator.py`:

```python
from __future__ import annotations

import pytest

from xiagent.core.errors import ValidationError
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.workflows.validator import validate_workflow_contract


def test_valid_workflow_contract_is_accepted() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = {
        "workflow": {
            "id": "echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Echo",
            "input_schema": {"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}},
        },
        "nodes": [
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {"type": "object", "properties": {"echo": {"type": "object"}}},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    }
    validate_workflow_contract(contract, registry)


def test_unknown_node_ref_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    contract = {
        "workflow": {
            "id": "bad",
            "version": "1.0.0",
            "scope": "global",
            "name": "Bad",
            "input_schema": {"type": "object"},
        },
        "nodes": [{"id": "missing", "ref": "tool.missing.v1", "inputs": {}, "outputs": {"type": "object"}}],
        "edges": [{"from": "START", "to": "missing"}, {"from": "missing", "to": "END"}],
    }
    with pytest.raises(ValidationError):
        validate_workflow_contract(contract, registry)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py -q
```

Expected: FAIL because workflow modules do not exist.

- [ ] **Step 3: 实现工作流模型和 loader**

Create `xiagent/workflows/models.py` with dataclasses `WorkflowTemplateRecord`, `WorkflowNodeSpec`, `WorkflowEdgeSpec`.

Create `xiagent/workflows/loader.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_workflow_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"workflow file must contain object: {path}")
    return data
```

- [ ] **Step 4: 实现契约校验**

Create `xiagent/workflows/validator.py`. Required behavior:

```text
workflow/id/version/scope/name/input_schema required
nodes must be non-empty list
node id unique
node ref must exist in NodeRegistry
node outputs must be valid JSON Schema
inputs must use "$workflow.input." or "$nodes.<node_id>.output." format
edges can use START and END
all edge node references must exist
detect cycles with depth-first search
```

Public function:

```python
def validate_workflow_contract(contract: dict[str, Any], registry: NodeRegistry) -> None:
    raise NotImplementedError
```

- [ ] **Step 5: 创建 DeepSeek 示例工作流**

Create `workflows/global/deepseek_echo.workflow.yaml`:

```yaml
workflow:
  id: deepseek_echo
  version: "1.0.0"
  scope: global
  name: DeepSeek 测试工作流
  description: 使用 DeepSeek 节点回复输入内容
  input_schema:
    type: object
    required: ["prompt"]
    properties:
      prompt:
        type: string

nodes:
  - id: chat
    ref: ai.deepseek_chat.v1
    inputs:
      prompt:
        from: "$workflow.input.prompt"
    outputs:
      type: object
      required: ["text"]
      properties:
        text:
          type: string
        model:
          type: string
        usage:
          type: object

edges:
  - from: START
    to: chat
  - from: chat
    to: END
```

- [ ] **Step 6: 运行工作流测试**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add xiagent/workflows workflows/global/deepseek_echo.workflow.yaml tests/test_workflow_validator.py
git commit -m "feat: add workflow contract validation"
```

## Task 8: 任务运行、输入解析、事件和等待恢复

**Files:**
- Create: `xiagent/runtime/models.py`
- Create: `xiagent/runtime/execution_store.py`
- Create: `xiagent/runtime/input_resolver.py`
- Create: `xiagent/runtime/task_view.py`
- Create: `xiagent/runtime/service.py`
- Create: `tests/test_runtime_service.py`

- [ ] **Step 1: 写运行时测试**

Create `tests/test_runtime_service.py`:

```python
from __future__ import annotations

from xiagent.infrastructure.migrations import migrate
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.service import SqliteUserService


async def test_simple_workflow_task_succeeds(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
    )
    contract = {
        "workflow": {
            "id": "echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Echo",
            "input_schema": {"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}},
        },
        "nodes": [
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    }

    task = await runtime.create_task_from_contract(
        user_id=user.user_id,
        project_id=project.project_id,
        contract=contract,
        input_data={"topic": "测试"},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(task_id=task.task_id)
    assert executions[0].input_snapshot == {"topic": "测试"}
    assert executions[0].output_snapshot == {"echo": {"topic": "测试"}}


async def test_human_node_waits_and_resume_succeeds(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
    )
    contract = {
        "workflow": {
            "id": "approval",
            "version": "1.0.0",
            "scope": "global",
            "name": "Approval",
            "input_schema": {"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}},
        },
        "nodes": [
            {
                "id": "review",
                "ref": "system.human_approval.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {
                    "type": "object",
                    "required": ["decision"],
                    "properties": {"decision": {"type": "string"}},
                },
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"decision": {"from": "$nodes.review.output.decision"}},
                "outputs": {"type": "object"},
            },
        ],
        "edges": [
            {"from": "START", "to": "review"},
            {"from": "review", "to": "echo", "when": {"path": "$nodes.review.output.decision", "equals": "approve"}},
            {"from": "echo", "to": "END"},
        ],
    }

    task = await runtime.create_task_from_contract(
        user_id=user.user_id,
        project_id=project.project_id,
        contract=contract,
        input_data={"topic": "测试"},
    )
    assert task.status == "waiting"

    resumed = await runtime.resume_task(
        user_id=user.user_id,
        project_id=project.project_id,
        task_id=task.task_id,
        node_id="review",
        output={"decision": "approve"},
    )
    assert resumed.status == "succeeded"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_runtime_service.py -q
```

Expected: FAIL because runtime modules do not exist.

- [ ] **Step 3: 实现运行时模型**

Create `xiagent/runtime/models.py` with frozen dataclasses:

```text
TaskRecord
NodeExecutionRecord
TaskEventRecord
```

Use dict fields for JSON snapshots:

```text
input_data
current_view
input_snapshot
output_snapshot
metadata
```

- [ ] **Step 4: 实现输入解析**

Create `xiagent/runtime/input_resolver.py`:

```python
from __future__ import annotations

from typing import Any

from xiagent.core.errors import ValidationError


def resolve_node_inputs(
    *,
    input_specs: dict[str, dict[str, str]],
    workflow_input: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for name, spec in input_specs.items():
        path = spec.get("from")
        if not isinstance(path, str):
            raise ValidationError(code="invalid_input_reference", message="输入引用必须包含 from", details={"input": name})
        resolved[name] = resolve_path(path=path, workflow_input=workflow_input, node_outputs=node_outputs)
    return resolved


def resolve_path(*, path: str, workflow_input: dict[str, Any], node_outputs: dict[str, dict[str, Any]]) -> Any:
    if path.startswith("$workflow.input."):
        key = path.removeprefix("$workflow.input.")
        return workflow_input[key]
    if path.startswith("$nodes."):
        parts = path.split(".")
        if len(parts) < 5 or parts[2] != "output":
            raise ValidationError(code="invalid_node_output_reference", message="节点输出引用格式无效", details={"path": path})
        node_id = parts[1]
        field = ".".join(parts[3:])
        value: Any = node_outputs[node_id]
        for segment in field.split("."):
            value = value[segment]
        return value
    raise ValidationError(code="unsupported_reference_path", message="不支持的引用路径", details={"path": path})
```

- [ ] **Step 5: 实现 RuntimeService**

Create `xiagent/runtime/service.py`. Required behavior:

```text
create_task_from_contract:
  validate project access
  validate workflow input schema
  insert workflow_template if needed for direct contract tests
  create task
  execute nodes from START through edges
  create node_execution before each node call
  update node_execution after result
  append task_events
  if result.status == "waiting": task.status = waiting and stop
  if END reached: task.status = succeeded

resume_task:
  validate project access
  find waiting task and waiting node_execution
  write output to waiting node_execution
  mark waiting node_execution succeeded
  continue from that node's outgoing edges
```

Use sequential DAG execution for first version. LangGraph adapter can be introduced in Task 9 after runtime semantics are stable.

- [ ] **Step 6: 运行运行时测试**

Run:

```powershell
python -m pytest tests/test_runtime_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add xiagent/runtime tests/test_runtime_service.py
git commit -m "feat: add task runtime and resume"
```

## Task 9: LangGraph 适配器

**Files:**
- Create: `xiagent/adapters/langgraph/adapter.py`
- Create: `tests/test_langgraph_adapter.py`

- [ ] **Step 1: 写适配器测试**

Create `tests/test_langgraph_adapter.py`:

```python
from __future__ import annotations

from xiagent.adapters.langgraph.adapter import LangGraphAdapter


def test_adapter_exposes_engine_name() -> None:
    adapter = LangGraphAdapter()
    assert adapter.engine_name == "langgraph"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_langgraph_adapter.py -q
```

Expected: FAIL because adapter module does not exist.

- [ ] **Step 3: 实现适配器外壳**

Create `xiagent/adapters/langgraph/adapter.py`:

```python
from __future__ import annotations


class LangGraphAdapter:
    @property
    def engine_name(self) -> str:
        return "langgraph"
```

Keep runtime first version using its own deterministic DAG walker. Introduce full LangGraph compilation after API and persistence tests are green, because waiting/resume semantics must stay owned by XiAgent runtime.

- [ ] **Step 4: 运行适配器测试**

Run:

```powershell
python -m pytest tests/test_langgraph_adapter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/adapters tests/test_langgraph_adapter.py
git commit -m "feat: add langgraph adapter boundary"
```

## Task 10: FastAPI 应用和 REST API

**Files:**
- Create: `xiagent/api/app.py`
- Create: `xiagent/api/dependencies.py`
- Create: `xiagent/api/error_handlers.py`
- Create: `xiagent/api/routers/auth.py`
- Create: `xiagent/api/routers/projects.py`
- Create: `xiagent/api/routers/assets.py`
- Create: `xiagent/api/routers/workflows.py`
- Create: `xiagent/api/routers/nodes.py`
- Create: `xiagent/api/routers/tasks.py`
- Create: `tests/test_api_smoke.py`

- [ ] **Step 1: 写 API 冒烟测试**

Create `tests/test_api_smoke.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from xiagent.api.app import create_app


def test_health_endpoint_returns_ok(test_settings) -> None:
    app = create_app(settings=test_settings)
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_api_smoke.py -q
```

Expected: FAIL because API app does not exist.

- [ ] **Step 3: 实现 FastAPI app**

Create `xiagent/api/app.py`:

```python
from __future__ import annotations

from fastapi import FastAPI

from xiagent.infrastructure.config import Settings, load_settings
from xiagent.infrastructure.migrations import migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    app = FastAPI(title="XiAgent API")
    app.state.settings = resolved_settings

    @app.on_event("startup")
    async def _startup() -> None:
        await migrate(resolved_settings.database_path)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: 实现路由外壳**

Create router modules with `APIRouter()` objects and register them in `create_app`. First version endpoints to implement:

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/projects
POST /api/projects
GET  /api/nodes
POST /api/assets/text
GET  /api/assets/search
POST /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/resume
```

Use request body `user_id` for first version authenticated calls. Add real sessions or bearer auth after service boundaries are stable.

- [ ] **Step 5: 运行 API 测试**

Run:

```powershell
python -m pytest tests/test_api_smoke.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add xiagent/api tests/test_api_smoke.py
git commit -m "feat: add fastapi app"
```

## Task 11: 组合注册和 DeepSeek 工作流手动验证

**Files:**
- Create: `xiagent/nodes/__init__.py`
- Modify: `xiagent/api/dependencies.py`
- Modify: `README.md`

- [ ] **Step 1: 实现节点注册构建函数**

Create or replace `xiagent/nodes/__init__.py`:

```python
from __future__ import annotations

from xiagent.infrastructure.config import Settings
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode


def build_node_registry(settings: Settings) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    registry.register(
        DeepSeekChatNode(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    )
    return registry
```

- [ ] **Step 2: 更新 README 运行说明**

Add to `README.md`:

```markdown
# XiAgent

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DEEPSEEK_API_KEY="替换为轮换后的 DeepSeek key"
uvicorn xiagent.api.app:app --reload
```

DeepSeek 测试节点使用：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

不要把 API key 写入代码、文档、测试数据或 Git 提交。
```

- [ ] **Step 3: 运行全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: 启动本地 API**

Run:

```powershell
uvicorn xiagent.api.app:app --host 127.0.0.1 --port 8000
```

Expected: server starts and `/api/health` returns `{"status":"ok"}`.

- [ ] **Step 5: 手动 DeepSeek 验证**

Only run this after rotating the pasted key and setting the new key in the current shell:

```powershell
$env:DEEPSEEK_API_KEY="替换为轮换后的 DeepSeek key"
```

Then create a task using `deepseek_echo.workflow.yaml` through the API or a temporary local script. Expected node output:

```json
{
  "text": "模型返回的文本",
  "model": "deepseek-v4-flash",
  "usage": {}
}
```

The exact text varies by model response. The key assertion is that task status is `succeeded`, node execution contains `input_snapshot.prompt`, and node execution contains `output_snapshot.text`.

- [ ] **Step 6: Commit**

```powershell
git add xiagent README.md
git commit -m "feat: wire backend services"
```

## Self-Review

### Spec coverage

- 用户与项目：Task 4 and API Task 10.
- 资产库：Task 5 and API Task 10.
- 工作流契约：Task 7.
- 节点强接口：Task 6.
- DeepSeek 测试 AI 节点：Task 6 and Task 11.
- 任务执行记录、等待、恢复：Task 8.
- LangGraph 边界：Task 9.
- 前端 API：Task 10.
- 密钥不落库不提交：Task 1, Task 6, Task 11.

### Placeholder scan

The plan has been scanned for incomplete markers and omitted implementation steps. Some implementation details are expressed as required behavior lists where the exact code is mechanical repository work; tests define the externally visible behavior.

### Type consistency

The plan consistently uses:

- `UserService.ensure_project_access`
- `AssetService.get_asset`
- `AssetService.get_asset_content`
- `BaseNode.describe`
- `BaseNode.run`
- `NodeResult.status`
- `SqliteRuntimeService.create_task_from_contract`
- `SqliteRuntimeService.resume_task`
- `DEEPSEEK_API_KEY`
- `deepseek-v4-flash`
