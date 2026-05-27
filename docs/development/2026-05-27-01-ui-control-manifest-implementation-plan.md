# UI 控件 Manifest 与 V2 节点控件库实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan.

## 目标

把 V2 任务界面中的工作流节点展示能力拆成后端可校验的 UI 控件 Manifest、前端可复用的节点控件库，以及工作流可声明的 UI 配置。

本计划采用已确认的建模规则：

- 工作流显式 UI 配置优先：`nodes[].ui` > `workflow.ui.defaults` > `NodeDescriptor.ui_defaults` > 系统 fallback。
- 默认把“模型生成候选图”和“用户三选一”拆成两个节点，三选一由可复用交互节点负责。
- 保留高级单节点模式：复合节点可以在同一节点内生成候选图并等待选择，但必须继续走标准 waiting/resume、output schema 校验和 UI 控件绑定规则。
- 后端只定义统一 UI 对接规则和数据兼容性校验，不绑定 V2 React 组件路径。

## 架构边界

后端负责：

- 维护 UI 控件 Manifest。
- 校验 workflow UI 配置和节点默认 UI 配置。
- 暴露只读控件库 API。
- 提供可复用交互节点，例如 `system.user_choice.v1`。
- 在任务 snapshot 中保留工作流 UI 配置和节点等待 metadata。

前端 V2 负责：

- 用本地 `node-ui` 注册表把 `control_id + variant + mode` 解析到 React 控件。
- 在任务详情页按 UI 配置渲染输入、输出、等待交互。
- 提供“控件库”导航页签，浏览后端 Manifest 与前端预览 fixture。
- 交互提交 payload 时遵守控件 Manifest 和节点 `outputs` schema。

工作流负责：

- 在 `workflow.ui.defaults` 放通用默认展示规则。
- 在 `nodes[].ui` 放具体节点展示规则。
- 使用可复用选择节点组合模型生成节点，除非确实需要高级单节点模式。

## 阶段 1：后端 UI 控件 Manifest 基础

### 1.1 新增模块

新增目录：

```text
xiagent/ui_controls/
  __init__.py
  catalog.py
  models.py
```

`models.py` 使用 dataclass，不引入前端或具体 UI 框架概念：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UiControlBindingRequirement:
    name: str
    required: bool = True
    accepted_sources: tuple[str, ...] = ("workflow.input", "node.input", "node.output", "node.metadata", "nodes.output")
    schema_constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UiControlVariant:
    name: str
    label: str
    tags: tuple[str, ...] = ()
    modes: tuple[str, ...] = ("readonly",)
    required_bindings: tuple[UiControlBindingRequirement, ...] = ()
    submit_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class UiControlDescriptor:
    control_id: str
    version: str
    name: str
    kind: str
    tags: tuple[str, ...]
    variants: tuple[UiControlVariant, ...]
    description: str | None = None
```

`catalog.py` 提供稳定只读注册表：

```python
class UiControlCatalog:
    def __init__(self, controls: list[UiControlDescriptor]) -> None:
        self._controls = {control.control_id: control for control in controls}

    def list_controls(self) -> list[UiControlDescriptor]:
        return list(self._controls.values())

    def get(self, control_id: str) -> UiControlDescriptor:
        try:
            return self._controls[control_id]
        except KeyError as exc:
            raise KeyError(f"unknown UI control: {control_id}") from exc
