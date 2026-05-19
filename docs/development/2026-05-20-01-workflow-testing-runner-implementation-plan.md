# Workflow Testing Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个不依赖 UI 的工作流测试运行器，让开发者通过 CLI 执行 `workflows/` 下的工作流、观察节点过程、交互恢复等待节点，并预览图片产物。

**Architecture:** 在 `xiagent.workflows.testing` 下新增测试辅助模块，底层复用正式 `SqliteRuntimeService`、`SqliteUserService`、`SqliteAssetService`、`WorkflowCatalog` 和 `NodeRegistry`。CLI 使用标准库 `argparse`，交互和图片预览放在测试工具层，不改变核心工作流契约和运行时。

**Tech Stack:** Python 3.11+、argparse、asyncio、SQLite、aiosqlite、PyYAML、jsonschema、pytest、pytest-asyncio。

---

## 参考文档

- 设计文档：`docs/design/2026-05-20-01-workflow-testing-runner-design.md`
- 工作流契约：`docs/design/2026-05-19-04-workflow-contract-design.md`
- 节点与运行时：`docs/design/2026-05-19-05-node-runtime-task-design.md`
- 项目规则：`AGENTS.md`

## 文件结构

新增文件：

```text
xiagent/workflows/testing/__init__.py
xiagent/workflows/testing/builder.py
xiagent/workflows/testing/artifacts.py
xiagent/workflows/testing/console.py
xiagent/workflows/testing/runner.py
xiagent/workflows/testing_cli.py
tests/test_workflow_testing_builder.py
tests/test_workflow_testing_artifacts.py
tests/test_workflow_testing_runner.py
tests/test_workflow_testing_cli.py
```

职责：

- `builder.py`：构建测试会话，迁移数据库，装配服务，创建或复用测试用户与项目。
- `artifacts.py`：识别图片引用、保存 data URL 图片、生成 HTML 预览、打开图片或预览。
- `console.py`：封装命令行输入输出、输入 schema 提示、等待节点恢复输入。
- `runner.py`：选择工作流、创建任务、处理 waiting 恢复、聚合运行结果。
- `testing_cli.py`：解析 CLI 参数并调用测试运行器。

修改文件：

```text
README.md
```

追加 CLI 使用说明。

## Task 1: 测试会话构建器

**Files:**
- Create: `xiagent/workflows/testing/__init__.py`
- Create: `xiagent/workflows/testing/builder.py`
- Test: `tests/test_workflow_testing_builder.py`

- [ ] **Step 1: 写 builder 失败测试**

Create `tests/test_workflow_testing_builder.py`:

```python
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
```

- [ ] **Step 2: 运行 builder 测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_testing_builder.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'xiagent.workflows.testing'`.

- [ ] **Step 3: 实现 builder**

Create `xiagent/workflows/testing/__init__.py`:

```python
from __future__ import annotations

from xiagent.workflows.testing.builder import WorkflowTestBuilder, WorkflowTestSession

__all__ = ["WorkflowTestBuilder", "WorkflowTestSession"]
```

Create `xiagent/workflows/testing/builder.py`:

```python
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


@dataclass(frozen=True, slots=True)
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
        base_settings = load_settings()
        self._settings = replace(
            base_settings,
            database_path=Path(".data/workflow-test.sqlite3"),
            asset_storage_dir=Path(".data/workflow-test-assets"),
            workflow_dir=Path("workflows"),
        )
        self._username = "workflow-test-admin"
        self._password = "secret-123"
        self._project_name = "Workflow Test Project"
        self._project_id: str | None = None
        self._run_output_dir: Path | None = None

    def with_database_path(self, path: Path) -> WorkflowTestBuilder:
        self._settings = replace(self._settings, database_path=path)
        if self._run_output_dir is None:
            self._run_output_dir = path.parent / "workflow-test-runs"
        return self

    def with_asset_storage_dir(self, path: Path) -> WorkflowTestBuilder:
        self._settings = replace(self._settings, asset_storage_dir=path)
        return self

    def with_workflow_dir(self, path: Path) -> WorkflowTestBuilder:
        self._settings = replace(self._settings, workflow_dir=path)
        return self

    def with_default_admin(
        self,
        *,
        username: str = "workflow-test-admin",
        password: str = "secret-123",
    ) -> WorkflowTestBuilder:
        self._username = username
        self._password = password
        return self

    def with_default_project(self, *, name: str = "Workflow Test Project") -> WorkflowTestBuilder:
        self._project_name = name
        self._project_id = None
        return self

    def with_project_id(self, project_id: str) -> WorkflowTestBuilder:
        self._project_id = project_id
        return self

    def with_run_output_dir(self, path: Path) -> WorkflowTestBuilder:
        self._run_output_dir = path
        return self

    async def build(self) -> WorkflowTestSession:
        await migrate(self._settings.database_path)
        users = SqliteUserService(self._settings.database_path)
        user = await _get_or_create_user(
            users,
            username=self._username,
            password=self._password,
        )
        project = await _get_or_create_project(
            users,
            user_id=user.user_id,
            project_id=self._project_id,
            project_name=self._project_name,
        )
        assets = SqliteAssetService(
            database_path=self._settings.database_path,
            storage_dir=self._settings.asset_storage_dir,
            user_service=users,
        )
        node_registry = build_node_registry(self._settings)
        runtime = SqliteRuntimeService(
            database_path=self._settings.database_path,
            user_service=users,
            node_registry=node_registry,
        )
        workflows = WorkflowCatalog(node_registry)
        if self._settings.workflow_dir.exists():
            workflows.load_directory(self._settings.workflow_dir)
        run_output_dir = self._run_output_dir or (
            self._settings.database_path.parent / "workflow-test-runs"
        )
        run_output_dir.mkdir(parents=True, exist_ok=True)
        return WorkflowTestSession(
            settings=self._settings,
            users=users,
            assets=assets,
            node_registry=node_registry,
            runtime=runtime,
            workflows=workflows,
            user=user,
            project=project,
            run_output_dir=run_output_dir,
        )


