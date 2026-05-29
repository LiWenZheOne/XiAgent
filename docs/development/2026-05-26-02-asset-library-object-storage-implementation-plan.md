# 资产库与对象存储实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现第一版图片资产上传管理、树形目录与标签检索、对象存储发布 URL，以及工作流创建页从资产库选择图片运行图生图工作流的闭环。

**Architecture:** 后端新增对象存储路由器抽象，七牛云只作为基础设施适配器出现。资产服务继续保存本地资产、目录、标签和索引，图片文件上传后发布到对象存储并把 `metadata.public_url` 交给前端和工作流。前端采用 `React + Vite + TypeScript`，资产库和工作流输入表单共用资产选择器。

**Tech Stack:** Python 3.11、FastAPI、SQLite、pytest、python-multipart、qiniu SDK、React、Vite、TypeScript、Vitest、Codex 内部浏览器验收。

---

## 文件结构

后端基础设施：

```text
xiagent/infrastructure/object_storage/__init__.py
xiagent/infrastructure/object_storage/models.py
xiagent/infrastructure/object_storage/base.py
xiagent/infrastructure/object_storage/config.py
xiagent/infrastructure/object_storage/router.py
xiagent/infrastructure/object_storage/qiniu.py
xiagent/infrastructure/object_storage.example.toml
xiagent/infrastructure/object_storage.local.toml  # 本地未跟踪
```

后端资产模块：

```text
xiagent/core/services.py
xiagent/assets/models.py
xiagent/assets/service.py
xiagent/api/dependencies.py
xiagent/api/routers/assets.py
xiagent/infrastructure/migrations.py
tests/test_object_storage.py
tests/test_assets_service.py
tests/test_api_smoke.py
```

前端：

```text
ui/V1/package.json
ui/V1/index.html
ui/V1/tsconfig.json
ui/V1/vite.config.ts
ui/V1/src/main.tsx
ui/V1/src/app/App.tsx
ui/V1/src/api/client.ts
ui/V1/src/api/assets.ts
ui/V1/src/api/tasks.ts
ui/V1/src/api/workflows.ts
ui/V1/src/api/types.ts
ui/V1/src/assets/AssetLibraryPage.tsx
ui/V1/src/assets/AssetPicker.tsx
ui/V1/src/assets/AssetUploadDialog.tsx
ui/V1/src/task/CreateTaskPage.tsx
ui/V1/src/task/WorkflowInputForm.tsx
ui/V1/src/styles/app.css
ui/V1/src/tests/*.test.tsx
```

工作流：

```text
workflows/global/runninghub_image_to_image_test.workflow.yaml
```

## Task 1: 对象存储抽象与配置

**Files:**
- Create: `xiagent/infrastructure/object_storage/models.py`
- Create: `xiagent/infrastructure/object_storage/base.py`
- Create: `xiagent/infrastructure/object_storage/config.py`
- Create: `xiagent/infrastructure/object_storage/router.py`
- Create: `xiagent/infrastructure/object_storage/qiniu.py`
- Create: `xiagent/infrastructure/object_storage/__init__.py`
- Create: `xiagent/infrastructure/object_storage.example.toml`
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Test: `tests/test_object_storage.py`

- [ ] **Step 1: 写对象存储路由器测试**

在 `tests/test_object_storage.py` 增加：

```python
from __future__ import annotations

from pathlib import Path

import pytest

from xiagent.infrastructure.object_storage.config import load_object_storage_config
from xiagent.infrastructure.object_storage.router import ObjectStorageRouter


def test_load_object_storage_config_prefers_local_file(tmp_path: Path) -> None:
    config_path = tmp_path / "object_storage.local.toml"
    config_path.write_text(
        """
[object_storage]
provider = "qiniu"

[object_storage.qiniu]
access_key = "ak"
secret_key = "sk"
bucket = "bucket"
region = "z0"
public_base_url = "https://cdn.example.com"
key_prefix = "xiagent/assets"
""".lstrip(),
        encoding="utf-8",
    )

    config = load_object_storage_config(config_path)

    assert config.provider == "qiniu"
    assert config.qiniu.access_key == "ak"
    assert config.qiniu.public_base_url == "https://cdn.example.com"


def test_object_storage_router_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported object storage provider"):
        ObjectStorageRouter(provider="missing", services={})
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_object_storage.py -q
```

Expected: FAIL，原因是 `xiagent.infrastructure.object_storage` 模块尚不存在。

