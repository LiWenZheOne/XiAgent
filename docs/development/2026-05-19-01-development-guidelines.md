# 开发约束与实现准则

## 实现顺序建议

第一版建议按以下顺序实现：

```text
1. 项目骨架与配置
2. core 抽象接口和领域对象
3. SQLite 基础设施
4. 用户与项目模块
5. 资产模块最小闭环
6. 节点基类和显式注册
7. 工作流模板加载与校验
8. 任务运行与节点执行记录
9. HumanApprovalNode 等待与恢复
10. FastAPI 对接接口
11. 示例工作流和示例节点
```

## 代码组织建议

```text
xiagent/
  core/
  users/
  assets/
  workflows/
  nodes/
  runtime/
  adapters/
    langgraph/
  infrastructure/
    sqlite/
    storage/
  api/
workflows/
storage/
tests/
docs/
```

## 接口优先

每个模块先定义对外服务接口，再实现内部细节。

跨模块调用只能依赖服务接口：

```text
UserService
AssetService
WorkflowService
RuntimeService
ExecutionStore
NodeRegistry
```

不得从其他模块导入 repository、database model、内部 helper。

## 节点实现约束

可注册节点必须继承 `BaseNode`。

节点实现可以内部使用 PydanticAI、OpenAI SDK、脚本函数或其他工具库，但这些依赖不得出现在 `BaseNode`、`NodeDescriptor`、`NodeContext`、`NodeResult` 的公共接口中。

节点只接受 `inputs` 和 `NodeContext`，返回 `NodeResult`。

节点访问资产必须通过：

```text
ctx.asset_service
```

## 数据库演进

第一版使用 SQLite。数据库访问封装在 infrastructure 和各模块 repository 内部。

业务服务接口不得返回数据库 ORM 对象。对外返回领域 record 或 DTO。

以后迁移 PostgreSQL 时，不应修改 API 层、节点接口、工作流契约和运行时调用方式。

## 测试策略

第一版至少覆盖：

- 用户注册、登录、项目访问校验。
- 资产导入、文字资产创建、全局和项目作用域查询。
- 资产目录树和标签隔离。
- 工作流契约加载和非法契约报错。
- 节点注册重复 ref 报错。
- 任务创建和简单 DAG 执行。
- 条件分支执行。
- 人工节点 waiting 和 resume。
- 节点执行记录 input/output 不覆盖历史。

测试中可以使用 `Protocol` 辅助替身类型，但正式代码不使用 `Protocol` 作为平台接口。

## 文档维护

设计变更先更新对应模块设计文档，再修改代码。

跨模块接口变更必须同步更新：

- `AGENTS.md` 中的项目规则。
- 对应 `docs/design/` 模块文档。
- `docs/development/` 中的实现准则或计划。

## 第一版完成标准

第一版后端完成时，至少应满足：

- 可以注册用户并创建项目。
- 可以导入文件资产和创建文字资产。
- 可以创建全局和项目级标签、目录。
- 可以加载至少一个工作流模板。
- 可以显式注册至少三个节点：示例 AI 节点、示例工具节点、人工确认节点。
- 可以创建任务并执行到完成或等待。
- 可以恢复等待中的任务。
- 可以查询任务详情、节点执行记录和任务事件。
- 节点执行记录完整保存输入快照和输出快照。