```

### 1.2 预置首批控件

在 `build_builtin_ui_control_catalog()` 中预置：

- `ui.display.value.v1`：普通值展示 fallback。
- `ui.display.image_candidates.v1`：图片候选列表展示。
- `ui.choice.image_three.v1`：三图单选交互，变体包括 `equal_grid`、`hero_list`、`hover_focus`。
- `ui.interaction.approval.v1`：人审/批准类交互。
- `ui.fallback.schema_form.v1`：schema 驱动输入表单 fallback。

`ui.choice.image_three.v1` 的 Manifest 必须声明：

- `kind = "interaction"`。
- tags 包含 `image`、`choice`、`select_one`、`candidates_3`。
- 必需绑定：`items_path`、`image_url_path`、`value_path`。
- `items_path` 目标必须是数组，候选数量至少 1，推荐 3。
- `image_url_path` 指向数组元素中的图片 URL 字段。
- `submit_schema` 至少支持 `selected_id`、`selected_index`、`selected_item`、`selected_image_url`。

### 1.3 测试

新增 `tests/test_ui_control_catalog.py`：

- 预置控件 ID 不重复。
- `ui.choice.image_three.v1` 包含三个变体。
- 查询未知控件抛稳定错误。
- Manifest 可以通过 `dataclasses.asdict()` 转为 API 响应。

运行：

```powershell
python -m pytest tests/test_ui_control_catalog.py
```

## 阶段 2：NodeDescriptor 增加 UI 默认配置

### 2.1 修改节点描述符

修改 `xiagent/nodes/base.py`：

```python
@dataclass(frozen=True)
class NodeDescriptor:
    ref: str
    name: str
    version: str
    kind: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any] | None = None
    description: str | None = None
    ui_defaults: dict[str, Any] = field(default_factory=dict)
```

注意事项：

- `ui_defaults` 只能表达保底建议。
- 不允许引用前端组件路径。
- 现有节点如果没有默认 UI，保持空字典。

### 2.2 注册校验

修改 `xiagent/nodes/registry.py`：

- 注册节点时继续校验 input/output/config schema。
- 如果 `ui_defaults` 非空，调用 UI 配置校验器校验控件 ID、variant、mode 和 bindings。
- 校验只依赖 UI 控件 Manifest 和节点自身 schema。

### 2.3 测试

更新 `tests/test_node_registry.py`：

- 空 `ui_defaults` 兼容旧节点。
- 有效 `ui_defaults` 可以注册。
- 未知 `control_id` 注册失败。
- 默认 binding 指向不存在字段时注册失败。

运行：

```powershell
python -m pytest tests/test_node_registry.py tests/test_ui_control_catalog.py
```

## 阶段 3：工作流 UI 配置校验

### 3.1 扩展 validator 入口

修改 `xiagent/workflows/validator.py`：

```python
def validate_workflow_contract(
    contract: dict[str, Any],
    registry: NodeRegistry,
    ui_controls: UiControlCatalog | None = None,
) -> None:
    catalog = ui_controls or build_builtin_ui_control_catalog()
    ...
```

保留现有调用兼容性。

### 3.2 有效 UI 配置解析

新增内部函数：

```python
def _resolve_effective_node_ui(workflow: dict[str, Any], node_def: dict[str, Any], descriptor: NodeDescriptor) -> dict[str, Any]:
    ...
```

解析顺序：

1. `nodes[].ui`。
2. `workflow.ui.defaults[<node_kind>]` 或 `workflow.ui.defaults[<node_ref>]`。
3. `descriptor.ui_defaults`。
4. 空配置，由前端 fallback 处理。

### 3.3 支持的 binding 路径

校验以下路径：

```text
$workflow.input.<field>
$node.input.<field>
$node.output.<field>
$node.metadata.<field>
$nodes.<node_id>.output.<field>
```

规则：

- `$workflow.input` 从 workflow input schema 解析。
- `$node.input` 从当前节点 `inputs` schema 解析。
- `$node.output` 从当前节点 `outputs` schema 解析。
- `$node.metadata` 从 UI 配置声明的 `metadata_schema` 或节点 descriptor 的 waiting metadata 约定解析。
- `$nodes.<node_id>.output` 只能引用上游节点输出，不能引用不存在节点。

### 3.4 控件兼容性检查

校验项：

- `control_id` 存在。
- `variant` 存在。
- `mode` 被该变体支持。
- 必需 bindings 全部存在。
- binding 源类型满足控件 Manifest 的 `accepted_sources`。
- binding 目标 schema 满足控件约束，例如数组、图片 URL 字段、单选提交 payload。
- 交互控件的 `submit_schema` 必须能被节点 `outputs` schema 接收。

错误码继续使用设计文档中定义的稳定值：

```text
unknown_ui_control
unknown_ui_control_variant
invalid_ui_binding_path
ui_binding_schema_mismatch
missing_ui_binding
unsupported_ui_control_mode
ui_control_payload_mismatch
```

### 3.5 测试

更新 `tests/test_workflow_validator.py`：

- 工作流无 UI 配置仍兼容。
- `nodes[].ui` 有效时通过。
- `workflow.ui.defaults` 能作为默认生效。
- 工作流配置覆盖节点默认配置。
- 未知控件失败。
- 未知 variant 失败。
- 缺少必需 binding 失败。
- binding 指向不存在字段失败。
- 三选一控件绑定非数组失败。
- 三选一控件绑定数组但缺图片 URL 字段失败。
- `$node.metadata.candidates` 可用于高级单节点模式。
- 交互 submit payload 与节点 outputs 不兼容时失败。

运行：

```powershell
python -m pytest tests/test_workflow_validator.py tests/test_node_registry.py tests/test_ui_control_catalog.py
```

## 阶段 4：后端控件库 API

### 4.1 服务装配

修改 `xiagent/api/dependencies.py`：

- `ApiServices` 增加 `ui_controls: UiControlCatalog`。
- `build_services()` 中调用 `build_builtin_ui_control_catalog()`。

### 4.2 路由

新增 `xiagent/api/routers/ui.py`：

```python
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api/ui", tags=["ui"])