- [ ] **Step 3: 实现模型和 ABC**

创建 `xiagent/infrastructure/object_storage/models.py`：

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    provider: str
    bucket: str
    key: str
    public_url: str
    content_type: str | None
    size_bytes: int
    etag: str | None = None
```

创建 `xiagent/infrastructure/object_storage/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from xiagent.infrastructure.object_storage.models import StoredObject


class ObjectStorageService(ABC):
    @abstractmethod
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    async def delete_object(self, *, key: str) -> None:
        raise NotImplementedError
```

- [ ] **Step 4: 实现配置加载**

创建 `xiagent/infrastructure/object_storage/config.py`：

```python
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OBJECT_STORAGE_CONFIG_PATH = Path(__file__).with_name("object_storage.local.toml")


@dataclass(frozen=True)
class QiniuObjectStorageConfig:
    access_key: str | None
    secret_key: str | None
    bucket: str | None
    region: str | None
    public_base_url: str | None
    key_prefix: str


@dataclass(frozen=True)
class ObjectStorageConfig:
    provider: str
    qiniu: QiniuObjectStorageConfig


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    return value if isinstance(value, dict) else {}


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def load_object_storage_config(
    path: Path = DEFAULT_OBJECT_STORAGE_CONFIG_PATH,
) -> ObjectStorageConfig:
    raw: dict[str, Any] = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    object_storage = _section(raw, "object_storage")
    qiniu = _section(object_storage, "qiniu")

    provider = (
        os.getenv("XIAGENT_OBJECT_STORAGE_PROVIDER")
        or _optional_text(object_storage.get("provider"))
        or "local_none"
    )
    key_prefix = os.getenv("QINIU_KEY_PREFIX") or _optional_text(qiniu.get("key_prefix")) or "xiagent/assets"

    return ObjectStorageConfig(
        provider=provider,
        qiniu=QiniuObjectStorageConfig(
            access_key=os.getenv("QINIU_ACCESS_KEY") or _optional_text(qiniu.get("access_key")),
            secret_key=os.getenv("QINIU_SECRET_KEY") or _optional_text(qiniu.get("secret_key")),
            bucket=os.getenv("QINIU_BUCKET") or _optional_text(qiniu.get("bucket")),
            region=os.getenv("QINIU_REGION") or _optional_text(qiniu.get("region")),
            public_base_url=os.getenv("QINIU_PUBLIC_BASE_URL")
            or _optional_text(qiniu.get("public_base_url")),
            key_prefix=key_prefix.strip("/"),
        ),
    )
```

- [ ] **Step 5: 实现路由器和空实现**

创建 `xiagent/infrastructure/object_storage/router.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.models import StoredObject


class DisabledObjectStorageService(ObjectStorageService):
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        raise RuntimeError("Object storage is not configured")

    async def delete_object(self, *, key: str) -> None:
        return None


