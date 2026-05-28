---
name: xiagent-ui-control-library-authoring
description: Use when adding, modifying, registering, validating, or documenting XiAgent UI node/control libraries across ui/V1, ui/V2, or future ui/V3/V4 versions, including backend UI control manifests, workflow/node UI config, React control registries, previews, fixtures, and version-specific AGENTS rules.
---

# XiAgent UI 控件库编写

## Overview

增改 XiAgent UI 控件库时，把“后端可验证契约”和“具体 UI 版本实现”分开处理。后端 manifest、工作流契约和节点默认 UI 是所有 UI 版本共享的边界；V2、V3、V4 等目录只负责把这些稳定控件契约适配为本版本的真实界面。

## Start Here

1. 先确定目标 UI 版本，例如 `ui/V2`。如果用户没有指定，读取 `ui/*`、当前 diff 和相关任务上下文；仍无法判断时再询问。
2. 必读根目录 `AGENTS.md`、`.codex/skills/xiagent-ui-development/SKILL.md`、目标版本的 `ui/<version>/AGENTS.md` 和 `ui/<version>/docs/ui-development-rules.md`。
3. 涉及工作流配置时读 `workflows/AGENTS.md`；涉及 `NodeDescriptor.ui_defaults` 时读 `xiagent/nodes/AGENTS.md`。
4. 涉及后端控件契约时读 `docs/design/2026-05-27-01-ui-control-manifest-design.md`、`xiagent/ui_controls/`、`tests/test_ui_control_catalog.py`、`tests/test_workflow_validator.py`。
5. 如果历史设计文档、目标 UI 目录规则和当前实现不一致，以当前后端 manifest、目标 UI 目录 AGENTS 和可运行测试为准，并同步修正对应文档。

## Ownership Boundary

| 内容 | 放置位置 | 约束 |
| --- | --- | --- |
| 控件 ID、版本、kind、tags、variant、mode、binding、submit payload | `xiagent/ui_controls/` | 所有 UI 版本共享，不依赖 React、Vite 或某个 UI 目录。 |
| 工作流里的控件选择 | `workflows/**/*.workflow.yaml` 的 `workflow.ui` 或 `nodes[].ui` | 只能引用 manifest 中存在的 `control_id`、`variant`、`mode` 和 `bindings`。 |
| 节点通用默认展示 | `NodeDescriptor.ui_defaults` | 只做保底建议，不写死某个工作流或 UI 版本体验。 |
| UI 版本控件实现 | `ui/<version>/src/node-ui/` 或该版本 AGENTS 指定的等价目录 | 只实现渲染、交互、预览和版本本地 fallback。 |
| UI 版本专属视觉、布局、命令和例外 | `ui/<version>/AGENTS.md`、`ui/<version>/docs/ui-development-rules.md` | 不写入通用 skill。 |

不要把后端 manifest 写成前端组件注册表，也不要让前端组件发明后端无法校验的 payload。

## Shared Control Contract

- `control_id` 全局唯一，使用 `ui.<category>.<name>.vN`，例如 `ui.choice.image_three.v1`。
- `kind` 表示用途，优先使用 `input`、`output`、`interaction`、`detail`。
- `variant` 是同一控件能力下的展示变体；如果工作流或节点配置要引用某个变体，必须先在后端 manifest 注册。
- `mode` 必须属于该 variant 支持的模式，常见值是 `readonly`、`interactive`、`input`。
- `bindings` 必须能从 schema 或运行时快照稳定解析，不要绑定临时内部字段。
- 交互控件的 `submit_schema` 必须能被节点 `outputs` 接受；UI 提交内容不得绕过运行时输出校验。
- 控件解析优先级是 `nodes[].ui` > `workflow.ui.defaults` > `NodeDescriptor.ui_defaults` > 系统 fallback。
- 工作流只覆盖某个 slot 时，不应清空其他 slot 的默认配置。常见 slot 是 `input`、`output`、`interaction`、`detail`。

支持的通用 binding 路径：