async def _get_or_create_user(
    users: SqliteUserService,
    *,
    username: str,
    password: str,
) -> UserRecord:
    try:
        return await users.create_user(username=username, password=password)
    except ConflictError:
        auth = await users.authenticate(username=username, password=password)
        return auth.user


async def _get_or_create_project(
    users: SqliteUserService,
    *,
    user_id: str,
    project_id: str | None,
    project_name: str,
) -> ProjectRecord:
    if project_id is not None:
        return await users.get_project(user_id=user_id, project_id=project_id)
    for project in await users.list_projects_for_user(user_id=user_id):
        if project.name == project_name:
            return project
    return await users.create_project(owner_user_id=user_id, name=project_name)
```

- [ ] **Step 4: 运行 builder 测试确认通过**

Run:

```powershell
python -m pytest tests/test_workflow_testing_builder.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/workflows/testing/__init__.py xiagent/workflows/testing/builder.py tests/test_workflow_testing_builder.py
git commit -m "feat: add workflow test session builder"
```

## Task 2: 图片产物识别与 HTML 预览

**Files:**
- Create: `xiagent/workflows/testing/artifacts.py`
- Test: `tests/test_workflow_testing_artifacts.py`

- [ ] **Step 1: 写 artifacts 失败测试**

Create `tests/test_workflow_testing_artifacts.py`:

```python
from __future__ import annotations

import base64
from pathlib import Path

from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord
from xiagent.workflows.testing.artifacts import (
    ImageArtifact,
    collect_image_artifacts,
    generate_html_preview,
    open_artifact_paths,
)


def _execution(output_snapshot: dict) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_execution_id="node_execution_1",
        task_id="task_1",
        node_id="render",
        node_ref="tool.render.v1",
        attempt=1,
        input_snapshot={},
        output_snapshot=output_snapshot,
        status="succeeded",
        error=None,
        metadata={},
        started_at="2026-05-20T00:00:00+00:00",
        finished_at="2026-05-20T00:00:01+00:00",
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:01+00:00",
    )


def _task() -> TaskRecord:
    return TaskRecord(
        task_id="task_1",
        workflow_template_id="workflow_template_1",
        workflow_id="image-demo",
        workflow_version="1.0.0",
        user_id="user_1",
        project_id="project_1",
        input_data={},
        status="succeeded",
        current_view={"status": "succeeded"},
        created_at="2026-05-20T00:00:00+00:00",
        started_at="2026-05-20T00:00:00+00:00",
        finished_at="2026-05-20T00:00:01+00:00",
        updated_at="2026-05-20T00:00:01+00:00",
    )