@dataclass(frozen=True)
class ObjectStorageRouter:
    provider: str
    services: dict[str, ObjectStorageService]

    def current(self) -> ObjectStorageService:
        try:
            return self.services[self.provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported object storage provider: {self.provider}") from exc

    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        return await self.current().put_object(
            key=key,
            content=content,
            content_type=content_type,
        )

    async def delete_object(self, *, key: str) -> None:
        await self.current().delete_object(key=key)
```

- [ ] **Step 6: 实现七牛适配器外壳**

创建 `xiagent/infrastructure/object_storage/qiniu.py`，内部使用七牛 SDK，外部只暴露 `ObjectStorageService`：

```python
from __future__ import annotations

import anyio
from qiniu import Auth, put_data

from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.config import QiniuObjectStorageConfig
from xiagent.infrastructure.object_storage.models import StoredObject


class QiniuObjectStorageService(ObjectStorageService):
    def __init__(self, config: QiniuObjectStorageConfig) -> None:
        self._config = config

    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        self._validate_config()
        assert self._config.access_key is not None
        assert self._config.secret_key is not None
        assert self._config.bucket is not None
        assert self._config.public_base_url is not None

        auth = Auth(self._config.access_key, self._config.secret_key)
        token = auth.upload_token(self._config.bucket, key)

        def upload() -> tuple[dict, object]:
            return put_data(token, key, content, mime_type=content_type)

        ret, info = await anyio.to_thread.run_sync(upload)
        if getattr(info, "status_code", None) not in {200, 201}:
            raise RuntimeError(f"Qiniu upload failed: {getattr(info, 'text_body', info)}")

        return StoredObject(
            provider="qiniu",
            bucket=self._config.bucket,
            key=key,
            public_url=f"{self._config.public_base_url.rstrip('/')}/{key}",
            content_type=content_type,
            size_bytes=len(content),
            etag=ret.get("hash") if isinstance(ret, dict) else None,
        )

    async def delete_object(self, *, key: str) -> None:
        return None

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "access_key": self._config.access_key,
                "secret_key": self._config.secret_key,
                "bucket": self._config.bucket,
                "public_base_url": self._config.public_base_url,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Qiniu object storage config is missing: {', '.join(missing)}")
```

- [ ] **Step 7: 导出模块并增加示例配置**

创建 `xiagent/infrastructure/object_storage/__init__.py`：

```python
from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.config import load_object_storage_config
from xiagent.infrastructure.object_storage.models import StoredObject
from xiagent.infrastructure.object_storage.router import (
    DisabledObjectStorageService,
    ObjectStorageRouter,
)

__all__ = [
    "DisabledObjectStorageService",
    "ObjectStorageRouter",
    "ObjectStorageService",
    "StoredObject",
    "load_object_storage_config",
]
```

创建 `xiagent/infrastructure/object_storage.example.toml`：

```toml
[object_storage]
provider = "qiniu"

[object_storage.qiniu]
access_key = ""
secret_key = ""
bucket = ""
region = ""
public_base_url = ""
key_prefix = "xiagent/assets"
```

- [ ] **Step 8: 保护本地配置并声明依赖**

修改 `.gitignore` 增加：

```text
xiagent/infrastructure/object_storage.local.toml
```

修改 `pyproject.toml` dependencies 增加：

```toml
  "qiniu>=7.15.0",
```

- [ ] **Step 9: 运行测试**

Run:

```powershell
python -m pytest tests/test_object_storage.py -q
```

Expected: PASS.

## Task 2: 资产服务支持文件发布、目录和标签索引

**Files:**
- Modify: `xiagent/core/services.py`
- Modify: `xiagent/assets/models.py`
- Modify: `xiagent/assets/service.py`
- Modify: `xiagent/infrastructure/migrations.py`
- Test: `tests/test_assets_service.py`

- [ ] **Step 1: 写目录、标签和 public_url 测试**

在 `tests/test_assets_service.py` 增加假对象存储和测试：

```python
from xiagent.infrastructure.object_storage.base import ObjectStorageService
from xiagent.infrastructure.object_storage.models import StoredObject


class FakeObjectStorage(ObjectStorageService):
    async def put_object(self, *, key: str, content: bytes, content_type: str | None) -> StoredObject:
        return StoredObject(
            provider="fake",
            bucket="test",
            key=key,
            public_url=f"https://cdn.example.test/{key}",
            content_type=content_type,
            size_bytes=len(content),
            etag="fake-etag",
        )

    async def delete_object(self, *, key: str) -> None:
        return None


async def test_import_image_asset_publishes_public_url_and_indexes_tags(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="asset-publisher", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="Image Project")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
        object_storage=FakeObjectStorage(),
    )
    collection = await assets.create_collection_node(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        parent_id=None,
        name="角色参考",
    )
    tag = await assets.create_tag(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="主角",
    )

    asset = await assets.import_file_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        file_name="hero.png",
        content_type="image/png",
        content=b"fake image",
        metadata={},
        publish=True,
        collection_ids=[collection.collection_id],
        tag_ids=[tag.tag_id],
    )
    result = await assets.search_assets(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        tag_ids=[tag.tag_id],
        collection_id=collection.collection_id,
    )

    assert asset.metadata["public_url"].startswith("https://cdn.example.test/")
    assert result.items[0].asset_id == asset.asset_id
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_assets_service.py::test_import_image_asset_publishes_public_url_and_indexes_tags -q
```

Expected: FAIL，原因是 `SqliteAssetService` 尚不接受 `object_storage`、`publish`、目录和标签参数。

- [ ] **Step 3: 增加资产模型记录**

在 `xiagent/assets/models.py` 增加：

```python
@dataclass(frozen=True)
class AssetCollectionRecord:
    collection_id: str
    scope: str
    project_id: str | None
    parent_id: str | None
    name: str
    description: str | None
    sort_order: int
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AssetTagRecord:
    tag_id: str
    scope: str
    project_id: str | None
    name: str
    description: str | None
    created_by: str
    created_at: str
    updated_at: str