@router.get("/node-controls")
def list_node_controls(services: ApiServices = Depends(get_services)) -> dict[str, Any]:
    return {"controls": [asdict(control) for control in services.ui_controls.list_controls()]}


@router.get("/node-controls/{control_id}")
def get_node_control(control_id: str, services: ApiServices = Depends(get_services)) -> dict[str, Any]:
    try:
        return {"control": asdict(services.ui_controls.get(control_id))}
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "unknown_ui_control"})
```

修改 `xiagent/api/app.py` 注册路由。

### 4.3 测试

新增或更新 API 测试：

- `GET /api/ui/node-controls` 返回预置控件。
- `GET /api/ui/node-controls/ui.choice.image_three.v1` 返回三选一控件。
- 未知控件返回 404 和稳定错误码。

运行：

```powershell
python -m pytest tests/test_api_ui_controls.py tests/test_ui_control_catalog.py
```

## 阶段 5：可复用用户选择节点

### 5.1 新增节点

新增 `xiagent/nodes/system/user_choice.py`。

节点 ref：

```text
system.user_choice.v1
```

节点定位：

- 通用用户单选交互节点。
- 默认用于“上游生成候选图，当前节点等待用户选择”。
- 不直接关心候选项由哪个模型或工具生成。

输入 schema：

```json
{
  "type": "object",
  "properties": {
    "question": {"type": "string"},
    "candidates": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "label": {"type": "string"},
          "image_url": {"type": "string"},
          "asset_id": {"type": "string"},
          "value": {}
        },
        "required": ["id"],
        "additionalProperties": true
      }
    }
  },
  "required": ["candidates"],
  "additionalProperties": true
}
```

输出 schema：

```json
{
  "type": "object",
  "properties": {
    "selected_id": {"type": "string"},
    "selected_index": {"type": "integer", "minimum": 0},
    "selected_item": {"type": "object", "additionalProperties": true},
    "selected_image_url": {"type": "string"}
  },
  "required": ["selected_id", "selected_item"],
  "additionalProperties": true
}
```

执行行为：

- 节点读取输入候选项。
- 返回 waiting 状态。
- waiting metadata 写入 `question`、`candidates`、`selection_mode = "single"`。
- 恢复时由现有 runtime 校验用户提交 payload 是否满足当前工作流节点 `outputs` schema。

### 5.2 默认 UI

`NodeDescriptor.ui_defaults`：

```python
{
    "controls": {
        "interaction": {
            "control_id": "ui.choice.image_three.v1",
            "variant": "equal_grid",
            "mode": "interactive",
            "bindings": {
                "items_path": "$node.input.candidates",
                "image_url_path": "image_url",
                "value_path": "id",
            },
        }
    }
}
```

该默认值只是保底。具体工作流可以改成 `hero_list` 或 `hover_focus`。

### 5.3 注册和测试

修改 `xiagent/nodes/__init__.py` 注册 `SystemUserChoiceNode`。

测试覆盖：

- builtins registry 包含 `system.user_choice.v1`。
- 节点输入候选图后进入 waiting。
- waiting metadata 带候选项。
- resume 提交的选择结果写入 output snapshot。
- 不满足 outputs schema 的 resume payload 失败。

运行：

```powershell
python -m pytest tests/test_node_registry.py tests/test_runtime_service.py
```

## 阶段 6：高级单节点模式验证

### 6.1 测试用复合节点

在测试中定义临时节点，不进入正式节点库：

- 输入 prompt。
- 执行时生成固定三张候选图 fixture。
- 返回 waiting，metadata 包含 `candidates`。
- 工作流 `nodes[].ui.controls.interaction.bindings.items_path` 使用 `$node.metadata.candidates`。
- resume payload 写入 `selected_item` 和 `selected_image_url`。

### 6.2 测试点

新增 runtime 或 validator 测试：

- `$node.metadata.candidates` 绑定通过校验。
- 复合节点 waiting metadata 能进入任务详情 snapshot。
- resume payload 按节点 outputs schema 校验。
- 高级单节点模式不需要前端知道节点内部实现。

运行：

```powershell
python -m pytest tests/test_workflow_validator.py tests/test_runtime_service.py
```

## 阶段 7：V2 控件库类型和注册表

### 7.1 新增目录

新增：

```text
ui/V2/src/node-ui/
  types.ts
  registry.ts
  resolve.ts
  controls/
    FallbackValueControl.tsx
    ImageChoiceThreeControl.tsx
    ImageCandidatesControl.tsx
    ApprovalControl.tsx
    SchemaFormControl.tsx
  fixtures/
    imageChoiceThree.ts
  ControlLibraryPage.tsx