def test_collect_image_artifacts_detects_path_object_and_data_url(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    data_url = "data:image/png;base64," + base64.b64encode(b"data-url-png").decode("ascii")
    output_dir = tmp_path / "run"
    executions = [
        _execution(
            {
                "direct": str(image_path),
                "object": {
                    "type": "image",
                    "path": str(image_path),
                    "mime_type": "image/png",
                },
                "inline": data_url,
            }
        )
    ]

    artifacts = collect_image_artifacts(executions, output_dir=output_dir)

    assert [(item.field_path, item.mime_type) for item in artifacts] == [
        ("output.direct", "image/png"),
        ("output.object", "image/png"),
        ("output.inline", "image/png"),
    ]
    assert artifacts[0].path == image_path
    assert artifacts[1].path == image_path
    assert artifacts[2].path.read_bytes() == b"data-url-png"
    assert artifacts[2].path.parent == output_dir / "images"


def test_generate_html_preview_contains_node_json_and_image(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    execution = _execution({"image": str(image_path), "text": "ok"})
    artifact = ImageArtifact(
        node_id="render",
        node_ref="tool.render.v1",
        snapshot_kind="output",
        field_path="output.image",
        path=image_path,
        mime_type="image/png",
        source_type="path",
    )
    preview_path = tmp_path / "preview.html"

    generated = generate_html_preview(
        task=_task(),
        node_executions=[execution],
        events=[
            TaskEventRecord(
                event_id="event_1",
                task_id="task_1",
                event_type="task_succeeded",
                payload={},
                created_at="2026-05-20T00:00:01+00:00",
            )
        ],
        artifacts=[artifact],
        output_path=preview_path,
    )

    html = generated.read_text(encoding="utf-8")
    assert generated == preview_path
    assert "image-demo" in html
    assert "render" in html
    assert "task_succeeded" in html
    assert "sample.png" in html
    assert "<img" in html


def test_open_artifact_paths_uses_injected_opener(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    opened: list[Path] = []

    open_artifact_paths([image_path], opener=opened.append)

    assert opened == [image_path]
```

- [ ] **Step 2: 运行 artifacts 测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_testing_artifacts.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `xiagent.workflows.testing.artifacts`.

- [ ] **Step 3: 实现 artifacts**

Create `xiagent/workflows/testing/artifacts.py`:

```python
from __future__ import annotations

import base64
import html
import json
import os
import re
import webbrowser
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord

_IMAGE_SUFFIX_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_DATA_URL_PATTERN = re.compile(r"^data:(image/[A-Za-z0-9.+-]+);base64,(.+)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ImageArtifact:
    node_id: str
    node_ref: str
    snapshot_kind: str
    field_path: str
    path: Path
    mime_type: str
    source_type: str


def collect_image_artifacts(
    node_executions: Iterable[NodeExecutionRecord],
    *,
    output_dir: Path,
) -> list[ImageArtifact]:
    artifacts: list[ImageArtifact] = []
    image_dir = output_dir / "images"
    for execution in node_executions:
        artifacts.extend(
            _collect_from_value(
                execution,
                snapshot_kind="input",
                prefix="input",
                value=execution.input_snapshot,
                image_dir=image_dir,
            )
        )
        artifacts.extend(
            _collect_from_value(
                execution,
                snapshot_kind="output",
                prefix="output",
                value=execution.output_snapshot,
                image_dir=image_dir,
            )
        )
    return artifacts


def generate_html_preview(
    *,
    task: TaskRecord,
    node_executions: list[NodeExecutionRecord],
    events: list[TaskEventRecord],
    artifacts: list[ImageArtifact],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_items = "\n".join(_artifact_html(output_path.parent, item) for item in artifacts)
    execution_items = "\n".join(_execution_html(item) for item in node_executions)
    event_items = "\n".join(_event_html(item) for item in events)
    task_json = html.escape(json.dumps(asdict(task), ensure_ascii=False, indent=2, default=str))
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>XiAgent Workflow Preview - {html.escape(task.task_id)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2933; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin: 24px 0; }}
    pre {{ background: #f5f7fa; padding: 12px; overflow: auto; border-radius: 6px; }}
    .artifact {{ margin: 12px 0; }}
    img {{ max-width: 420px; max-height: 320px; display: block; border: 1px solid #d8dee4; }}
  </style>
</head>
<body>
  <h1>{html.escape(task.workflow_id)} {html.escape(task.workflow_version)}</h1>
  <section>
    <h2>Task</h2>
    <pre>{task_json}</pre>
  </section>
  <section>
    <h2>Events</h2>
    {event_items}
  </section>
  <section>
    <h2>Node Executions</h2>
    {execution_items}
  </section>
  <section>
    <h2>Images</h2>
    {artifact_items or "<p>No image artifacts.</p>"}
  </section>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")
    return output_path


def open_artifact_paths(
    paths: Iterable[Path],
    *,
    opener: Callable[[Path], object] | None = None,
) -> None:
    resolved_opener = opener or _default_open_path
    for path in paths:
        resolved_opener(path)


def open_html_preview(path: Path) -> None:
    webbrowser.open(path.resolve().as_uri())


def _collect_from_value(
    execution: NodeExecutionRecord,
    *,
    snapshot_kind: str,
    prefix: str,
    value: Any,
    image_dir: Path,
) -> list[ImageArtifact]:
    artifacts: list[ImageArtifact] = []
    if isinstance(value, dict):
        image_object = _image_object(value)
        if image_object is not None:
            path, mime_type = image_object
            artifacts.append(
                _artifact(
                    execution,
                    snapshot_kind=snapshot_kind,
                    field_path=prefix,
                    path=path,
                    mime_type=mime_type,
                    source_type="object",
                )
            )
            return artifacts
        for key, item in value.items():
            artifacts.extend(
                _collect_from_value(
                    execution,
                    snapshot_kind=snapshot_kind,
                    prefix=f"{prefix}.{key}",
                    value=item,
                    image_dir=image_dir,
                )
            )
        return artifacts
    if isinstance(value, list):
        for index, item in enumerate(value):
            artifacts.extend(
                _collect_from_value(
                    execution,
                    snapshot_kind=snapshot_kind,
                    prefix=f"{prefix}.{index}",
                    value=item,
                    image_dir=image_dir,
                )
            )
        return artifacts
    if isinstance(value, str):
        data_url = _write_data_url(value, image_dir=image_dir, field_path=prefix)
        if data_url is not None:
            path, mime_type = data_url
            artifacts.append(
                _artifact(
                    execution,
                    snapshot_kind=snapshot_kind,
                    field_path=prefix,
                    path=path,
                    mime_type=mime_type,
                    source_type="data_url",
                )
            )
            return artifacts
        path_mime = _path_mime(value)
        if path_mime is not None:
            path, mime_type = path_mime
            artifacts.append(
                _artifact(
                    execution,
                    snapshot_kind=snapshot_kind,
                    field_path=prefix,
                    path=path,
                    mime_type=mime_type,
                    source_type="path",
                )
            )
    return artifacts


def _image_object(value: dict[str, Any]) -> tuple[Path, str] | None:
    if value.get("type") != "image":
        return None
    path_value = value.get("path")
    if not isinstance(path_value, str):
        return None
    mime_type = value.get("mime_type")
    if not isinstance(mime_type, str):
        path_mime = _path_mime(path_value)
        mime_type = path_mime[1] if path_mime is not None else "image/*"
    return Path(path_value), mime_type


def _path_mime(value: str) -> tuple[Path, str] | None:
    path = Path(value)
    mime_type = _IMAGE_SUFFIX_MIME.get(path.suffix.lower())
    if mime_type is None:
        return None
    return path, mime_type


def _write_data_url(value: str, *, image_dir: Path, field_path: str) -> tuple[Path, str] | None:
    match = _DATA_URL_PATTERN.match(value)
    if match is None:
        return None
    mime_type = match.group(1)
    extension = "." + mime_type.split("/", 1)[1].replace("jpeg", "jpg")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", field_path)
    path = image_dir / f"{safe_name}{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(match.group(2)))
    return path, mime_type


def _artifact(
    execution: NodeExecutionRecord,
    *,
    snapshot_kind: str,
    field_path: str,
    path: Path,
    mime_type: str,
    source_type: str,
) -> ImageArtifact:
    return ImageArtifact(
        node_id=execution.node_id,
        node_ref=execution.node_ref,
        snapshot_kind=snapshot_kind,
        field_path=field_path,
        path=path,
        mime_type=mime_type,
        source_type=source_type,
    )


def _artifact_html(base_dir: Path, artifact: ImageArtifact) -> str:
    image_src = _html_path(base_dir, artifact.path)
    title = html.escape(f"{artifact.node_id} {artifact.field_path}")
    path_text = html.escape(str(artifact.path))
    return f"""<div class="artifact">
  <h3>{title}</h3>
  <img src="{image_src}" alt="{title}">
  <pre>{path_text}</pre>
</div>"""


def _execution_html(execution: NodeExecutionRecord) -> str:
    payload = html.escape(json.dumps(asdict(execution), ensure_ascii=False, indent=2, default=str))
    return f"<h3>{html.escape(execution.node_id)}</h3><pre>{payload}</pre>"


def _event_html(event: TaskEventRecord) -> str:
    payload = html.escape(json.dumps(asdict(event), ensure_ascii=False, indent=2, default=str))
    return f"<pre>{payload}</pre>"


def _html_path(base_dir: Path, path: Path) -> str:
    try:
        return html.escape(path.resolve().relative_to(base_dir.resolve()).as_posix())
    except ValueError:
        return html.escape(path.resolve().as_uri())


def _default_open_path(path: Path) -> object:
    if os.name == "nt":
        return os.startfile(path)  # type: ignore[attr-defined]
    return webbrowser.open(path.resolve().as_uri())
```

- [ ] **Step 4: 运行 artifacts 测试确认通过**

Run:

```powershell
python -m pytest tests/test_workflow_testing_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/workflows/testing/artifacts.py tests/test_workflow_testing_artifacts.py
git commit -m "feat: add workflow test image artifacts"
```

## Task 3: Console 输入输出

**Files:**
- Create: `xiagent/workflows/testing/console.py`
- Test: `tests/test_workflow_testing_runner.py`

- [ ] **Step 1: 写 console 失败测试**

Create the first part of `tests/test_workflow_testing_runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from xiagent.workflows.testing.console import ConsoleIO, parse_input_data


def test_parse_input_data_prefers_inline_json(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text('{"topic":"from-file"}', encoding="utf-8")

    parsed = parse_input_data(
        inline_json='{"topic":"from-inline"}',
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-inline"}


def test_parse_input_data_reads_json_file(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"topic": "from-file"}), encoding="utf-8")

    parsed = parse_input_data(
        inline_json=None,
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-file"}


def test_parse_input_data_prompts_required_schema_fields() -> None:
    prompts: list[str] = []
    answers = iter(["hello", "7", "yes", '{"nested": true}'])
    console = ConsoleIO(input_func=lambda prompt: prompts.append(prompt) or next(answers))

    parsed = parse_input_data(
        inline_json=None,
        input_file=None,
        interactive=False,
        input_schema={
            "type": "object",
            "required": ["topic", "count", "enabled", "options"],
            "properties": {
                "topic": {"type": "string"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "options": {"type": "object"},
            },
        },
        console=console,
    )

    assert parsed == {
        "topic": "hello",
        "count": 7,
        "enabled": True,
        "options": {"nested": True},
    }
    assert prompts == ["topic: ", "count: ", "enabled: ", "options (JSON): "]
```

- [ ] **Step 2: 运行 console 测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_testing_runner.py::test_parse_input_data_prefers_inline_json tests/test_workflow_testing_runner.py::test_parse_input_data_reads_json_file tests/test_workflow_testing_runner.py::test_parse_input_data_prompts_required_schema_fields -q
```

Expected: FAIL with `ModuleNotFoundError` for `xiagent.workflows.testing.console`.

- [ ] **Step 3: 实现 console**

Create `xiagent/workflows/testing/console.py`:

```python
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from xiagent.core.schemas import validate_json_value
from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord


class ConsoleIO:
    def __init__(
        self,
        *,
        input_func: Callable[[str], str] | None = None,
        output_func: Callable[[str], object] | None = None,
    ) -> None:
        self._input = input_func or input
        self._output = output_func or print

    def write(self, message: str = "") -> None:
        self._output(message)

    def ask(self, prompt: str) -> str:
        return self._input(prompt)

    def ask_json(self, prompt: str) -> dict[str, Any]:
        raw_value = self.ask(prompt)
        parsed = json.loads(raw_value)
        if not isinstance(parsed, dict):
            raise ValueError("JSON input must be an object")
        return parsed

    def show_event(self, index: int, event: TaskEventRecord) -> None:
        self.write(f"[{index:02d}] {event.event_type}")
        if event.payload:
            self.write(_json(event.payload))

    def show_node_execution(self, execution: NodeExecutionRecord) -> None:
        self.write(f"     node={execution.node_id} ref={execution.node_ref} status={execution.status}")
        self.write(f"     input: {_json(execution.input_snapshot)}")
        self.write(f"     output: {_json(execution.output_snapshot)}")
        if execution.error:
            self.write(f"     error: {_json(execution.error)}")

    def prompt_resume_output(
        self,
        *,
        execution: NodeExecutionRecord,
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.write(f"[等待输入] 节点 {execution.node_id} {execution.node_ref}")
        requested_inputs = execution.metadata.get("requested_inputs")
        if requested_inputs is not None:
            self.write("requested_inputs:")
            self.write(_json(requested_inputs))
        self.write("output_schema:")
        self.write(_json(output_schema))
        return self.ask_json("请输入恢复输出 JSON: ")


def parse_input_data(
    *,
    inline_json: str | None,
    input_file: Path | None,
    interactive: bool,
    input_schema: dict[str, Any],
    console: ConsoleIO,
) -> dict[str, Any]:
    if inline_json is not None:
        return _validated_object(json.loads(inline_json), input_schema)
    if input_file is not None:
        return _validated_object(json.loads(input_file.read_text(encoding="utf-8")), input_schema)
    return _validated_object(_prompt_schema(input_schema, console=console), input_schema)


def print_error(exc: Exception, *, debug: bool, console: ConsoleIO) -> None:
    from traceback import format_exc

    from xiagent.core.errors import XiAgentError

    if isinstance(exc, XiAgentError):
        console.write(f"[错误] {exc.code}")
        console.write(exc.message)
        if exc.details:
            console.write(f"details: {_json(exc.details)}")
        return
    console.write(f"[错误] {exc.__class__.__name__}")
    console.write(str(exc))
    if debug:
        console.write(format_exc())


def _validated_object(value: Any, schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Workflow input must be a JSON object")
    validate_json_value(schema, value)
    return value


def _prompt_schema(schema: dict[str, Any], *, console: ConsoleIO) -> dict[str, Any]:
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    if not isinstance(required, list) or not isinstance(properties, dict):
        return console.ask_json("workflow input JSON: ")
    result: dict[str, Any] = {}
    for field in required:
        if not isinstance(field, str):
            continue
        field_schema = properties.get(field, {})
        result[field] = _prompt_field(field, field_schema, console=console)
    return result


def _prompt_field(field: str, schema: Any, *, console: ConsoleIO) -> Any:
    field_type = schema.get("type") if isinstance(schema, dict) else None
    if field_type == "integer":
        return int(console.ask(f"{field}: "))
    if field_type == "number":
        return float(console.ask(f"{field}: "))
    if field_type == "boolean":
        raw_value = console.ask(f"{field}: ").strip().lower()
        return raw_value in {"true", "yes", "y", "1"}
    if field_type in {"object", "array"}:
        return json.loads(console.ask(f"{field} (JSON): "))
    return console.ask(f"{field}: ")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
```

- [ ] **Step 4: 运行 console 测试确认通过**

Run:

```powershell
python -m pytest tests/test_workflow_testing_runner.py::test_parse_input_data_prefers_inline_json tests/test_workflow_testing_runner.py::test_parse_input_data_reads_json_file tests/test_workflow_testing_runner.py::test_parse_input_data_prompts_required_schema_fields -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/workflows/testing/console.py tests/test_workflow_testing_runner.py
git commit -m "feat: add workflow test console input"
```

## Task 4: 工作流测试 runner

**Files:**
- Create: `xiagent/workflows/testing/runner.py`
- Modify: `xiagent/workflows/testing/__init__.py`
- Test: `tests/test_workflow_testing_runner.py`

- [ ] **Step 1: 追加 runner 失败测试**

Append to `tests/test_workflow_testing_runner.py`:

```python
from xiagent.workflows.testing import WorkflowTestBuilder
from xiagent.workflows.testing.runner import WorkflowTestRunner


def _echo_contract() -> dict:
    return {
        "workflow": {
            "id": "runner-echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Runner Echo",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
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


def _approval_contract() -> dict:
    return {
        "workflow": {
            "id": "runner-approval",
            "version": "1.0.0",
            "scope": "global",
            "name": "Runner Approval",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
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
            {
                "from": "review",
                "to": "echo",
                "when": {"path": "$nodes.review.output.decision", "equals": "approve"},
            },
            {"from": "echo", "to": "END"},
        ],
    }


async def test_runner_executes_echo_contract_and_collects_events(tmp_path: Path) -> None:
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_contract(_echo_contract(), input_data={"topic": "hello"})

    assert result.task.status == "succeeded"
    assert [event.event_type for event in result.events] == [
        "task_created",
        "task_started",
        "node_started",
        "node_succeeded",
        "task_succeeded",
    ]
    assert result.node_executions[0].output_snapshot == {"echo": {"topic": "hello"}}
    assert result.run_dir == tmp_path / "runs" / result.task.task_id


async def test_runner_resumes_waiting_task_from_console(tmp_path: Path) -> None:
    answers = iter(['{"decision":"approve"}'])
    output_lines: list[str] = []
    console = ConsoleIO(
        input_func=lambda prompt: next(answers),
        output_func=output_lines.append,
    )
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(tmp_path / "workflows")
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=console)

    result = await runner.run_contract(_approval_contract(), input_data={"topic": "hello"})

    assert result.task.status == "succeeded"
    assert [item.node_id for item in result.node_executions] == ["review", "echo"]
    assert any("[等待输入] 节点 review" in line for line in output_lines)


async def test_runner_loads_contract_from_workflow_file(tmp_path: Path) -> None:
    workflow_file = tmp_path / "echo.workflow.yaml"
    workflow_file.write_text(
        """
workflow:
  id: file-echo
  version: 1.0.0
  scope: global
  name: File Echo
  input_schema:
    type: object
    required: ["topic"]
    properties:
      topic:
        type: string
nodes:
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: "$workflow.input.topic"
    outputs:
      type: object
edges:
  - from: START
    to: echo
  - from: echo
    to: END
""".lstrip(),
        encoding="utf-8",
    )
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    session = await (
        WorkflowTestBuilder()
        .with_database_path(tmp_path / "workflow-test.sqlite3")
        .with_asset_storage_dir(tmp_path / "assets")
        .with_workflow_dir(workflow_dir)
        .with_run_output_dir(tmp_path / "runs")
        .build()
    )
    runner = WorkflowTestRunner(session=session, console=ConsoleIO())

    result = await runner.run_workflow_file(workflow_file, input_data={"topic": "file"})

    assert result.task.workflow_id == "file-echo"
    assert result.task.status == "succeeded"
```

- [ ] **Step 2: 运行 runner 测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_testing_runner.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `xiagent.workflows.testing.runner`.

- [ ] **Step 3: 实现 runner**

Create `xiagent/workflows/testing/runner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xiagent.core.errors import ValidationError
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


@dataclass(frozen=True, slots=True)
class WorkflowTestRunResult:
    task: TaskRecord
    node_executions: list[NodeExecutionRecord]
    events: list[TaskEventRecord]
    artifacts: list[ImageArtifact]
    run_dir: Path
    preview_path: Path | None = None


class WorkflowTestRunner:
    def __init__(self, *, session: WorkflowTestSession, console: ConsoleIO) -> None:
        self._session = session
        self._console = console

    async def run_workflow_file(
        self,
        workflow_path: Path,
        *,
        input_data: dict[str, Any],
        open_images: bool = False,
        preview: str | None = None,
        open_preview: bool = False,
    ) -> WorkflowTestRunResult:
        contract = load_workflow_file(workflow_path)
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
        preview: str | None = None,
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
        preview: str | None = None,
        open_preview: bool = False,
    ) -> WorkflowTestRunResult:
        workflow = contract["workflow"]
        self._console.write(f"[01] 加载工作流 {workflow['id']} {workflow['version']}")
        task = await self._session.runtime.create_task_from_contract(
            user_id=self._session.user.user_id,
            project_id=self._session.project.project_id,
            contract=contract,
            input_data=input_data,
        )
        task = await self._resume_until_finished(task=task, contract=contract)
        result = await self._build_result(
            task=task,
            open_images=open_images,
            preview=preview,
            open_preview=open_preview,
        )
        self._show_result(result)
        return result

    async def _resume_until_finished(
        self,
        *,
        task: TaskRecord,
        contract: dict[str, Any],
    ) -> TaskRecord:
        current_task = task
        while current_task.status == "waiting":
            executions = await self._session.runtime.list_node_executions(
                user_id=self._session.user.user_id,
                project_id=self._session.project.project_id,
                task_id=current_task.task_id,
            )
            waiting_execution = _latest_waiting_execution(executions)
            node_def = _node_by_id(contract, waiting_execution.node_id)
            output = self._console.prompt_resume_output(
                execution=waiting_execution,
                output_schema=node_def["outputs"],
            )
            validate_json_value(node_def["outputs"], output)
            current_task = await self._session.runtime.resume_task(
                user_id=self._session.user.user_id,
                project_id=self._session.project.project_id,
                task_id=current_task.task_id,
                node_id=waiting_execution.node_id,
                output=output,
            )
        return current_task

    async def _build_result(
        self,
        *,
        task: TaskRecord,
        open_images: bool,
        preview: str | None,
        open_preview: bool,
    ) -> WorkflowTestRunResult:
        node_executions = await self._session.runtime.list_node_executions(
            user_id=self._session.user.user_id,
            project_id=self._session.project.project_id,
            task_id=task.task_id,
        )
        events = await self._session.runtime.list_events(
            user_id=self._session.user.user_id,
            project_id=self._session.project.project_id,
            task_id=task.task_id,
        )
        run_dir = self._session.run_output_dir / task.task_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts = collect_image_artifacts(node_executions, output_dir=run_dir)
        if open_images:
            open_artifact_paths([item.path for item in artifacts])
        preview_path = None
        if preview == "html":
            preview_path = generate_html_preview(
                task=task,
                node_executions=node_executions,
                events=events,
                artifacts=artifacts,
                output_path=run_dir / "preview.html",
            )
            if open_preview:
                open_html_preview(preview_path)
        return WorkflowTestRunResult(
            task=task,
            node_executions=node_executions,
            events=events,
            artifacts=artifacts,
            run_dir=run_dir,
            preview_path=preview_path,
        )

    def _show_result(self, result: WorkflowTestRunResult) -> None:
        for index, event in enumerate(result.events, start=1):
            self._console.show_event(index, event)
        for execution in result.node_executions:
            self._console.show_node_execution(execution)
        for artifact in result.artifacts:
            self._console.write(
                f"[图片输出] node={artifact.node_id} field={artifact.field_path}"
            )
            self._console.write(f"path: {artifact.path}")
            self._console.write(f"mime: {artifact.mime_type}")
        if result.preview_path is not None:
            self._console.write(f"preview: {result.preview_path}")


def _latest_waiting_execution(executions: list[NodeExecutionRecord]) -> NodeExecutionRecord:
    for execution in reversed(executions):
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
```

Modify `xiagent/workflows/testing/__init__.py`:

```python
from __future__ import annotations

from xiagent.workflows.testing.builder import WorkflowTestBuilder, WorkflowTestSession
from xiagent.workflows.testing.runner import WorkflowTestRunner, WorkflowTestRunResult

__all__ = [
    "WorkflowTestBuilder",
    "WorkflowTestRunner",
    "WorkflowTestRunResult",
    "WorkflowTestSession",
]
```

- [ ] **Step 4: 运行 runner 测试确认通过**

Run:

```powershell
python -m pytest tests/test_workflow_testing_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/workflows/testing/__init__.py xiagent/workflows/testing/runner.py tests/test_workflow_testing_runner.py
git commit -m "feat: add workflow test runner"
```

## Task 5: CLI 参数解析与入口

**Files:**
- Create: `xiagent/workflows/testing_cli.py`
- Test: `tests/test_workflow_testing_cli.py`

- [ ] **Step 1: 写 CLI 失败测试**

Create `tests/test_workflow_testing_cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from xiagent.workflows.testing_cli import build_parser, run_from_args


def test_build_parser_accepts_workflow_path_and_input() -> None:
    args = build_parser().parse_args(
        ["workflows/global/deepseek_echo.workflow.yaml", "--input", '{"prompt":"hello"}']
    )

    assert args.workflow_path == Path("workflows/global/deepseek_echo.workflow.yaml")
    assert args.input == '{"prompt":"hello"}'
    assert args.workflow_id is None


def test_build_parser_accepts_workflow_id() -> None:
    args = build_parser().parse_args(["--workflow-id", "deepseek_echo", "--input", '{"prompt":"hello"}'])

    assert args.workflow_path is None
    assert args.workflow_id == "deepseek_echo"


def test_parser_rejects_missing_workflow_selector() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--input", '{"prompt":"hello"}'])


def test_parser_rejects_both_workflow_selectors() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["workflow.yaml", "--workflow-id", "deepseek_echo", "--input", '{"prompt":"hello"}']
        )


async def test_run_from_args_executes_workflow_file(tmp_path: Path) -> None:
    workflow_file = tmp_path / "echo.workflow.yaml"
    workflow_file.write_text(
        """
workflow:
  id: cli-echo
  version: 1.0.0
  scope: global
  name: CLI Echo
  input_schema:
    type: object
    required: ["topic"]
    properties:
      topic:
        type: string
nodes:
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: "$workflow.input.topic"
    outputs:
      type: object
edges:
  - from: START
    to: echo
  - from: echo
    to: END
""".lstrip(),
        encoding="utf-8",
    )
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    args = argparse.Namespace(
        workflow_path=workflow_file,
        workflow_id=None,
        input='{"topic":"cli"}',
        input_file=None,
        interactive=False,
        database_path=tmp_path / "workflow-test.sqlite3",
        asset_storage_dir=tmp_path / "assets",
        workflow_dir=workflow_dir,
        project_id=None,
        project_name="Workflow Test Project",
        username="workflow-test-admin",
        password="secret-123",
        show_json=False,
        open_images=False,
        preview=None,
        open_preview=False,
        debug=False,
    )

    exit_code = await run_from_args(args)

    assert exit_code == 0
```

- [ ] **Step 2: 运行 CLI 测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_testing_cli.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `xiagent.workflows.testing_cli`.

- [ ] **Step 3: 实现 CLI**

Create `xiagent/workflows/testing_cli.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing import WorkflowTestBuilder, WorkflowTestRunner
from xiagent.workflows.testing.console import ConsoleIO, parse_input_data, print_error


class WorkflowTestingArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args: list[str] | None = None, namespace: argparse.Namespace | None = None) -> argparse.Namespace:
        parsed = super().parse_args(args=args, namespace=namespace)
        if parsed.workflow_path is None and parsed.workflow_id is None:
            self.error("workflow_path or --workflow-id is required")
        if parsed.workflow_path is not None and parsed.workflow_id is not None:
            self.error("workflow_path and --workflow-id are mutually exclusive")
        return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = WorkflowTestingArgumentParser(description="Run a XiAgent workflow without the UI.")
    parser.add_argument("workflow_path", nargs="?", type=Path)
    parser.add_argument("--workflow-id")
    parser.add_argument("--input")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--database-path", type=Path, default=Path(".data/workflow-test.sqlite3"))
    parser.add_argument("--asset-storage-dir", type=Path, default=Path(".data/workflow-test-assets"))
    parser.add_argument("--workflow-dir", type=Path, default=Path("workflows"))
    parser.add_argument("--project-id")
    parser.add_argument("--project-name", default="Workflow Test Project")
    parser.add_argument("--username", default="workflow-test-admin")
    parser.add_argument("--password", default="secret-123")
    parser.add_argument("--show-json", action="store_true")
    parser.add_argument("--open-images", action="store_true")
    parser.add_argument("--preview", choices=["html"])
    parser.add_argument("--open-preview", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


async def run_from_args(args: argparse.Namespace) -> int:
    console = ConsoleIO()
    try:
        builder = (
            WorkflowTestBuilder()
            .with_database_path(args.database_path)
            .with_asset_storage_dir(args.asset_storage_dir)
            .with_workflow_dir(args.workflow_dir)
            .with_default_admin(username=args.username, password=args.password)
            .with_default_project(name=args.project_name)
        )
        if args.project_id is not None:
            builder.with_project_id(args.project_id)
        session = await builder.build()
        contract = (
            load_workflow_file(args.workflow_path)
            if args.workflow_path is not None
            else session.workflows.get(args.workflow_id)
        )
        input_data = parse_input_data(
            inline_json=args.input,
            input_file=args.input_file,
            interactive=args.interactive,
            input_schema=contract["workflow"]["input_schema"],
            console=console,
        )
        runner = WorkflowTestRunner(session=session, console=console)
        result = await runner.run_contract(
            contract,
            input_data=input_data,
            open_images=args.open_images,
            preview=args.preview,
            open_preview=args.open_preview,
        )
        if args.show_json:
            console.write(
                json.dumps(
                    {
                        "task": asdict(result.task),
                        "events": [asdict(item) for item in result.events],
                        "node_executions": [asdict(item) for item in result.node_executions],
                        "artifacts": [
                            asdict(item) | {"path": str(item.path)}
                            for item in result.artifacts
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        return 0 if result.task.status == "succeeded" else 1
    except Exception as exc:
        print_error(exc, debug=args.debug, console=console)
        return 1


def main() -> None:
    raise SystemExit(asyncio.run(run_from_args(build_parser().parse_args())))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行 CLI 测试确认通过**

Run:

```powershell
python -m pytest tests/test_workflow_testing_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add xiagent/workflows/testing_cli.py tests/test_workflow_testing_cli.py
git commit -m "feat: add workflow testing cli"
```

## Task 6: README 说明与集成验证

**Files:**
- Modify: `README.md`
- Test: all workflow testing tests

- [ ] **Step 1: 更新 README**

Append to `README.md`:

```markdown
## 无 UI 工作流测试

可以通过 CLI 直接执行工作流文件：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input '{"prompt":"你好"}'
```

也可以从工作流目录按模板 ID 执行：

```powershell
python -m xiagent.workflows.testing_cli --workflow-id deepseek_echo --input '{"prompt":"你好"}'
```

默认使用测试数据库 `.data/workflow-test.sqlite3`、测试用户 `workflow-test-admin` 和测试项目 `Workflow Test Project`。遇到人工等待节点时，CLI 会提示输入恢复输出 JSON。

图片输出默认打印本地路径。需要打开图片或生成 HTML 报告时：

```powershell
python -m xiagent.workflows.testing_cli workflows/demo.workflow.yaml --input-file .data/input.json --open-images --preview html --open-preview
```
```

- [ ] **Step 2: 运行定向测试**

Run:

```powershell
python -m pytest tests/test_workflow_testing_builder.py tests/test_workflow_testing_artifacts.py tests/test_workflow_testing_runner.py tests/test_workflow_testing_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: 运行全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: 手动 CLI 验证 echo 或 DeepSeek 工作流**

Run:

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input '{"prompt":"用一句话说明 XiAgent 是什么"}'
```

Expected with configured DeepSeek key: CLI exits `0`, task status is `succeeded`, node output contains `text`、`model` and `usage`.

Expected without DeepSeek key: CLI exits `1`, task is persisted as `failed`, output includes a structured XiAgent error from the model provider path.

- [ ] **Step 5: Commit**

```powershell
git add README.md
git commit -m "docs: add workflow testing cli usage"
```

## Self-Review

### Spec coverage

- 测试专用构建器：Task 1 covers `WorkflowTestBuilder` and `WorkflowTestSession`.
- CLI 执行工作流文件或模板 ID：Task 5 covers parser and `run_from_args`.
- 默认测试用户和项目：Task 1 covers create/reuse behavior.
- 输入来源：Task 3 covers inline JSON, file JSON and schema prompting.
- 执行过程展示：Task 3 and Task 4 cover events, node snapshots and final result output.
- waiting 恢复：Task 4 covers console-provided resume output through `RuntimeService.resume_task`.
- 图片路径、打开、HTML 预览：Task 2 covers artifact detection, opener injection and preview generation.
- 不新增第二套运行时：Task 4 calls `RuntimeService.create_task_from_contract` and `resume_task`.
- README 使用说明：Task 6 covers documentation.

### Placeholder scan

The plan avoids incomplete markers and gives exact files, commands, expected outcomes, test code and implementation code for each task.

### Type consistency

- `WorkflowTestSession` fields match services already present in the repository.
- `WorkflowTestRunner.run_contract`, `run_workflow_file` and `run_workflow_id` return `WorkflowTestRunResult`.
- `ConsoleIO.prompt_resume_output` returns `dict[str, Any]`, matching `RuntimeService.resume_task(output=...)`.
- `ImageArtifact` fields are used consistently by `collect_image_artifacts`, `generate_html_preview` and runner display.