```

- [ ] **Step 4: 扩展 AssetService ABC**

在 `xiagent/core/services.py` 中给 `import_file_asset` 增加可选参数：

```python
        publish: bool = False,
        collection_ids: list[str] | None = None,
        tag_ids: list[str] | None = None,
```

并增加 `create_collection_node`、`list_collection_nodes`、`create_tag`、`list_tags` 抽象方法。

- [ ] **Step 5: 扩展迁移**

在 `xiagent/infrastructure/migrations.py` 的 `migrate()` 中确保 `asset_index_entries` 可被重复写入，无需新增表。若现有表已存在，保持兼容。

- [ ] **Step 6: 实现目录和标签服务方法**

在 `xiagent/assets/service.py` 实现：

```python
async def create_collection_node(...)
async def list_collection_nodes(...)
async def create_tag(...)
async def list_tags(...)
```

这些方法复用 `_validate_write_scope` 和 `_validate_search_scope`。

- [ ] **Step 7: 扩展文件导入和索引**

在 `SqliteAssetService.__init__` 增加：

```python
object_storage: ObjectStorageService | None = None,
```

在 `import_file_asset()` 增加 `publish`、`collection_ids`、`tag_ids` 参数。图片 `publish=True` 时：

```python
stored_object = await self._object_storage.put_object(
    key=self._object_key(content_hash=content_hash, file_name=clean_name),
    content=content,
    content_type=content_type,
)
metadata = {
    **metadata,
    "public_url": stored_object.public_url,
    "object_storage": asdict(stored_object),
}
```

创建资产后向 `asset_index_entries` 写入目录和标签关系。

- [ ] **Step 8: 扩展搜索过滤**

在 `search_assets()` 和 `_search_filter()` 增加：

```python
tag_ids: list[str] | None = None
collection_id: str | None = None
```

当存在 `tag_ids` 或 `collection_id` 时，通过 `asset_index_entries` 子查询过滤资产。

- [ ] **Step 9: 运行资产服务测试**

Run:

```powershell
python -m pytest tests/test_assets_service.py -q
```

Expected: PASS.

## Task 3: 资产 API 补齐上传、目录和标签

**Files:**
- Modify: `xiagent/api/dependencies.py`
- Modify: `xiagent/api/routers/assets.py`
- Test: `tests/test_api_smoke.py`

- [ ] **Step 1: 写 API 冒烟测试**

在 `tests/test_api_smoke.py` 增加：

```python
def test_file_asset_upload_returns_public_url_and_searches_by_tag(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "asset-uploader", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="asset-uploader")
        project = client.post(
            "/api/projects",
            json={"name": "Upload Project"},
            headers=headers,
        ).json()
        tag_response = client.post(
            "/api/assets/tags",
            json={"scope": "project", "project_id": project["project_id"], "name": "主角"},
            headers=headers,
        )
        assert tag_response.status_code == 200
        tag = tag_response.json()

        upload_response = client.post(
            "/api/assets/files",
            data={
                "scope": "project",
                "project_id": project["project_id"],
                "name": "hero.png",
                "tag_ids": tag["tag_id"],
                "publish": "true",
            },
            files={"file": ("hero.png", b"fake image", "image/png")},
            headers=headers,
        )

        assert upload_response.status_code == 200
        asset = upload_response.json()
        assert asset["metadata"]["public_url"]

        search_response = client.get(
            "/api/assets/search",
            params={
                "scope": "project",
                "project_id": project["project_id"],
                "tag_ids": tag["tag_id"],
            },
            headers=headers,
        )
        assert search_response.json()["items"][0]["asset_id"] == asset["asset_id"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_api_smoke.py::test_file_asset_upload_returns_public_url_and_searches_by_tag -q
```

Expected: FAIL，原因是 `/api/assets/files` 和 tags API 尚不存在。

- [ ] **Step 3: 在依赖中装配对象存储**

在 `xiagent/api/dependencies.py` 中加载对象存储配置，构造 `ObjectStorageRouter`，并把 `services.assets` 改为传入 `object_storage=router`。

测试环境无真实配置时使用一个测试可用的本地假 public URL 服务，保证 API 测试不依赖七牛云。

- [ ] **Step 4: 增加文件上传请求**

在 `xiagent/api/routers/assets.py` 增加：

```python
@router.post("/files")
async def import_file_asset(
    file: UploadFile,
    scope: Annotated[str, Form()],
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    project_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    collection_ids: Annotated[str | None, Form()] = None,
    tag_ids: Annotated[str | None, Form()] = None,
    publish: Annotated[bool, Form()] = True,
) -> dict:
    ...
```

解析 `metadata_json`、逗号分隔或重复表单传入的 `collection_ids/tag_ids`，调用 `services.assets.import_file_asset()`。

- [ ] **Step 5: 增加目录和标签 API**

在 `xiagent/api/routers/assets.py` 增加：

```text
POST /api/assets/collections
GET /api/assets/collections
POST /api/assets/tags
GET /api/assets/tags
```

请求模型使用 `extra="forbid"`，继续禁止外部传 `user_id`。

- [ ] **Step 6: 扩展 search 参数**

`GET /api/assets/search` 增加 `collection_id` 和 `tag_ids` 查询参数，并传给服务层。

- [ ] **Step 7: 运行 API 测试**

Run:

```powershell
python -m pytest tests/test_api_smoke.py -q
```

Expected: PASS.

## Task 4: 前端工程与资产库页面

**Files:**
- Create: `ui/V1/package.json`
- Create: `ui/V1/index.html`
- Create: `ui/V1/tsconfig.json`
- Create: `ui/V1/vite.config.ts`
- Create: `ui/V1/src/main.tsx`
- Create: `ui/V1/src/app/App.tsx`
- Create: `ui/V1/src/api/client.ts`
- Create: `ui/V1/src/api/assets.ts`
- Create: `ui/V1/src/api/types.ts`
- Create: `ui/V1/src/assets/AssetLibraryPage.tsx`
- Create: `ui/V1/src/assets/AssetUploadDialog.tsx`
- Create: `ui/V1/src/styles/app.css`
- Test: `ui/V1/src/tests/asset-library.test.tsx`

- [ ] **Step 1: 写资产库组件测试**

创建 `ui/V1/src/tests/asset-library.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssetLibraryPage } from "../assets/AssetLibraryPage";

