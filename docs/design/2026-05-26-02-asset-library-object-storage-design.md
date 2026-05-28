# 资产库、对象存储与工作流文件选择器设计

## 背景

XiAgent 第一版已经有本地资产服务、工作流运行时和图生图节点。现有图生图模型只接受可公网访问的图片 URL，本地运行时无法直接把本地文件路径交给模型使用，因此需要补充对象存储基础设施，把本地上传的图片发布为网络 URL。

本设计覆盖第一版资产库前端、后端资产上传管理、树形目录与标签检索、对象存储路由器抽象，以及工作流创建时从资产库选择图片并运行图生图工作流的闭环。

## 目标

- 支持在前端资产库上传图片文件，并在资产记录中保留可用于模型调用的公网 URL。
- 支持树形目录和标签两套本地管理系统，二者用于资产组织和搜索，不与云服务商存储结构耦合。
- 支持工作流创建页从资产库选择图片，把选中资产的 URL 写入 `image_urls` 输入。
- 支持最终验证场景：上传或选择图片资产，创建图生图任务，图生图节点拿到 URL 并完成运行。
- 对象存储统一通过平台抽象接口访问，业务代码不得直接调用七牛云或其他云服务商 SDK。

## 非目标

- 第一版不做拖拽式工作流编辑器。
- 第一版不做完整的批量资产治理、复杂权限共享或多租户对象存储策略。
- 第一版不把目录树映射为云服务商真实目录。云端对象 key 是基础设施内部实现，目录树只存在于 XiAgent 本地资产索引。
- 第一版不要求所有文件类型都可公网预览。图生图闭环优先支持图片文件。

## 总体架构

```text
前端资产库 / 工作流输入表单
  -> /api/assets/*
     -> AssetService
        -> 本地 SQLite 资产、目录、标签、索引
        -> ObjectStorageRouter
           -> ObjectStorageService(ABC)
              -> QiniuObjectStorageService
```

边界规则：

- `xiagent.assets` 只依赖对象存储抽象，不直接依赖七牛云 SDK 或七牛 HTTP 细节。
- `xiagent.infrastructure.object_storage` 负责对象存储路由器、配置和云服务商适配器。
- 前端只消费 HTTP API，不读取本地文件路径、SQLite 表或 Python 内部实现。
- 工作流节点继续只依赖 `AssetService`、`NodeContext` 和工作流输入输出契约。

## 对象存储路由器

新增基础设施抽象：

```python
class ObjectStorageService(ABC):
    @abstractmethod
    async def put_object(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str | None,
    ) -> StoredObject:
        ...

    @abstractmethod
    async def delete_object(self, *, key: str) -> None:
        ...
```

`StoredObject` 返回：

```text
provider
bucket
key
public_url
content_type
size_bytes
etag
```

`ObjectStorageRouter` 根据配置选择 provider。第一版支持：

- `local_none`：不发布公网 URL，仅用于无云配置时保持后端可启动。
- `qiniu`：把图片发布到七牛云对象存储，并返回可访问 URL。

业务层只持有 `ObjectStorageRouter` 或 `ObjectStorageService`，不得直接 import 七牛云 SDK。

## 七牛云配置

正式密钥只写入本地未跟踪配置文件，例如：

```text
xiagent/infrastructure/object_storage.local.toml
```

该文件必须被 `.gitignore` 排除。仓库只提交示例：

```text
xiagent/infrastructure/object_storage.example.toml
```

示例配置结构：

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

环境变量优先级高于本地配置文件，便于生产部署：

```text
XIAGENT_OBJECT_STORAGE_PROVIDER
QINIU_ACCESS_KEY
QINIU_SECRET_KEY
QINIU_BUCKET
QINIU_REGION
QINIU_PUBLIC_BASE_URL
QINIU_KEY_PREFIX
```

## 资产数据模型

现有 `assets` 表继续保存资产本体。图片上传时：

- 原始文件仍可按现有本地存储规则保存一份，保证本地内容可追溯。
- 云端对象信息写入 `metadata_json`，不新增云服务商专属字段。
- `metadata.public_url` 是工作流和前端选择器使用的稳定字段。

建议 metadata 结构：

```json
{
  "public_url": "https://cdn.example.com/xiagent/assets/ab/cd/file.png",
  "object_storage": {
    "provider": "qiniu",
    "bucket": "bucket-name",
    "key": "xiagent/assets/ab/cd/file.png",
    "etag": "..."
  },
  "tags": ["角色", "参考图"],
  "collection_ids": ["collection_..."]
}
```

