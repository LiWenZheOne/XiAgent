# 资产模块设计

## 模块定位

资产模块负责管理本地文件资产和文字资产，并提供独立于文件管理系统的检索分类能力。

资产模块是独立一级模块。工作流、节点和 API 只能通过 `AssetService` 使用资产，不得直接读取文件路径、SQLite 表或检索内部结构。

## 第一版能力

- 导入本地文件资产。
- 直接创建文字资产。
- 支持全局项目资产和普通项目资产。
- 支持项目级目录树，其中 `project_id=global` 作为共享全局项目目录树。
- 支持项目级标签，其中 `project_id=global` 作为共享全局项目标签。
- 支持关键词搜索、标签筛选、目录筛选。
- 支持资产元数据更新。
- 支持软删除。
- 支持项目对全局资产建立项目内分类和用途说明。

不支持外部 URL 资产。

## 核心实体

### Asset

资产本体。

```text
asset_id
scope: project
project_id
asset_type: file | text
name
mime_type
content_hash
size_bytes
storage_uri
text_content
metadata
created_by
created_at
updated_at
deleted_at
```

规则：

- `scope = project` 时 `project_id` 必须存在。
- 全局资产统一使用 `scope = project` 且 `project_id = global`，不再使用 `scope = global` 作为资产作用域。
- 文件资产内容保存在本地文件存储，数据库保存 `storage_uri`。
- 文字资产第一版可以直接保存在 SQLite。

### AssetProjectBinding

某个项目如何使用某个资产。

```text
binding_id
project_id
asset_id
display_name
usage_note
metadata
created_by
created_at
updated_at
```

全局项目资产被普通项目使用时，通过绑定记录保存项目内别名、用途说明和项目检索关系。

### AssetCollection

虚拟目录树节点，不是文件目录。

```text
collection_id
scope: project
project_id
parent_id
name
description
sort_order
created_by
created_at
updated_at
```

普通项目目录树不会污染全局项目目录树。

### AssetTag

标签定义。

```text
tag_id
scope: project
project_id
name
description
created_by
created_at
updated_at
```

普通项目标签不会污染全局项目标签。

### AssetIndexEntry

资产与目录、标签、关键词索引的关系。

```text
entry_id
scope: project
project_id
asset_id
collection_id
tag_id
search_text
created_at
updated_at
```

第一版使用 SQLite 关系表和 FTS5 实现搜索。外部接口不暴露 FTS5 细节。

## 对外接口

```python
class AssetService(ABC):
    async def import_file_asset(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        file_name: str,
        content_type: str,
        content: bytes,
        metadata: dict,
    ) -> AssetRecord:
        ...

    async def create_text_asset(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        name: str,
        text: str,
        metadata: dict,
    ) -> AssetRecord:
        ...

    async def get_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> AssetRecord:
        ...

    async def get_asset_content(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> AssetContent:
        ...

    async def copy_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        target_scope: str,
        target_project_id: str | None,
        source_project_id: str | None = None,
        copy_tags: bool = True,
    ) -> AssetRecord:
        ...

    async def move_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        target_scope: str,
        target_project_id: str | None,
        source_project_id: str | None = None,
        copy_tags: bool = True,
    ) -> AssetRecord:
        ...

    async def update_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        name: str,
    ) -> AssetRecord:
        ...

    async def update_asset_metadata(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None,
        metadata: dict,
    ) -> AssetRecord:
        ...

    async def delete_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str | None,
    ) -> None:
        ...

    async def attach_asset_to_project(
        self,
        *,
        user_id: str,
        asset_id: str,
        project_id: str,
        display_name: str | None = None,
        usage_note: str | None = None,
        metadata: dict | None = None,
    ) -> AssetProjectBindingRecord:
        ...

    async def create_collection_node(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        parent_id: str | None,
        name: str,
        description: str | None = None,
    ) -> AssetCollectionRecord:
        ...

    async def move_collection_node(
        self,
        *,
        user_id: str,
        collection_id: str,
        new_parent_id: str | None,
        project_id: str | None = None,
    ) -> AssetCollectionRecord:
        ...

    async def assign_asset_to_collection(
        self,
        *,
        user_id: str,
        asset_id: str,
        collection_id: str,
        project_id: str | None = None,
    ) -> None:
        ...

    async def create_tag(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        name: str,
        description: str | None = None,
    ) -> AssetTagRecord:
        ...

    async def tag_asset(
        self,
        *,
        user_id: str,
        asset_id: str,
        tag_id: str,
        project_id: str | None = None,
    ) -> None:
        ...

    async def search_assets(
        self,
        *,
        user_id: str,
        scope: str,
        project_id: str | None,
        keyword: str | None = None,
        asset_type: str | None = None,
        mime_type: str | None = None,
        tag_ids: list[str] | None = None,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AssetSearchResult:
        ...
```

跨项目复制与转移必须通过 `AssetService.copy_asset` / `AssetService.move_asset` 完成。目标第一版限定为项目资产库；复制会保留资产内容和同名标签，剥离旧的公开 URL / 对象存储发布元数据，避免复制资产仍指向原资产公开地址。转移采用“复制到目标项目后软删除原资产”的语义，历史任务引用仍指向原资产记录。普通项目组合视图中的全局项目资产只能复制到项目，不能被项目组合视图转移或删除；需要管理共享资产时必须切换到全局项目。

`update_asset` 只更新资产展示名称，不改动底层文件存储 URI、内容哈希、目录关系或标签关系。调用方必须传入非空 `name`；空名称返回 `asset_name_required`，资产不存在返回 `asset_not_found`，项目资产写入前必须通过 `UserService.ensure_project_access(..., action="asset:write")`。

## 作用域查询规则

`scope` 支持：

```text
project
combined
```

规则：

- `project` 只查项目资产和项目检索结构。
- `project` + `project_id=global` 是唯一全局项目资产查询口径，用于共享模板和素材。
- `combined` 查全局项目资产和当前项目资产，项目级分类和标签优先用于项目视图。
- `scope=global` 不再是合法资产查询或写入口径；旧数据必须由迁移规范化到 `scope=project, project_id=global`。

## 文件存储规则

文件资产按内容 hash 存储，避免重名冲突和重复文件。

示例：

```text
storage/assets/ab/cd/abcdef...png
```

文件路径规则属于资产模块内部实现，不暴露给节点和其他模块。

## 任务资产引用

节点执行中使用过的资产需要记录到节点执行元数据或单独关系表：

```text
node_execution_asset_refs
  node_execution_id
  asset_id
  usage_type
  source
  created_at
```

前端未来打开任务详情时，可以展示该任务使用过哪些资产、由哪个节点使用、用途是什么。