describe("AssetLibraryPage", () => {
  it("renders tree, tags, search, and upload entry", () => {
    render(<AssetLibraryPage />);

    expect(screen.getByText("资产库")).toBeInTheDocument();
    expect(screen.getByText("目录")).toBeInTheDocument();
    expect(screen.getByText("标签")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上传图片" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 创建前端工程并确认测试失败**

创建基础 `package.json` 后运行：

```powershell
Set-Location ui\V1
npm install
npm run test -- src/tests/asset-library.test.tsx
Set-Location ..\..
```

Expected: FAIL，原因是 `AssetLibraryPage` 尚不存在。

- [ ] **Step 3: 实现 API client 和类型**

实现 `ApiClient`、`AssetRecord`、`searchAssets()`、`uploadFileAsset()`、`listCollections()`、`listTags()`。

- [ ] **Step 4: 实现资产库页面**

`AssetLibraryPage` 使用统一工作台布局：

- 左侧目录树。
- 左下标签列表。
- 顶部搜索和筛选。
- 主区域图片资产网格。
- 上传按钮打开 `AssetUploadDialog`。

- [ ] **Step 5: 实现上传弹窗**

`AssetUploadDialog` 支持：

- 选择本地图片文件。
- 输入名称。
- 选择作用域。
- 勾选标签。
- 提交 multipart 到 `/api/assets/files`。

- [ ] **Step 6: 补 CSS**

`ui/V1/src/styles/app.css` 使用既定风格：

```css
body { margin: 0; background: #f5f8fa; color: #172026; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif; }
.app-shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.sidebar { background: #fff; border-right: 1px solid #d8e0e7; }
.workspace { padding: 24px; }
.panel { background: #fff; border: 1px solid #d8e0e7; border-radius: 8px; }
```

- [ ] **Step 7: 运行前端测试和构建**

Run:

```powershell
Set-Location ui\V1
npm run test
npm run build
Set-Location ..\..
```

Expected: PASS.

## Task 5: 工作流输入资产选择器与图生图任务创建

**Files:**
- Create: `ui/V1/src/assets/AssetPicker.tsx`
- Create: `ui/V1/src/task/WorkflowInputForm.tsx`
- Create: `ui/V1/src/task/CreateTaskPage.tsx`
- Create: `ui/V1/src/api/tasks.ts`
- Create: `ui/V1/src/api/workflows.ts`
- Test: `ui/V1/src/tests/workflow-input-form.test.tsx`

- [ ] **Step 1: 写选择器 payload 测试**

创建 `ui/V1/src/tests/workflow-input-form.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkflowInputForm } from "../task/WorkflowInputForm";

describe("WorkflowInputForm", () => {
  it("writes selected asset public URL into image_urls", async () => {
    const onSubmit = vi.fn();
    render(
      <WorkflowInputForm
        schema={{
          type: "object",
          required: ["prompt", "image_urls"],
          properties: {
            prompt: { type: "string" },
            image_urls: { type: "array", items: { type: "string" } },
          },
        }}
        assets={[
          {
            asset_id: "asset_1",
            name: "hero.png",
            mime_type: "image/png",
            metadata: { public_url: "https://cdn.example.test/hero.png" },
          },
        ]}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.type(screen.getByLabelText("prompt"), "改成电影海报风格");
    await userEvent.click(screen.getByRole("button", { name: "选择 hero.png" }));
    await userEvent.click(screen.getByRole("button", { name: "创建并运行" }));

    expect(onSubmit).toHaveBeenCalledWith({
      prompt: "改成电影海报风格",
      image_urls: ["https://cdn.example.test/hero.png"],
    });
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
Set-Location ui\V1
npm run test -- src/tests/workflow-input-form.test.tsx
Set-Location ..\..
```

Expected: FAIL，原因是 `WorkflowInputForm` 尚不存在。

- [ ] **Step 3: 实现 AssetPicker**

`AssetPicker` 接收图片资产列表，只显示 `mime_type` 以 `image/` 开头且存在 `metadata.public_url` 的资产。点击后回传 URL。

- [ ] **Step 4: 实现 WorkflowInputForm**

根据 schema 渲染：

- `string`：文本输入。
- `array<string>` 且字段名为 `image_urls`：资产选择器。
- `string` 且字段名为 `image_url`：单图资产选择器。

- [ ] **Step 5: 实现 CreateTaskPage**

页面加载 `/api/workflows` 和 `/api/assets/search?scope=combined&mime_type=image/*`，选择工作流后渲染 `WorkflowInputForm`。提交时调用 `POST /api/tasks`。

- [ ] **Step 6: 运行前端测试**

Run:

```powershell
Set-Location ui\V1
npm run test
npm run build
Set-Location ..\..
```

Expected: PASS.

## Task 6: 图生图端到端验证

**Files:**
- Modify: `docs/development/2026-05-21-01-dependency-and-deployment-guidelines.md`

- [ ] **Step 1: 准备 Codex 内部浏览器场景**

Codex 内部浏览器验收覆盖：

- 注册/登录。
- 创建项目。
- 进入资产库。
- 上传图片。
- 进入创建任务。
- 选择 `runninghub_image_to_image_test`。
- 从资产库选择图片。
- 创建并运行任务。
- 看到图生图任务结果区域。

- [ ] **Step 2: 更新部署文档**

在依赖和配置文档中补充：

- `qiniu` 依赖。
- `xiagent/infrastructure/object_storage.local.toml` 本地配置。
- 七牛云 `bucket/public_base_url/key_prefix` 说明。
- 正式密钥不得提交。

- [ ] **Step 3: 运行完整验证**

Run:

```powershell
python -m pytest -q
Set-Location ui\V1
npm run test
npm run build
Set-Location ..\..
```

Expected: PASS.

真实图生图链路本地验证命令：

```powershell
python -m uvicorn xiagent.api.app:app --host 127.0.0.1 --port 8000
Set-Location ui\V1
npm run dev -- --host 127.0.0.1
Set-Location ..\..
```

Expected: 使用 Codex 内部浏览器完成上传、资产选择、创建任务、提交图生图输入、查看输出资产的真实页面交互；前提是本地 `object_storage.local.toml`、RunningHub 配置和七牛云 bucket/public domain 有效。验收报告必须记录访问 URL、输入资产、点击路径、任务结果和截图或日志证据。

## 自检

- 对象存储通过基础设施抽象访问，资产和工作流层不直接依赖七牛云。
- 七牛云正式密钥只进入本地未跟踪配置，仓库只提交 example。
- 树形目录和标签均保存在本地数据库并参与搜索。
- 图片文件发布到对象存储，`metadata.public_url` 是工作流选择器使用的标准字段。
- 图生图 workflow 继续接收 `image_urls`，不感知资产库内部实现。
