# 节点、任务运行与恢复设计

## 模块定位

节点模块负责定义和注册可执行节点。运行模块负责任务生命周期、节点执行记录、事件、等待与恢复。

节点是工作流唯一可调用单元。模型、工具脚本、人工确认和未来子工作流都必须封装为节点。

## 节点接口

正式代码使用抽象基类，不使用 `Protocol` 作为平台接口。

```python
class BaseNode(ABC):
    @abstractmethod
    def describe(self) -> NodeDescriptor:
        ...

    @abstractmethod
    async def run(
        self,
        ctx: NodeContext,
        inputs: Mapping[str, Any],
    ) -> NodeResult:
        ...
```

### NodeDescriptor

```text
ref
name
version
kind
input_schema
output_schema
config_schema
description
```

`ref` 示例：

```text
ai.planner.v1
tool.search_local_assets.v1
system.human_approval.v1
```

### NodeContext

```text
user_id
project_id
task_id
node_id
node_execution_id
config
asset_service
event_sink
logger
```

节点通过 `asset_service` 获取资产。节点不得直接读文件系统或数据库。

### NodeResult

```text
status
output
metadata
asset_refs
```

`status` 支持：

```text
succeeded
waiting
failed
```

## 节点注册

第一版使用显式注册。

```python
def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(PlannerNode())
    registry.register(HumanApprovalNode())
    registry.register(WriterNode())
    return registry
```

注册规则：

- 只接受 `BaseNode` 实例。
- `ref` 必须唯一。
- `describe()` 必须返回合法 JSON Schema。
- 注册时可以执行轻量校验，不执行外部模型调用。

## 任务实体

```text
task_id
workflow_template_id
workflow_id
workflow_version
user_id
project_id
input
status
current_view
created_at
started_at
finished_at
updated_at
```

`status` 支持：

```text
created
running
waiting
succeeded
failed
canceled
```

## 节点执行实体

```text
node_execution_id
task_id
node_id
node_ref
attempt
input_snapshot
output_snapshot
status
error
metadata
started_at
finished_at
created_at
updated_at
```

同一任务中同一节点可以有多次 attempt。旧记录不覆盖、不删除。

## 任务事件

```text
event_id
task_id
event_type
payload
created_at
```

事件类型第一版支持：

```text
task_created
task_started
node_started
node_succeeded
node_failed
human_input_requested
task_waiting
task_resumed
task_succeeded
task_failed
```

## 执行流程

```text
1. RuntimeService 接收 template_id、project_id、input。
2. UserService 校验项目访问权限。
3. WorkflowService 读取模板并校验输入。
4. RuntimeService 创建 Task。
5. LangGraphAdapter 根据契约构建执行图。
6. 节点执行前解析输入长路径。
7. 保存 NodeExecution input_snapshot。
8. 调用 BaseNode.run()。
9. 保存 output_snapshot、status、metadata、asset_refs。
10. 追加 TaskEvent。
11. 根据边和条件分支决定后续节点。
12. 任务进入 succeeded、failed 或 waiting。
```

## 人工等待与恢复

第一版提供内置节点：

```text
system.human_approval.v1
```

执行到人工节点时：

```text
Task.status = waiting
NodeExecution.status = waiting
TaskEvent = human_input_requested
```

恢复接口收到人工输入后：

```text
1. 校验用户项目权限。
2. 找到等待中的 Task 和 NodeExecution。
3. 校验提交内容满足人工节点 output_schema。
4. 写入 NodeExecution.output_snapshot。
5. 设置 NodeExecution.status = succeeded。
6. 追加 task_resumed 事件。
7. 从等待节点后续边继续执行。
```

## 当前视图

`current_view` 是派生视图，不是唯一事实来源。

示例：

```json
{
  "status": "succeeded",
  "active_node_outputs": {
    "planner": "node_execution_001",
    "human_review": "node_execution_004",
    "writer": "node_execution_005"
  },
  "final_output": {
    "script": "..."
  }
}
```

未来回溯重跑时，可以通过追加新 attempt 更新当前视图，同时保留旧执行记录。