```

### 7.2 类型

更新 `ui/V2/src/api/types.ts`：

```ts
export type NodeUiControlMode = "readonly" | "interactive" | "input";

export interface NodeUiControlConfig {
  control_id: string;
  variant?: string;
  mode?: NodeUiControlMode;
  bindings?: Record<string, string>;
  options?: Record<string, unknown>;
}

export interface NodeUiConfig {
  controls?: {
    input?: NodeUiControlConfig;
    output?: NodeUiControlConfig;
    interaction?: NodeUiControlConfig;
    detail?: NodeUiControlConfig;
  };
}

export interface UiControlDescriptor {
  control_id: string;
  version: string;
  name: string;
  kind: string;
  tags: string[];
  variants: Array<{
    name: string;
    label: string;
    tags: string[];
    modes: string[];
    required_bindings: unknown[];
    submit_schema?: Record<string, unknown>;
  }>;
  description?: string;
}
```

### 7.3 注册表

`registry.ts`：

```ts
export const nodeUiRegistry = {
  "ui.display.value.v1": FallbackValueControl,
  "ui.display.image_candidates.v1": ImageCandidatesControl,
  "ui.choice.image_three.v1": ImageChoiceThreeControl,
  "ui.interaction.approval.v1": ApprovalControl,
  "ui.fallback.schema_form.v1": SchemaFormControl,
} satisfies Record<string, NodeUiComponent>;
```

`resolve.ts`：

- 解析 `nodes[].ui`。
- 解析 task snapshot 中 workflow UI。
- 找不到控件时返回 fallback。
- binding 读取支持输入、输出、metadata 和上游输出 snapshot。

## 阶段 8：V2 三选一控件

### 8.1 ImageChoiceThreeControl

支持变体：

- `equal_grid`：三张图等宽。
- `hero_list`：首图大，其他候选纵向或横向列表。
- `hover_focus`：鼠标悬停图片放大，其他候选缩小；移动端用点击选中后的视觉强调替代 hover。

交互规则：

- 只提交节点 outputs schema 需要的字段。
- 如果候选项有 `id`、`image_url`、`asset_id`，提交 `selected_id`、`selected_item`、`selected_image_url`。
- loading、提交失败、已选择状态必须清晰。
- 不在控件里写工作流专属文案。

### 8.2 测试

新增 `ui/V2/src/tests/node-ui.test.tsx`：

- 三个变体都能渲染三张图。
- 点击候选项后提交正确 payload。
- hover 变体不会改变布局尺寸导致文本和图片重叠。
- 未知控件使用 fallback。

运行：

```powershell
cd ui/V2
npm test -- node-ui
```

## 阶段 9：V2 任务详情接入控件库

### 9.1 修改节点执行卡片

修改 `ui/V2/src/app/App.tsx` 或拆出组件：

- `NodeExecutionCard` 不再直接决定所有输入输出展示。
- 根据 task snapshot 中节点 UI 配置选择控件。
- 没有 UI 配置时继续使用当前 `ValuePanel` fallback。
- waiting 节点优先渲染 `controls.interaction`。

### 9.2 兼容现有测试

现有测试要求不展示原始 `input_schema`、`output_snapshot`、`public_url` 等内部字段。接入控件库后继续保持。

运行：

```powershell
cd ui/V2
npm test -- app
```

## 阶段 10：V2 控件库浏览页签

### 10.1 导航

修改 `ui/V2/src/app/App.tsx`：

- Route 增加 `"controls"`。
- 顶部导航增加“控件库”页签。
- 页面加载 `/api/ui/node-controls`。

### 10.2 页面能力

`ControlLibraryPage` 显示：

- 控件名称、`control_id`、kind、tags。
- 变体列表和支持 mode。
- binding 要求。
- payload 要求。
- 本地 preview fixture，例如三图等宽、首图大列表、hover 放大。

页面只面向开发者和工作流作者，不暴露后端原始任务 JSON。

### 10.3 浏览器验证

启动 V2 后，用 in-app browser 验证：

- 顶部导航能进入“控件库”。
- 三选一控件三个变体预览正常。
- 任务详情 waiting 节点能显示三选一控件。
- hover 变体桌面端放大行为正常，移动端无布局重叠。

## 阶段 11：示例工作流和文档回填

### 11.1 工作流示例

为图片候选选择场景补示例工作流。默认使用拆分节点：

```yaml
workflow:
  id: image_three_choice_demo
  name: 图片三选一示例
  ui:
    defaults:
      system.user_choice.v1:
        controls:
          interaction:
            control_id: ui.choice.image_three.v1
            variant: hover_focus
            mode: interactive
            bindings:
              items_path: $node.input.candidates
              image_url_path: image_url
              value_path: id