```text
$workflow.input.<field>
$node.input.<field>
$node.output.<field>
$node.metadata.<field>
$nodes.<node_id>.output.<field>
```

## Implementation Workflow

1. 判断需求属于新控件、新 variant、现有控件修复、版本本地展示修复，还是工作流/节点配置修复。
2. 如果工作流或节点需要引用新的 `control_id`、`variant`、`mode` 或 binding 语义，先更新后端 manifest 和后端验证测试，再做 UI 版本实现。
3. 如果只是目标 UI 版本的视觉或交互 bug，保持后端 manifest 不变，只改目标版本控件实现和版本规则文档。
4. 在目标 UI 版本中通过本地控件注册表解析控件，不在页面代码里为某个工作流硬编码可复用展示。
5. 控件 props 应围绕稳定任务节点快照、工作流节点 spec、workflow snapshot、slot、config、value、busy、preview 和 `onSubmit` 一类输入设计；不要让控件直接读取 SQLite、资产路径、节点类或后端内部实现。
6. 新增控件时同时补：注册表映射、控件组件、必要 fixture、控件库预览页展示、渲染测试、提交 payload 测试、fallback 行为。
7. 修改已有控件时保留旧任务 snapshot 的兼容性；需要破坏性变更时新增 `vN+1` 控件 ID，不复用旧 ID 改语义。

## UI Version Rules

- 每个维护中的 UI 版本都应有自己的 `ui/<version>/AGENTS.md`。先读它，再决定目录、样式、测试命令和已注册控件的版本本地做法。
- UI 版本实现只能消费 `/api/ui/node-controls` 暴露的控件元数据和任务/工作流 API 返回的 snapshot/config；不要 import 后端 Python 代码。
- 可见 UI 不展示 `input_schema`、`output_snapshot`、`public_url`、节点 ref、原始 JSON 或内部 binding，除非用户明确要求开发者调试视图。
- 控件库页面面向开发者和工作流作者，用于发现控件 ID、variant、mode、binding 要求、标签和预览；它不是普通用户配置工作流的低代码编辑器。
- 缺失或未知控件应走版本本地 fallback，并给开发者可读提示；普通用户主流程不应因此暴露原始数据结构。

## Documentation Updates

- 通用控件边界变化：更新本 skill。
- 目标 UI 版本目录、视觉、控件注册表、命令或例外变化：更新 `ui/<version>/AGENTS.md` 和该版本 `docs/ui-development-rules.md`。
- 后端 manifest、验证错误语义或 API 变化：更新 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 或相关架构/设计文档。
- 工作流控件配置规则变化：更新 `workflows/AGENTS.md`。
- 节点 `ui_defaults` 规则变化：更新 `xiagent/nodes/AGENTS.md`。

## Verification

- 后端 manifest 或校验变更：运行 `python -m pytest tests/test_ui_control_catalog.py tests/test_workflow_validator.py tests/test_node_registry.py -q`，并补充相关 API 测试。
- 工作流配置变更：运行 `python -m xiagent.workflows.testing_cli <workflow-path> --input '<json>'` 或 `WorkflowTestBuilder`。
- UI 版本控件变更：运行目标版本 AGENTS 中列出的测试、构建和浏览器验证命令。
- 涉及人工交互控件时，至少验证等待态渲染、提交 payload、busy/disabled 状态、错误态和刷新后的任务详情。

## Common Mistakes

- 只在 React 注册一个控件，却没有在后端 manifest 注册，导致工作流无法校验。
- 在工作流里临时写不存在的 `control_id`、variant 或 binding 名称。
- 为某个工作流把渲染逻辑写进页面，而不是进入控件注册表。
- 让 `NodeDescriptor.ui_defaults` 表达具体工作流体验，而不是通用保底展示。
- 为了控件方便改节点输出字段，破坏下游工作流路径引用。
- 修改 V2 控件库后没有同步 `ui/V2/AGENTS.md` 或 `ui/V2/docs/ui-development-rules.md`。