## 树形目录与标签

第一版底层必须支持目录树和标签两套管理系统：

- `asset_collections`：本地虚拟目录树，不代表真实文件路径或云端 key。
- `asset_tags`：本地标签定义，分全局和项目作用域。
- `asset_index_entries`：资产与目录、标签、搜索文本的关联索引。

API 需要覆盖：

- 创建目录节点、移动目录节点、列出目录树。
- 创建标签、列出标签。
- 给资产分配目录和标签。
- 搜索资产时按 `collection_id`、`tag_ids`、`keyword`、`mime_type`、`scope` 过滤。

目录树和标签均保存在本地数据库。图片二进制内容发布到云服务商，但云服务商只负责对象存储，不参与业务目录和标签语义。

## 资产 API

第一版新增或补齐以下接口：

```text
POST /api/assets/files
GET /api/assets/search
GET /api/assets/{asset_id}
GET /api/assets/{asset_id}/content
DELETE /api/assets/{asset_id}
POST /api/assets/collections
GET /api/assets/collections
POST /api/assets/tags
GET /api/assets/tags
POST /api/assets/{asset_id}/collections
POST /api/assets/{asset_id}/tags
```

`POST /api/assets/files` 使用 multipart 表单：

```text
file
scope
project_id
name
metadata_json
collection_ids
tag_ids
publish: true | false
```

图片文件默认 `publish=true`，上传成功后返回资产记录和 `metadata.public_url`。

## 前端资产库

资产库页面采用与现有 UI 任务交互设计一致的左侧导航和工作台布局：

- 顶部工具区：搜索框、作用域筛选、类型筛选、上传按钮。
- 左侧资产管理区：目录树和标签筛选。
- 主区域：资产网格，图片资产显示缩略图、名称、作用域、标签、是否已有 URL。
- 详情抽屉：显示元数据、public URL、复制 URL、删除、目录/标签分配。

第一版优先支持：

- 单文件图片上传。
- 项目/全局作用域选择。
- 搜索、目录筛选、标签筛选。
- 删除软删除。
- 复制 URL。

## 工作流文件选择器

工作流创建页的输入表单不直接猜测所有字段。第一版使用约定：

- 字段名为 `image_urls` 且 schema 为字符串数组时，显示图片资产选择器。
- 字段名为 `image_url` 且 schema 为字符串时，显示单图资产选择器。
- 后续可在 workflow `ui` 配置中显式声明 `input_widgets`，避免仅靠字段名推断。

选择器行为：

- 打开资产选择弹窗。
- 默认查询 `scope=combined`、当前 `project_id`、`mime_type=image/*`。
- 只允许选择已有 `metadata.public_url` 的图片资产。
- 支持从弹窗内上传新图片，上传成功后立即可选。
- 提交任务时把选中资产的 `metadata.public_url` 写入 `image_urls`。

## 图生图验证场景

最终测试用例以 `runninghub_image_to_image_test.workflow.yaml` 为基础：

1. 创建测试用户和项目。
2. 上传本地图片到资产库，后端保存本地资产记录并发布到七牛云，返回 `metadata.public_url`。
3. 前端创建图生图任务，进入任务详情中的用户输入节点。
4. 在节点资产选择器中选择该图片，提交后该节点 `input_snapshot.image_urls` 包含选中图片 URL，并由节点输出供下游引用。
5. 运行时执行 `ai.runninghub_image_to_image.v1`，返回结果 URL。
6. 前端任务详情页展示图生图结果。

测试可以分层：

- 后端单元测试使用假对象存储服务，验证 API、AssetService 和 metadata。
- 前端组件测试使用 mock API 验证选择器 payload。
- 真实端到端测试使用七牛云正式配置和 RunningHub 配置，作为可手动触发或本地验证场景，不把密钥提交到仓库。

## 风险与约束

- 七牛云 bucket、区域和 public domain 必须配置正确，否则上传成功也无法得到可访问 URL。
- 正式密钥不得进入 git，必须依赖 `.gitignore` 和提交前检查。
- 如果对象存储上传成功但数据库写入失败，需要尽量删除云端对象，避免孤儿文件。
- 如果本地文件保存成功但对象存储发布失败，API 应返回明确错误，不创建“看似可用于图生图但无 URL”的图片资产。
- 工作流节点不得直接读取本地文件路径；图生图模型只接收 URL。
