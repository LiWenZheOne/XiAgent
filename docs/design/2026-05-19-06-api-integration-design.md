# 前端对接 API 设计

## 设计目标

第一版先实现后端 API，为未来前端提供完整数据支撑。

前端用户不编排工作流，只选择已有工作流模板、创建任务、查看任务执行详情、处理等待中的人工输入、管理资产。

## API 分组

### Auth

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

### Projects

```text
POST /api/projects
GET  /api/projects
GET  /api/projects/{project_id}
```

### Workflow Templates

```text
GET  /api/workflow-templates?scope=global|project|combined&project_id=...
GET  /api/workflow-templates/{template_id}
POST /api/workflow-templates/reload
```

### Nodes

```text
GET /api/nodes
GET /api/nodes/{node_ref}
```

### Tasks

```text
POST /api/tasks
GET  /api/tasks?project_id=...
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/events
GET  /api/tasks/{task_id}/node-executions
POST /api/tasks/{task_id}/resume
```

### Assets

```text
POST   /api/assets/files
POST   /api/assets/text
GET    /api/assets
GET    /api/assets/{asset_id}
GET    /api/assets/{asset_id}/content
PATCH  /api/assets/{asset_id}
DELETE /api/assets/{asset_id}
```

### Asset Index

```text
POST   /api/assets/collections
PATCH  /api/assets/collections/{collection_id}
DELETE /api/assets/collections/{collection_id}
POST   /api/assets/collections/{collection_id}/assets
POST   /api/assets/tags
POST   /api/assets/{asset_id}/tags
GET    /api/assets/search
```

## 前端页面映射

未来前端可以按以下页面组织：

```text
登录 / 注册
  ↓
项目列表 / 项目选择
  ↓
工作流模板列表
  ↓
创建任务
  ↓
任务列表
  ↓
任务详情
     ├─ 初始输入
     ├─ 当前状态
     ├─ 节点图状态
     ├─ 每个节点 input/output/error
     ├─ 时间线 events
     ├─ 使用资产列表
     └─ waiting 时显示人工提交控件

资产库
  ├─ 全局资产
  ├─ 项目资产
  ├─ 项目目录树
  ├─ 标签筛选
  └─ 搜索
```

## 任务详情响应要求

`GET /api/tasks/{task_id}` 应返回前端打开任务详情需要的核心数据：

```text
task
workflow_template_summary
current_view
node_execution_summary
waiting_input_request
asset_refs_summary
```

完整节点执行和事件可以通过独立接口分页获取。

## 错误响应

API 错误响应统一结构：

```json
{
  "error": {
    "code": "project_access_denied",
    "message": "当前用户没有访问该项目的权限",
    "details": {}
  }
}
```

错误码由模块定义，API 层只负责转换 HTTP 状态码。

## 权限检查点

- 创建任务：检查项目访问权限。
- 查询任务：检查任务所属项目访问权限。
- 恢复任务：检查任务所属项目访问权限。
- 创建项目资产：检查项目访问权限。
- 查询项目资产：检查项目访问权限。
- 使用项目工作流模板：检查项目访问权限。

全局资产和全局模板第一版对登录用户可读。写入全局资产和全局模板第一版可以先限制为本地开发配置或管理员标记。