nodes:
  - id: generate_images
    ref: ai.runninghub_text_to_image.v1
    ...
  - id: choose_image
    ref: system.user_choice.v1
    inputs:
      candidates: $nodes.generate_images.output.results
    outputs:
      type: object
      required: [selected_id, selected_item]
      properties:
        selected_id:
          type: string
        selected_item:
          type: object
```

如果要演示高级单节点模式，单独放一个测试 fixture，不作为普通工作流默认样板。

### 11.2 文档

确认以下文档保持同步：

- `docs/design/2026-05-27-01-ui-control-manifest-design.md`
- `workflows/AGENTS.md`
- `xiagent/nodes/AGENTS.md`
- `.codex/skills/xiagent-workflow-authoring/SKILL.md`
- `.codex/skills/xiagent-node-authoring/SKILL.md`
- `ui/V2/docs/ui-development-rules.md`

## 总体验证命令

后端：

```powershell
python -m pytest tests/test_ui_control_catalog.py tests/test_node_registry.py tests/test_workflow_validator.py tests/test_runtime_service.py tests/test_api_ui_controls.py
```

前端：

```powershell
cd ui/V2
npm test
npm run build
```

浏览器：

- 打开 V2 本地地址。
- 登录并进入任务详情。
- 验证可复用三选一节点的 waiting 交互。
- 验证“控件库”页签。
- 验证 hover 放大变体在桌面端和移动端都无重叠。

## 完成标准

- 后端 Manifest 和 API 不引用 V2 React 实现。
- 工作流 UI 配置有硬性校验，错误码稳定。
- 节点默认 UI 只作为保底，不覆盖工作流显式配置。
- 三选一默认由独立交互节点复用。
- 高级单节点模式有测试覆盖，但不成为普通工作流默认建模方式。
- V2 任务详情通过控件库渲染输入、输出和等待交互。
- 顶部导航包含“控件库”页签，可查看当前可用控件和变体。
