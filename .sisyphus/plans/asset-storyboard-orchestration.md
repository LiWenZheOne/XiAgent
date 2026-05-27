# 资产提取→分镜总工作流计划

## TL;DR

> **Quick Summary**: 新增全局编排工作流 `asset_storyboard_generation`，将资产提取管道与分镜生成管道串联为单次任务，通过 `$nodes.xxx.output` 全链路内存传递数据，消除文件/历史任务中间传递。
>
> **Deliverables**:
> - 1 个新工作流 YAML：`workflows/global/asset_storyboard_generation.workflow.yaml`
> - 3 个新节点：`ai.assign_assets_to_segments.v1`、`tool.assemble_storyboard_context.v1`、`tool.extract_panel_image_urls.v1`
> - 改造 2 个现有节点输出（`.v2` 新增）：`generate_prompt`→`generate_image` 和 `upload_images` 统一为同构资产结果
> - 完整 TDD 测试套件：契约测试 + schema 测试 + 两条路径的端到端测试
>
> **Estimated Effort**: Large（~26 节点工作流 + 3 新节点 + 改造 2 末端节点 + 场景/道具并行管道 + 全链路测试）
> **Parallel Execution**: YES — Waves 1-4 可高度并行，角色/场景/道具三段提取并行
> **Critical Path**: 统一资产 schema 定义 → 新节点实现 → YAML 组装 → Fork 端点改造 → 场景/道具管道 → 端到端测试
> **Update Notes**: 追加 Wave 2.5（场景/道具管道），移除 negative_prompt

---

## Context

### Original Request
用户已有详细计划文档，要求新增全局编排工作流将资产提取（`asset_catalog`）与分镜生成（`storyboard_generation`）串联为单次任务，避免文件传递。

### Interview Summary

**Key Discussions**:
- **分叉统一策略**：改造两个末端节点（`generate_prompt`+`generate_image` 和 `upload_images`），使其输出同构的 `AssetImageResult[]` 结构
- **上下文组装**：新增专用工具 `tool.assemble_storyboard_context.v1`，接收段落在场资产数据（含 image_url），不修改现有 `assemble_segment_context`
- **资产链路复用**：7 个资产提取节点基本照搬，prompt 通过 workflow YAML 模板覆盖微调，不创建新节点版本
- **审核 schema**：3 个人工审核节点全部使用严格 schema（`additionalProperties: false`），定义完整的 required 字段
- **storyboard_target**：input_schema 增加可选参数，默认 `segment_index=0, panel_index=0`，预留扩展
- **测试策略**：TDD — 先写测试再实现，使用 FakeRouter + WorkflowTestBuilder 模式

**Research Findings**:
- 现有 13 个注册节点（system/ai/tool）— 新节点需在 `build_node_registry()` 注册
- `generate_image` 当前只处理第一个角色（`.prompt_results.0.prompt`）— 编排工作流需处理所有角色
- 无现有 `assign_assets_to_segments` 逻辑 — 全新建造
- `EnrichCharactersNode` 使用 4 级标签层级（角色/名称/变体/配件）— 可作为段落在场分配的输入基础
- 条件分支验证器支持 `$nodes.*` 路径引用 — 可用于 fork 汇合设计
- 测试注入点统一为 `monkeypatch.setattr("xiagent.workflows.testing.builder.build_node_registry", ...)`

### Metis Review

**Auto-Resolved（已合并入计划）**:
| 问题 | 解决方案 |
|------|---------|
| Fork-merge 输出 schema 未定义 | 定义了统一的 `AssetImageResult` 结构（见下方 schema 设计） |
| `assign_assets_to_segments` 分类 | 重新分类为 `ai.assign_assets_to_segments.v1`（调用 LLM），非 `tool.*` |
| `collect_assets` 替代 | `tool.extract_panel_image_urls.v1` 自动从段落在场资产中提取 image_urls |
| 最终输出 schema | 以 `review_storyboard_image` 输出为基础，含 `decision`、`selected_image_url`、`revision_notes` |
| YAML 行数风险 | 使用分阶段注释（`# ===== P1: xxx =====`）组织 800+ 行 YAML |

**Guardrails from Metis**:
- ⛔ 不修改现有节点代码 — 如需改动，创建 `.v2` 新 ref
- ⛔ V1 只处理 `storyboard_target` 默认值（segment 0, panel 0）
- ⛔ 不添加循环重试机制 — 任何节点失败 = 工作流失败
- ⛔ 所有新节点输出 schema 使用 `additionalProperties: false`
- ⛔ 不在本轮修复现有两个独立工作流

---

## Work Objectives

### Core Objective
新增全局工作流 `asset_storyboard_generation`（~20 节点），串联资产提取全链路与分镜生成全链路，实现"剧本输入→分镜图像输出"的一次性任务执行。

### Concrete Deliverables
- `workflows/global/asset_storyboard_generation.workflow.yaml`（~800 行）
- `xiagent/nodes/ai/assign_assets_to_segments.py` — 新 AI 节点
- `xiagent/nodes/tools/assemble_storyboard_context.py` — 新工具节点
- `xiagent/nodes/tools/extract_panel_image_urls.py` — 新工具节点
- `xiagent/nodes/ai/runninghub_image.py` — 扩展 `RunningHubImageToImageNode` 为 `.v2`
- `xiagent/nodes/tools/storyboard_prompt.py` — 扩展 `StoryboardPromptAssemblerNode` 为 `.v2`
- `tests/test_asset_storyboard_orchestration.py` — 完整 TDD 测试套件

### Definition of Done
- [ ] `python -m pytest tests/test_asset_storyboard_orchestration.py -q -v` → 全部通过
- [ ] `python -m xiagent.workflows.testing_cli workflows/global/asset_storyboard_generation.workflow.yaml --input '{"script":"林冲踏雪而来。","background":"水浒传"}'` → task.status=succeeded，输出含 `selected_image_url`
- [ ] 工作流通过 `validate_workflow_contract()` 校验

### Must Have
- 资产管道（7 节点）+ 分镜管道（8 节点）全链路串联
- 自动生成和手动上传两条路径均可达 END
- 3 个人工审核节点均使用严格 schema
- `storyboard_target` 可选参数，默认 segment=0, panel=0
- 新节点全部在 `build_node_registry()` 注册

### Must NOT Have (Guardrails)
- 不修改现有 `asset_catalog` 或 `storyboard_generation` YAML/节点代码
- 不实现子工作流调用机制
- 不通过本地 JSON 文件传递资产列表
- 不实现循环式"生成-审核-重试"
- 不处理 segment 0 / panel 0 以外的分镜（V1 硬约束）
- 不在本次改造测试基础设施（仅新增测试文件）

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES（pytest + asyncio_mode=auto + WorkflowTestBuilder）
- **Automated tests**: TDD
- **Framework**: pytest + pytest-asyncio
- **Pattern**: FakeRouter + WorkflowTestBuilder + WorkflowTestRunner + monkeypatch 注入

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend/API**: Bash (curl) — 发送请求，验证 status + response fields
- **Workflow/CLI**: Bash (python -m xiagent.workflows.testing_cli) — 执行工作流，验证输出
- **Unit/Contract**: Bash (pytest) — 运行测试，验证 pass/fail

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1（立即开始 — 基础 + 契约）:
├── Task 1: 统一资产结果 schema 定义 [quick]
├── Task 2: 新工作流 YAML 草稿（手动上传路径，含角色提取） [deep]
├── Task 3: 契约测试编写 [quick]
└── Task 4: 测试 FakeRouter 准备 [quick]

Wave 2（Wave 1 后 — 新节点实现 + 场景/道具管道，MAX PARALLEL）:
├── Task 5: ai.assign_assets_to_segments.v1 实现 [deep]
├── Task 6: tool.assemble_storyboard_context.v1 实现 [quick]
├── Task 7: tool.extract_panel_image_urls.v1 实现 [quick]
├── Task 8: StoryboardPromptAssemblerNode.v2 改造 [quick]
├── Task 16: 场景提取管道（YAML 节点 + prompt） [quick]
└── Task 17: 道具提取管道（YAML 节点 + prompt） [quick]

Wave 3（Wave 2 后 — 末端节点改造 + 注册 + YAML 补全）:
├── Task 9: RunningHubImageToImageNode.v2 改造 + generate_prompt 输出统一 [deep]
├── Task 10: upload_images 输出统一适配 [quick]
├── Task 11: 节点注册（build_node_registry） [quick]
└── Task 12: 总工作流 YAML 补全（自动生成路径 + 审核节点 + 三类资产并行拓扑） [deep]

Wave 4（Wave 3 后 — 集成测试）:
├── Task 13: 手动上传路径 e2e 测试 [deep]
├── Task 14: 自动生成路径 e2e 测试 [deep]
├── Task 15: schema 测试 + 边界测试 [quick]
├── Task 18: 场景管道测试 [quick]
└── Task 19: 道具管道测试 [quick]

Wave FINAL（全部实现后）:
├── Task F1: 计划合规审计 (oracle)
├── Task F2: 代码质量审查 (unspecified-high)
├── Task F3: 实际 QA 执行 (unspecified-high)
└── Task F4: 范围忠实度检查 (deep)
→ 展示结果 → 等待用户确认

Critical Path: Task 1 → Task 2 → Task 5 → Task 9 → Task 12 → Task 13 → F1-F4 → 用户确认
Parallel Speedup: ~70% faster than sequential（三段资产提取并行）
Max Concurrent: 6 (Wave 2)
```

### Agent Dispatch Summary

- **Wave 1**: 4 tasks — T1→quick, T2→deep, T3→quick, T4→quick
- **Wave 2**: 6 tasks — T5→deep, T6→quick, T7→quick, T8→quick, T16→quick, T17→quick
- **Wave 3**: 4 tasks — T9→deep, T10→quick, T11→quick, T12→deep
- **Wave 4**: 5 tasks — T13→deep, T14→deep, T15→quick, T18→quick, T19→quick
- **FINAL**: 4 tasks — F1→oracle, F2→unspecified-high, F3→unspecified-high, F4→deep

---

## TODOs

- [x] 1. 统一资产结果 schema 定义

  **What to do**:
  - 在 `xiagent/core/schemas.py` 或新文件 `xiagent/workflows/schemas/asset_image_result.py` 中定义 `AssetImageResult` JSON Schema
  - Schema 必须同时兼容自动生成路径（RunningHub 输出）和手动上传路径（human_approval 输出）
  - 结构设计：
    ```yaml
    type: object
    required: ["full_name", "image_url", "source"]
    properties:
      full_name: {type: string, minLength: 1}
      image_url: {type: string, minLength: 1}
      variant: {type: string}
      asset_id: {type: string}
      source: {type: string, enum: ["ai_generated", "manual_upload"]}
      runninghub_task_id: {type: string}
    additionalProperties: false
    ```
  - 定义 `AssetImageResultList` schema（`AssetImageResult` 数组包装）供节点输出使用

  **Must NOT do**:
  - 不要在 schema 中包含 `additionalProperties: true`
  - 不要为两种路径定义不同 schema — 必须同构

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯 schema 定义，无复杂逻辑
  - **Skills**: `[]`
    - 无外部依赖，纯 Python 类型定义

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 2, 3, 4）
  - **Blocks**: Tasks 5, 9, 10
  - **Blocked By**: None

  **References**:
  - `xiagent/core/schemas.py` — 现有 JSON Schema 工具函数（`validate_json_value`, `validate_json_schema`）
  - `xiagent/nodes/ai/runninghub_image.py:30-60` — RunningHubImageToImageNode 输出 schema 参考
  - `workflows/global/asset_catalog.workflow.yaml:602-645` — upload_images 输出 schema 参考
  - `workflows/global/asset_catalog.workflow.yaml:560-600` — generate_image 输出 schema 参考

  **Acceptance Criteria**:

  **QA Scenarios**:

  ```
  Scenario: Schema 验证 — AI 生成路径输出通过校验
    Tool: Bash (pytest)
    Preconditions: AssetImageResult schema 已定义，validate_json_value 可用
    Steps:
      1. 构造 AI 生成路径的示例输出：{full_name: "林冲", image_url: "https://cdn.test/img.png", source: "ai_generated"}
      2. 调用 validate_json_value(ASSET_IMAGE_RESULT_SCHEMA, example_output)
      3. 验证不抛出 ValidationError
    Expected Result: 校验通过，无异常
    Failure Indicators: ValidationError 被抛出
    Evidence: .sisyphus/evidence/task-1-schema-ai-generated.txt

  Scenario: Schema 验证 — 手动上传路径输出通过校验
    Tool: Bash (pytest)
    Preconditions: AssetImageResult schema 已定义
    Steps:
      1. 构造手动上传路径的示例输出：{full_name: "武松", image_url: "https://user-upload.test/ws.png", source: "manual_upload"}
      2. 调用 validate_json_value(ASSET_IMAGE_RESULT_SCHEMA, example_output)
      3. 验证不抛出 ValidationError
    Expected Result: 校验通过
    Evidence: .sisyphus/evidence/task-1-schema-manual-upload.txt

  Scenario: Schema 拒绝不合规输出
    Tool: Bash (pytest)
    Preconditions: AssetImageResult schema 已定义
    Steps:
      1. 构造缺少 required 字段的输出：{full_name: "林冲"}（缺少 image_url, source）
      2. 调用 validate_json_value(ASSET_IMAGE_RESULT_SCHEMA, bad_output)
      3. 验证抛出 ValidationError
    Expected Result: ValidationError 被抛出
    Evidence: .sisyphus/evidence/task-1-schema-reject-invalid.txt
  ```

  **Commit**: YES（groups with Task 2）
  - Message: `feat(orchestration): define unified AssetImageResult schema`
  - Files: `xiagent/core/schemas.py` 或新增 schema 文件

- [x] 2. 新工作流 YAML 草稿（手动上传路径）

  **What to do**:
  - 创建 `workflows/global/asset_storyboard_generation.workflow.yaml`
  - 阶段 A（资产提取）：从 `asset_catalog` 照搬 7 个节点（extract_characters → lookup_existing_assets → match_by_name → semantic_match_characters → enrich_characters → match_variants → check_accessories），`system`/`prompt` 模板可微调
  - 阶段 B（资产审核）：`review_assets`（system.human_approval.v1），严格 schema 含 `decision`、`approved_assets`、`image_urls`
  - 阶段 C（手动上传）：`upload_images`（system.human_approval.v1），输出强制为 `AssetImageResult[]`
  - 阶段 D（剧本分段 + 在场分配）：`split_script` → `assign_assets_to_segments` → `assemble_storyboard_context`
  - 阶段 E（分镜描述 + 提示词审核）：`describe_panels` → `review_storyboard_prompt`
  - 阶段 F（提取图像 URL + 组装 prompt）：`extract_panel_image_urls` → `assemble_prompt_v2`
  - 阶段 G（生成图像 + 审查）：`generate_image_v2` → `review_storyboard_image`
  - Input schema：
    ```yaml
    type: object
    required: ["script", "background"]
    properties:
      script: {type: string, minLength: 1}
      background: {type: string, minLength: 1}
      generate_assets: {type: string, enum: ["手动上传", "自动生成"]}
      template_image_url: {type: string}
      storyboard_target:
        type: object
        default: {segment_index: 0, panel_index: 0}
        properties:
          segment_index: {type: integer, minimum: 0, default: 0}
          panel_index: {type: integer, minimum: 0, default: 0}
    additionalProperties: false
    ```
  - 所有 Edges 先按手动上传路径（无分叉）直连

  **Must NOT do**:
  - 不包含自动生成路径的 conditional edge
  - 不修改现有 asset_catalog 或 storyboard_generation YAML
  - 不要遗漏任何节点的 `outputs` schema 定义

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解全链路数据流和节点间依赖关系
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 1, 3, 4）
  - **Blocks**: Tasks 5, 9, 10, 12
  - **Blocked By**: None（但依赖 Task 1 的 schema 决策）

  **References**:
  - `workflows/global/asset_catalog.workflow.yaml:1-274` — 资产提取阶段 A 的完整节点定义（节点 1-7）
  - `workflows/global/storyboard_generation.workflow.yaml:1-65` — split_script + describe_panels 节点定义
  - `workflows/global/asset_catalog.workflow.yaml:440-491` — review_assets human_approval 模板参考
  - `workflows/global/storyboard_generation.workflow.yaml:329-360` — collect_assets 模板参考（将被 extract_panel_image_urls 替代）
  - `workflows/global/asset_catalog.workflow.yaml:647-675` — 条件分叉 edge 语法参考
  - `docs/design/2026-05-19-04-workflow-contract-design.md` — 工作流契约格式规范

  **Acceptance Criteria**:
  - [ ] YAML 文件可被 `load_workflow_file()` 成功解析
  - [ ] `validate_workflow_contract()` 对注册节点校验通过
  - [ ] Input schema 包含 script, background 为 required
  - [ ] storyboard_target 为 optional，有默认值

  **QA Scenarios**:

  ```
  Scenario: YAML 加载 + 结构校验
    Tool: Bash (pytest)
    Preconditions: YAML 文件已创建
    Steps:
      1. from xiagent.workflows.loader import load_workflow_file
      2. contract = load_workflow_file(Path("workflows/global/asset_storyboard_generation.workflow.yaml"))
      3. 验证 contract["workflow"]["id"] == "asset_storyboard_generation"
      4. 验证 contract["workflow"]["scope"] == "global"
      5. 验证 input_schema.required 包含 ["script", "background"]
    Expected Result: 所有断言通过
    Failure Indicators: YAML 解析错误、required 字段缺失
    Evidence: .sisyphus/evidence/task-2-yaml-structure.txt

  Scenario: 节点完整性校验
    Tool: Bash (pytest)
    Preconditions: YAML 已加载
    Steps:
      1. nodes_by_id = {node["id"]: node for node in contract["nodes"]}
      2. 验证资产提取阶段节点全部存在（extract_characters, lookup_existing_assets, match_by_name, semantic_match_characters, enrich_characters, match_variants, check_accessories）
      3. 验证分镜阶段节点全部存在（split_script, assign_assets_to_segments, assemble_storyboard_context, describe_panels, review_storyboard_prompt, extract_panel_image_urls, assemble_prompt_v2, generate_image_v2, review_storyboard_image）
      4. 每个节点的 ref 在 NodeRegistry 可查到
    Expected Result: 所有节点存在且 ref 可解析
    Evidence: .sisyphus/evidence/task-2-nodes-complete.txt
  ```

  **Commit**: YES（groups with Task 1）
  - Message: `feat(orchestration): add asset_storyboard_generation workflow skeleton (manual path)`
  - Files: `workflows/global/asset_storyboard_generation.workflow.yaml`

- [x] 3. 契约测试编写（TDD — RED）

  **What to do**:
  - 创建 `tests/test_asset_storyboard_orchestration.py`
  - 编写以下契约测试（初始状态全部 FAIL — TDD RED 阶段）：
    - `test_orchestration_workflow_contract_structure`: 验证 workflow id/version/scope/input_schema
    - `test_orchestration_workflow_node_list`: 验证所有节点的 id 和 ref 完整
    - `test_orchestration_workflow_edges_are_dag`: 验证 edges 形成合法 DAG
    - `test_orchestration_workflow_manual_path_valid`: 验证 `generate_assets="手动上传"` 时 edges 路径正确
    - `test_orchestration_asset_extract_nodes_match_original`: 验证资产提取 7 节点的 ref 与 asset_catalog 一致
    - `test_orchestration_input_schema_storyboard_target_default`: 验证 storyboard_target 可选且有默认值
  - 使用现有的 `load_workflow_file()` + `validate_workflow_contract()` 模式
  - 参考 `test_asset_catalog_workflow.py` 和 `test_storyboard_workflow.py` 的契约测试写法

  **Must NOT do**:
  - 不要写端到端测试（那是 Wave 4 的任务）
  - 不要创建 FakeRouter（那是 Task 4）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 遵循已有测试模式，纯结构验证
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 1, 2, 4）
  - **Blocks**: Tasks 13, 14, 15
  - **Blocked By**: Task 2（需要 YAML 草稿存在）

  **References**:
  - `tests/test_asset_catalog_workflow.py:30-73` — 契约结构测试模板（test_asset_catalog_workflow_contract_structure）
  - `tests/test_asset_catalog_workflow.py:75-108` — 条件分支测试模板（test_asset_catalog_workflow_has_conditional_edges）
  - `tests/test_storyboard_workflow.py:25-65` — 节点序列 + edges 测试模板
  - `tests/conftest.py` — test_settings fixture

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_asset_storyboard_orchestration.py -q` → 初始状态 6 tests FAIL（RED — 因为 YAML 和新节点尚未完全实现）
  - [ ] 测试文件被 `pyproject.toml` 的 `testpaths = ["tests"]` 覆盖

  **QA Scenarios**:

  ```
  Scenario: 测试框架加载 + 初始 RED 状态
    Tool: Bash (pytest)
    Preconditions: 测试文件已创建，YAML 草稿存在
    Steps:
      1. python -m pytest tests/test_asset_storyboard_orchestration.py -q -v
      2. 验证测试框架正常加载（无 import 错误）
      3. 记录每个测试的 PASS/FAIL 状态
      4. 确认 RED 状态的测试数（预期至少部分 FAIL）
    Expected Result: 测试框架运行，部分测试 FAIL（RED 阶段）
    Failure Indicators: ImportError、pytest 崩溃（非预期）
    Evidence: .sisyphus/evidence/task-3-tdd-red.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): add TDD contract tests (RED phase)`
  - Files: `tests/test_asset_storyboard_orchestration.py`

- [x] 4. 测试 FakeRouter 准备

  **What to do**:
  - 在 `tests/test_asset_storyboard_orchestration.py` 中创建 `FakeOrchestrationRouter(ChatModelRouter)`
  - Pre-program 所有 LLM 调用所需的响应（~8-10 个 DeepSeek 调用）：
    - extract_characters（角色提取）
    - semantic_match_characters（语义匹配）
    - match_variants × N（并行变体匹配）
    - check_accessories × N（并行配件检查）
    - assign_assets_to_segments（段落在场分配）
    - describe_panels（分镜描述）
  - 创建 `_orchestration_registry(router)` 工厂函数注册所有节点
  - 处理 RunningHub image 调用（返回固定测试 URL）
  - 创建 `_long_shuihu_script()` 辅助函数提供测试用剧本

  **Must NOT do**:
  - 不要预先定义 Human Approval 的 canned answers（留给 Task 13/14 的端到端测试）
  - 不要在 FakeRouter 中模拟工作流引擎逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 遵循已有 FakeRouter 模式，纯模板代码
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1（with Tasks 1, 2, 3）
  - **Blocks**: Tasks 13, 14
  - **Blocked By**: Task 1（需要了解 AssetImageResult schema 以构造响应）

  **References**:
  - `tests/test_asset_catalog_workflow.py:389-452` — FakeAssetCatalogRouter 完整模板
  - `tests/test_storyboard_workflow.py:313-352` — FakeStoryboardRouter 完整模板
  - `tests/test_asset_catalog_workflow.py:454-481` — _asset_catalog_registry 工厂模板
  - `tests/test_asset_catalog_workflow.py:484-518` — _seed_file_asset 数据播种模板
  - `xiagent/models/__init__.py` — ChatModelRouter 和 ChatResponse 导入路径

  **Acceptance Criteria**:
  - [ ] FakeOrchestrationRouter 类可实例化
  - [ ] `_orchestration_registry(router)` 返回包含所有所需节点的 NodeRegistry

  **QA Scenarios**:

  ```
  Scenario: FakeRouter 响应队列完整性
    Tool: Bash (pytest)
    Preconditions: FakeOrchestrationRouter 已定义
    Steps:
      1. router = FakeOrchestrationRouter()
      2. 验证 router._deepseek_responses 非空（至少 8 个响应）
      3. router.requests = []（初始状态）
      4. 调用 router.chat() 验证返回 ChatResponse
      5. 验证 router.requests 记录了调用
    Expected Result: FakeRouter 正常工作，响应队列就绪
    Evidence: .sisyphus/evidence/task-4-fake-router-ready.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): prepare FakeOrchestrationRouter and registry factory`
  - Files: `tests/test_asset_storyboard_orchestration.py`

- [ ] 5. ai.assign_assets_to_segments.v1 实现

  **What to do**:
  - 创建 `xiagent/nodes/ai/assign_assets_to_segments.py`
  - 新建 `AssignAssetsToSegmentsNode(BaseNode)`，ref = `ai.assign_assets_to_segments.v1`
  - kind = `"ai"`（调用 LLM，需要 ChatModelRouter 注入）
  - 输入：
    - `segments`：from `$nodes.split_script.output.segments`
    - `characters`：from `$nodes.enrich_characters.output.characters`
    - `variant_results`：from `$nodes.match_variants.output.results`
    - `accessory_results`：from `$nodes.check_accessories.output.results`
    - `asset_images`：from 统一后的 `review_assets.output`（AssetImageResult[]）
  - 使用 `ai.deepseek_structured_json.v1` 类似的 LLM 调用模式
  - System prompt 规则（沿用用户原文）：
    - "仅返回合法 JSON。你是剧本分析师。根据叙事事实判断每个资产是否在段落中在场。"
    - "对话提及、命令、计划、回忆不算在场。"
  - 输出 schema（严格）：
    ```yaml
    type: object
    required: ["segment_asset_assignments"]
    properties:
      segment_asset_assignments:
        type: array
        items:
          type: object
          required: ["index", "location", "time", "present_assets", "absent_assets", "reasoning"]
          properties:
            index: {type: integer, minimum: 0}
            location: {type: string}
            time: {type: string}
            present_assets: {type: array, items: {type: object, required: ["full_name", "confidence", "reason"]}}
            absent_assets: {type: array, items: {type: object, required: ["full_name", "reason"]}}
            reasoning: {type: string, minLength: 1}
    additionalProperties: false
    ```
  - 每个 present_asset 包含 `full_name`、`asset_id`/`matched_asset_id`、`variant`、`image_url`/`storage_uri`、`accessories`、`confidence`、`reason`
  - 在 `xiagent/nodes/__init__.py` 的 `build_node_registry()` 中注册

  **Must NOT do**:
  - 不使用 `tool.*` 前缀 — 此节点调用 LLM，必须是 `ai.*`
  - 不在 prompt 中包含"无法确定"选项 — 必须明确在场/缺席
  - 不包含额外根键（`additionalProperties: false`）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要设计 LLM prompt + 复杂 schema + 理解资产匹配数据流
  - **Skills**: `[]`
    - 不需要特殊技能，遵循现有 DeepSeekStructuredJsonNode 模式

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 6, 7, 8）
  - **Blocks**: Tasks 12, 13, 14
  - **Blocked By**: Task 1（AssetImageResult schema）, Task 2（YAML 草稿）

  **References**:
  - `xiagent/nodes/ai/deepseek_structured_json.py` — AI 节点实现模板（构造器注入 model_router）
  - `xiagent/nodes/ai/parallel_deepseek_structured_json.py` — 并行 LLM 调用模式参考
  - `xiagent/nodes/tools/enrich_characters.py:54-141` — 角色-资产映射逻辑（4 级标签层级）
  - `workflows/global/asset_catalog.workflow.yaml:204-262` — semantic_match_characters prompt 模板参考
  - `xiagent/nodes/__init__.py:72-116` — 节点注册模式

  **Acceptance Criteria**:
  - [ ] NodeDescriptor.ref == "ai.assign_assets_to_segments.v1"
  - [ ] output_schema 中 segment_asset_assignments 为 required
  - [ ] 节点在 NodeRegistry 成功注册
  - [ ] 测试：给定 1 段 3 个角色（2 在场 1 缺席），输出正确分配

  **QA Scenarios**:

  ```
  Scenario: 单段单角色在场分配
    Tool: Bash (pytest)
    Preconditions: FakeRouter 已注入，WorkflowTestRunner 就绪
    Steps:
      1. 构造输入：1 个 segment + 1 个 character（在场）
      2. 调用 AssignAssetsToSegmentsNode.run(ctx, inputs)
      3. 验证 output.segment_asset_assignments[0].present_assets 包含该角色
      4. 验证 present_assets[0].full_name 正确
      5. 验证 present_assets[0].confidence 字段存在
    Expected Result: 角色正确标记为 present_assets
    Failure Indicators: 角色错误出现在 absent_assets、confidence 缺失
    Evidence: .sisyphus/evidence/task-5-single-present.txt

  Scenario: 对话提及角色不算在场
    Tool: Bash (pytest)
    Preconditions: FakeRouter 预编程响应
    Steps:
      1. 构造输入：段落中角色仅在对话中被提及（"林冲说武松已经走了"）
      2. 调用节点
      3. 验证"武松"出现在 absent_assets 中
      4. 验证原因说明中包含"仅在对话中提及"
    Expected Result: 对话提及的角色标记为 absent
    Failure Indicators: 对话提及角色出现在 present_assets
    Evidence: .sisyphus/evidence/task-5-dialog-absent.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `feat(nodes): add ai.assign_assets_to_segments.v1 with segment-level asset assignment`
  - Files: `xiagent/nodes/ai/assign_assets_to_segments.py`, `xiagent/nodes/__init__.py`

- [ ] 6. tool.assemble_storyboard_context.v1 实现

  **What to do**:
  - 创建 `xiagent/nodes/tools/assemble_storyboard_context.py`
  - 新建 `AssembleStoryboardContextNode(BaseNode)`，ref = `tool.assemble_storyboard_context.v1`
  - kind = `"tool"`（纯程序化，不调用 LLM）
  - 输入：
    - `segments`：from `$nodes.split_script.output.segments`
    - `segment_asset_assignments`：from `$nodes.assign_assets_to_segments.output.segment_asset_assignments`
  - 输出：
    - `context_string`：包含段落原文、建议分格数、地点、时间、在场资产（含 full_name、variant、image_url、accessories）
  - 逻辑：遍历每个 segment，从 segment_asset_assignments 提取在场资产信息，格式化为上下文文本
  - 参考 `assemble_segment_context.py` 的格式化逻辑（中日文段落头、角色列表格式）
  - 每个在场资产行格式：`  - {full_name}（变体：{variant}）（参考图：{image_url}）（配件：{accessories}）`
  - 在 `build_node_registry()` 注册

  **Must NOT do**:
  - 不修改现有 `assemble_segment_context.py`
  - 不调用 LLM — 纯字符串拼接
  - 不包含缺席角色信息（absent_assets）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯字符串格式化工具，无外部依赖
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 5, 7, 8）
  - **Blocks**: Task 12
  - **Blocked By**: Task 5（需要知道 segment_asset_assignments 的结构）

  **References**:
  - `xiagent/nodes/tools/assemble_segment_context.py:1-141` — 完整参考实现（格式化逻辑、校验模式）
  - `xiagent/nodes/tools/assemble_segment_context.py:68-130` — run() 方法的格式化逻辑
  - `xiagent/nodes/tools/assemble_segment_context.py:87-118` — 段落上下文格式化代码

  **Acceptance Criteria**:
  - [ ] NodeDescriptor.ref == "tool.assemble_storyboard_context.v1"
  - [ ] context_string 包含段落原文、在场资产名、variant、image_url
  - [ ] 节点在 NodeRegistry 成功注册

  **QA Scenarios**:

  ```
  Scenario: 单段在场资产上下文组装
    Tool: Bash (pytest)
    Preconditions: 节点已注册
    Steps:
      1. 构造 segments（1 段："林冲在山神庙外"）和 segment_asset_assignments（1 个在场角色："林冲" with variant="囚服", image_url="https://cdn.test/lc.png"）
      2. 调用 AssembleStoryboardContextNode.run(ctx, inputs)
      3. 验证 context_string 包含 "段落 0"
      4. 验证 context_string 包含 "林冲"
      5. 验证 context_string 包含 "囚服"
      6. 验证 context_string 包含 "https://cdn.test/lc.png"
      7. 验证 context_string 不包含 absent 角色
    Expected Result: context_string 包含所有在场资产关键信息
    Failure Indicators: 缺失 image_url、包含 absent 角色
    Evidence: .sisyphus/evidence/task-6-context-assembly.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `feat(nodes): add tool.assemble_storyboard_context.v1 with asset-aware context assembly`
  - Files: `xiagent/nodes/tools/assemble_storyboard_context.py`, `xiagent/nodes/__init__.py`

- [ ] 7. tool.extract_panel_image_urls.v1 实现

  **What to do**:
  - 创建 `xiagent/nodes/tools/extract_panel_image_urls.py`
  - 新建 `ExtractPanelImageUrlsNode(BaseNode)`，ref = `tool.extract_panel_image_urls.v1`
  - kind = `"tool"`（纯程序化）
  - 输入：
    - `segment_asset_assignments`：from `$nodes.assign_assets_to_segments.output.segment_asset_assignments`
    - `storyboard_target`：from `$workflow.input.storyboard_target`（默认 segment=0, panel=0）
  - 逻辑：根据 storyboard_target 找到目标段落的 present_assets，提取所有 image_url 为数组
  - 输出：
    ```yaml
    type: object
    required: ["image_urls"]
    properties:
      image_urls: {type: array, minItems: 1, items: {type: string, minLength: 1}}
      target_segment: {type: integer}
      target_panel: {type: integer}
    additionalProperties: false
    ```
  - 此节点替代 storyboard_generation 中的 `collect_assets`（human_approval）节点 — 全自动提取
  - 在 `build_node_registry()` 注册

  **Must NOT do**:
  - 不调用任何外部 API
  - 不做人为判断
  - 如果目标段落无在场资产（present_assets 为空），返回 ValidationError

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯数据提取和数组过滤，无外部依赖
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 5, 6, 8）
  - **Blocks**: Task 12
  - **Blocked By**: Task 5（需要知道 segment_asset_assignments 的结构）

  **References**:
  - `xiagent/nodes/tools/asset_lookup.py` — 工具节点实现模式
  - `workflows/global/storyboard_generation.workflow.yaml:329-360` — collect_assets 被替换节点
  - `workflows/global/storyboard_generation.workflow.yaml:371-396` — assemble_prompt.input.image_urls 消费方（需 image_urls 数组）

  **Acceptance Criteria**:
  - [ ] NodeDescriptor.ref == "tool.extract_panel_image_urls.v1"
  - [ ] 给定 2 个在场资产（各含 image_url），输出 image_urls 数组长度为 2
  - [ ] 目标段落无在场资产时抛出 ValidationError

  **QA Scenarios**:

  ```
  Scenario: 正常提取在场资产 image_urls
    Tool: Bash (pytest)
    Preconditions: 节点已注册
    Steps:
      1. 构造 segment_asset_assignments（segment 0 含 2 个 present_assets，各带 image_url）
      2. storyboard_target = {segment_index: 0, panel_index: 0}
      3. 调用 ExtractPanelImageUrlsNode.run(ctx, inputs)
      4. 验证 output.image_urls 长度为 2
      5. 验证 output.target_segment == 0
    Expected Result: 正确提取 2 个 image URLs
    Evidence: .sisyphus/evidence/task-7-extract-urls.txt

  Scenario: 空在场资产抛出错误
    Tool: Bash (pytest)
    Preconditions: 节点已注册
    Steps:
      1. 构造 segment_asset_assignments（segment 0 的 present_assets 为空数组）
      2. 调用节点
      3. 验证抛出 ValidationError
      4. 验证错误消息包含 "no present assets"
    Expected Result: ValidationError 被抛出
    Evidence: .sisyphus/evidence/task-7-empty-assets-error.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `feat(nodes): add tool.extract_panel_image_urls.v1 for auto-extracting reference image URLs`
  - Files: `xiagent/nodes/tools/extract_panel_image_urls.py`, `xiagent/nodes/__init__.py`

- [ ] 8. StoryboardPromptAssemblerNode.v2 改造

  **What to do**:
  - 在 `xiagent/nodes/tools/storyboard_prompt.py` 中新增 `StoryboardPromptAssemblerNodeV2` 类
  - ref = `tool.storyboard_prompt_assembler.v2`
  - 与 v1 的区别：
    - 新增可选输入 `segment_context`（从 `assemble_storyboard_context` 输出的 context_string）注入 prompt
    - 新增可选输入 `manual_overrides`（从人工审核节点 `review_storyboard_prompt` 的 corrections）
    - 如果 manual_overrides 提供了 `corrected_prompt` 和 `corrected_image_urls`，则使用修正值替代组装值
  - v1 原类保持不变（保留向后兼容）
  - **⚠️ 不输出 `negative_prompt`**（用户确认：生成图像不需要 negative_prompt）
  - 在 `build_node_registry()` 注册 v2（v1 继续注册）
  - prompt 模板增加 "在场资产约束" 部分：
    ```
    在场资产约束
    - 以下资产在当前分格中在场，需严格参考其外观：
    {segment_context}
    ```

  **Must NOT do**:
  - 不删除或修改现有 `StoryboardPromptAssemblerNode`（v1）
  - 不改变 v1 的默认 aspect_ratio（16:9）和 resolution（2K）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 扩展现有节点，增量改动小
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 5, 6, 7）
  - **Blocks**: Task 12
  - **Blocked By**: Task 6（需要 assemble_storyboard_context 输出格式）

  **References**:
  - `xiagent/nodes/tools/storyboard_prompt.py:1-145` — v1 完整实现
  - `xiagent/nodes/tools/storyboard_prompt.py:53-114` — run() 方法和 prompt 组装逻辑
  - `xiagent/nodes/__init__.py:80` — 现有注册位置

  **Acceptance Criteria**:
  - [ ] NodeDescriptor.ref == "tool.storyboard_prompt_assembler.v2"
  - [ ] v1 和 v2 在 NodeRegistry 同时存在且不冲突
  - [ ] manual_overrides 存在时使用修正值
  - [ ] segment_context 注入 prompt

  **QA Scenarios**:

  ```
  Scenario: v2 注入在场资产上下文
    Tool: Bash (pytest)
    Preconditions: v2 节点已注册
    Steps:
      1. 输入：description="A warrior in snow", style="cinematic", constraints="keep consistency", image_urls=["https://cdn.test/ref.png"], segment_context="在场角色：林冲（囚服）"
      2. 调用节点
      3. 验证 output.prompt 包含 "在场资产约束"
      4. 验证 output.prompt 包含 "林冲（囚服）"
      5. 验证 v1 节点不受影响（不包含 segment_context 相关内容）
    Expected Result: v2 prompt 含在场资产信息，v1 不受影响
    Evidence: .sisyphus/evidence/task-8-v2-context-injection.txt

  Scenario: manual_overrides 覆盖自动组装
    Tool: Bash (pytest)
    Preconditions: v2 节点已注册
    Steps:
      1. 输入含 manual_overrides: {corrected_prompt: "修正后的 prompt", corrected_image_urls: ["https://cdn.test/override.png"]}
      2. 调用节点
      3. 验证 output.prompt == "修正后的 prompt"
      4. 验证 output.image_urls == ["https://cdn.test/override.png"]
    Expected Result: 修正值覆盖自动组装
    Evidence: .sisyphus/evidence/task-8-manual-override.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `feat(nodes): add StoryboardPromptAssemblerNode.v2 with segment context and manual overrides`
  - Files: `xiagent/nodes/tools/storyboard_prompt.py`, `xiagent/nodes/__init__.py`

- [ ] 9. RunningHubImageToImageNode.v2 改造 + generate_prompt 输出统一

  **What to do**:
  - 在 `xiagent/nodes/ai/runninghub_image.py` 中新增 `RunningHubImageToImageNodeV2` 类
  - ref = `ai.runninghub_image_to_image.v2`
  - 新特性：批量处理多个角色的 prompt_results（非仅 `.prompt_results.0`）
  - 输入新增 `prompt_results`（`generate_prompt_v2` 的完整输出数组），循环处理每个角色的 prompt + reference_image_url
  - 输出改为统一的 `AssetImageResult[]` 结构：
    ```yaml
    type: object
    required: ["asset_images"]
    properties:
      asset_images:
        type: array
        items:
          type: object
          required: ["full_name", "image_url", "source"]
          properties:
            full_name: {type: string}
            image_url: {type: string}
            variant: {type: string}
            asset_id: {type: string}
            source: {type: string, enum: ["ai_generated"]}
            runninghub_task_id: {type: string}
    additionalProperties: false
    ```
  - 同时调整 `generate_prompt`（workflow YAML 中的 prompt 节点）的 output schema，使其数组结构完整对应每个角色
  - v1 原类保持不变（向后兼容）
  - 在 `build_node_registry()` 注册 v2

  **Must NOT do**:
  - 不删除或修改现有 `RunningHubImageToImageNode`（v1）
  - 不使用 `additionalProperties: true`
  - 不跳过任何角色的图像生成

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解 RunningHub API 调用循环 + 统一输出 schema 改造
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3（with Tasks 10, 11, 12）
  - **Blocks**: Tasks 13, 14
  - **Blocked By**: Task 1（AssetImageResult schema）, Task 5（完成节点结构理解）

  **References**:
  - `xiagent/nodes/ai/runninghub_image.py:1-180` — v1 完整实现（RunningHub 调用逻辑）
  - `xiagent/nodes/ai/runninghub_image.py:30-60` — v1 输出 schema
  - `workflows/global/asset_catalog.workflow.yaml:560-600` — generate_image 节点定义（当前只处理 .prompt_results.0）
  - `workflows/global/asset_catalog.workflow.yaml:494-558` — generate_prompt 节点定义（输出 prompt_results 数组）
  - `xiagent/nodes/__init__.py:102-108` — v1 注册位置

  **Acceptance Criteria**:
  - [ ] NodeDescriptor.ref == "ai.runninghub_image_to_image.v2"
  - [ ] 输入 prompt_results 含 3 个角色 → 调用 RunningHub 3 次 → 输出 asset_images 长度为 3
  - [ ] 每个 asset_image 的 source == "ai_generated"
  - [ ] v1 节点不受影响

  **QA Scenarios**:

  ```
  Scenario: 多角色批量图像生成
    Tool: Bash (pytest)
    Preconditions: FakeRouter 已注入（RunningHub 返回固定测试 URL）
    Steps:
      1. 构造 prompt_results 含 2 个角色（林冲、武松），各含 prompt 和 reference_image_url
      2. 调用 RunningHubImageToImageNodeV2.run(ctx, inputs)
      3. 验证 output.asset_images 长度为 2
      4. 验证 asset_images[0].full_name == "林冲", source == "ai_generated"
      5. 验证 asset_images[1].full_name == "武松"
      6. 验证 router.requests 记录了 2 次 RunningHub 调用
    Expected Result: 2 个角色各生成图像，输出统一 AssetImageResult 结构
    Failure Indicators: 只生成 1 张图、source 字段缺失、v1 节点受影响
    Evidence: .sisyphus/evidence/task-9-multi-character-gen.txt

  Scenario: RunningHub 超时处理
    Tool: Bash (pytest)
    Preconditions: FakeRouter 模拟超时
    Steps:
      1. 构造 FakeRouter 在第二次调用时 raise TimeoutError
      2. 调用节点
      3. 验证返回 status == "failed"
      4. 验证 error 信息包含 "timeout"
    Expected Result: 超时后节点返回 failed，不会 infinite wait
    Evidence: .sisyphus/evidence/task-9-timeout.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `feat(nodes): add RunningHubImageToImageNode.v2 with batch processing and unified AssetImageResult output`
  - Files: `xiagent/nodes/ai/runninghub_image.py`, `xiagent/nodes/__init__.py`

- [ ] 10. upload_images 输出统一适配

  **What to do**:
  - 在总工作流 YAML 中，将 `upload_images`（system.human_approval.v1）的 output_schema 改为严格的 `AssetImageResult[]` 结构
  - 人工审核 prompt 中明确要求输出格式：
    ```
    请为每个角色提供图像 URL。输出格式（严格 JSON）：
    {
      "asset_images": [
        {"full_name": "林冲", "image_url": "https://...", "source": "manual_upload", "variant": "囚服"},
        ...
      ]
    }
    ```
  - 确保 `additionalProperties: false`
  - 消费方（assign_assets_to_segments）统一从 `asset_images` 字段读取，无论来自哪条路径

  **Must NOT do**:
  - 不创建新的节点类 — 复用 `system.human_approval.v1`
  - 不修改 HumanApprovalNode 代码 — 仅通过 YAML schema 约束

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: YAML schema 修改 + prompt 调整，无代码改动
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3（with Tasks 9, 11, 12）
  - **Blocks**: Tasks 13, 14
  - **Blocked By**: Task 1（AssetImageResult schema）

  **References**:
  - `workflows/global/asset_catalog.workflow.yaml:602-645` — upload_images 节点定义（需改造 output schema）
  - `workflows/global/asset_catalog.workflow.yaml:633-645` — 当前 output schema（`additionalProperties: true` — 需改为 strict）

  **Acceptance Criteria**:
  - [ ] upload_images 的 outputs schema 含 `asset_images` 为 required
  - [ ] `additionalProperties: false`
  - [ ] human_approval prompt 明确说明 AssetImageResult 格式
  - [ ] validate_workflow_contract() 对改造后的 schema 校验通过

  **QA Scenarios**:

  ```
  Scenario: 手动上传输出通过严格 schema 校验
    Tool: Bash (pytest)
    Preconditions: 节点定义已更新
    Steps:
      1. 构造手动上传输出：{asset_images: [{full_name: "林冲", image_url: "https://...", source: "manual_upload"}]}
      2. validate_json_value(upload_images_output_schema, output)
      3. 验证通过
    Expected Result: 校验通过
    Evidence: .sisyphus/evidence/task-10-upload-schema-valid.txt

  Scenario: 拒绝非 AssetImageResult 格式
    Tool: Bash (pytest)
    Preconditions: 节点定义已更新
    Steps:
      1. 构造旧格式输出：{decision: "approved", image_urls: ["https://..."]}
      2. validate_json_value(upload_images_output_schema, old_output)
      3. 验证抛出 ValidationError（缺少 asset_images）
    Expected Result: ValidationError 被抛出
    Evidence: .sisyphus/evidence/task-10-reject-old-format.txt
  ```

  **Commit**: YES（groups with Task 12）
  - Message: `feat(orchestration): unify upload_images output to strict AssetImageResult schema`
  - Files: `workflows/global/asset_storyboard_generation.workflow.yaml`

- [ ] 11. 节点注册（build_node_registry）

  **What to do**:
  - 在 `xiagent/nodes/__init__.py` 的 `build_node_registry()` 中注册所有新节点：
    ```python
    from xiagent.nodes.ai.assign_assets_to_segments import AssignAssetsToSegmentsNode
    from xiagent.nodes.tools.assemble_storyboard_context import AssembleStoryboardContextNode
    from xiagent.nodes.tools.extract_panel_image_urls import ExtractPanelImageUrlsNode
    from xiagent.nodes.ai.runninghub_image import RunningHubImageToImageNodeV2
    from xiagent.nodes.tools.storyboard_prompt import StoryboardPromptAssemblerNodeV2
    ```
  - 注册代码：
    ```python
    registry.register(AssignAssetsToSegmentsNode(
        model_router=router, provider="deepseek", model=deepseek_config.model,
    ))
    registry.register(AssembleStoryboardContextNode())
    registry.register(ExtractPanelImageUrlsNode())
    registry.register(RunningHubImageToImageNodeV2(
        model_router=router, provider="runninghub_image", model=runninghub_image_config.model,
    ))
    registry.register(StoryboardPromptAssemblerNodeV2())
    ```
  - 更新 `xiagent/nodes/__init__.py` 的 imports 和 `__all__`

  **Must NOT do**:
  - 不删除任何现有节点的注册
  - 不改变现有注册顺序

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯注册代码，模式固定
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3（with Tasks 9, 10, 12）
  - **Blocks**: Tasks 13, 14
  - **Blocked By**: Tasks 5, 6, 7, 8, 9（所有新节点实现完成）

  **References**:
  - `xiagent/nodes/__init__.py:72-116` — 当前注册代码参考
  - `xiagent/nodes/__init__.py:1-34` — 当前 imports
  - `xiagent/nodes/registry.py:12-26` — register() 方法

  **Acceptance Criteria**:
  - [ ] 所有 5 个新 ref 在 NodeRegistry 可查询
  - [ ] `build_node_registry()` 不抛出 ConflictError
  - [ ] 现有节点的注册不受影响

  **QA Scenarios**:

  ```
  Scenario: 注册表完整性验证
    Tool: Bash (pytest)
    Preconditions: 所有新节点已注册
    Steps:
      1. registry = build_node_registry(test_settings)
      2. 验证 registry.get("ai.assign_assets_to_segments.v1") 存在
      3. 验证 registry.get("tool.assemble_storyboard_context.v1") 存在
      4. 验证 registry.get("tool.extract_panel_image_urls.v1") 存在
      5. 验证 registry.get("ai.runninghub_image_to_image.v2") 存在
      6. 验证 registry.get("tool.storyboard_prompt_assembler.v2") 存在
      7. 验证现有节点 registry.get("tool.script_split.v1") 仍存在
    Expected Result: 所有新旧节点均可查询
    Failure Indicators: NotFoundError、ConflictError
    Evidence: .sisyphus/evidence/task-11-registry-complete.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `feat(nodes): register all new nodes in build_node_registry`
  - Files: `xiagent/nodes/__init__.py`

- [ ] 12. 总工作流 YAML 补全（自动生成路径 + 审核节点）

  **What to do**:
  - 在 Task 2 的草稿基础上补全：
    1. 添加 `generate_assets="自动生成"` 的条件分支：
       - `review_assets` → `generate_prompt_v2`（when generate_assets=自动生成）
       - `generate_prompt_v2` → `generate_image_v2`
       - `generate_image_v2` → 汇合点（与手动上传路径汇合到 `split_script`）
    2. 汇合点设计：两条路径都输出 `asset_images`（AssetImageResult[]），通过一个新汇合节点或直接将 `asset_images` 传递给 `assign_assets_to_segments`
    3. 遇到的关键问题：workflow 的 DAG 约束下两条路径如何汇合。使用方案：
       - 两条路径都连接到同一个下游节点（`split_script`）
       - DAG 合法（多入边合法）
       - `split_script` 不依赖 asset_images — 但 `assign_assets_to_segments` 依赖
       - 实际方案：两条路径汇入一个 data-only 节点（可用 `tool.echo.v1` 或新工具），输出即 `asset_images`
    4. 添加 `review_storyboard_prompt`（system.human_approval.v1，严格 schema）：
       - 展示：目标段落原文、在场资产列表、参考图 URL、分镜描述、最终 prompt
       - 输出：`decision`、`corrections`（可选，含 corrected_prompt、corrected_image_urls）
    5. 添加 `review_storyboard_image`（system.human_approval.v1，严格 schema）：
       - 展示：生成图像 URL、使用的 prompt 和参考资产
       - 输出：`decision`、`selected_image_url`、`revision_notes`
    6. 更新 edges 包含完整 DAG
    7. Final output schema（workflow level）：
       ```yaml
       type: object
       required: ["decision"]
       properties:
         decision: {type: string, enum: ["approved", "revision_needed"]}
         selected_image_url: {type: string}
         revision_notes: {type: string}
         generated_prompt: {type: string}
         asset_images: {type: array}
       additionalProperties: false
       ```

  **Must NOT do**:
  - 不在 v1 实现段落的循环处理
  - 不引入循环/重试逻辑
  - 不在 YAML 中使用未注册的 ref

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解完整 DAG 拓扑 + 条件分支 + 汇合设计
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3（with Tasks 9, 10, 11）
  - **Blocks**: Tasks 13, 14
  - **Blocked By**: Tasks 2, 5, 6, 7, 8（需要 YAML 草稿 + 所有新节点 ref 已确定）

  **References**:
  - `workflows/global/asset_storyboard_generation.workflow.yaml` — Task 2 草稿
  - `workflows/global/asset_catalog.workflow.yaml:647-675` — 条件分叉 edges 参考
  - `workflows/global/storyboard_generation.workflow.yaml:329-360` — collect_assets（审核节点模板，被替代）
  - `workflows/global/storyboard_generation.workflow.yaml:445-463` — 完整 edges 示例
  - `docs/design/2026-05-19-04-workflow-contract-design.md:104-116` — 条件分叉语法规范

  **Acceptance Criteria**:
  - [ ] YAML 包含 2 条条件分叉路径（手动上传 + 自动生成）
  - [ ] DAG 正确汇合（两条路径合法到达 END）
  - [ ] 3 个人工审核节点全部包含严格 output schema
  - [ ] `output_schema` 定义在 workflow 级别
  - [ ] `validate_workflow_contract()` 校验通过

  **QA Scenarios**:

  ```
  Scenario: 完整 YAML 通过 validator 校验
    Tool: Bash (pytest)
    Preconditions: 所有新节点已注册
    Steps:
      1. contract = load_workflow_file(WORKFLOW_PATH)
      2. validate_workflow_contract(contract, build_node_registry(test_settings))
      3. 验证不抛出任何校验错误
    Expected Result: 校验通过，无错误
    Failure Indicators: 任何 ValidationError（Schema 错误、ref 未找到、DAG 非法）
    Evidence: .sisyphus/evidence/task-12-full-validation.txt

  Scenario: 条件分叉 edges 正确
    Tool: Bash (pytest)
    Preconditions: YAML 已补全
    Steps:
      1. 提取所有 conditional edges（含 "when"）
      2. 验证 review_assets → generate_prompt_v2（when: 自动生成）
      3. 验证 review_assets → upload_images（when: 手动上传）
      4. 验证两条路径都可达 END
      5. 验证无孤立节点
    Expected Result: 分叉正确，汇合合法
    Failure Indicators: 孤立节点、路径断裂
    Evidence: .sisyphus/evidence/task-12-conditional-edges.txt
  ```

  **Commit**: YES（groups with Task 10）
  - Message: `feat(orchestration): complete workflow YAML with auto-generate path and review nodes`
  - Files: `workflows/global/asset_storyboard_generation.workflow.yaml`

- [ ] 13. 手动上传路径端到端测试（TDD — GREEN）

  **What to do**:
  - 在 `tests/test_asset_storyboard_orchestration.py` 中添加 `test_orchestration_manual_upload_path`
  - 使用 FakeOrchestrationRouter + WorkflowTestRunner
  - ConsoleIO 回答 3 轮 human_approval（review_assets → review_storyboard_prompt → review_storyboard_image）
  - 输入数据：
    ```python
    input_data = {
        "script": "林冲在山神庙外踏雪而来。",
        "background": "水浒传",
        "generate_assets": "手动上传",
    }
    ```
  - 验证：
    - `result.task.status == "succeeded"`
    - 资产提取 7 节点全部执行
    - 分镜 8 节点全部执行
    - `upload_images` 执行，`generate_prompt` 和 `generate_image` 不执行
    - 最终输出含 `selected_image_url`
    - `router.requests` 记录了正确的 LLM 调用序列

  **Must NOT do**:
  - 不使用真实 API Key
  - 不跳过任何人审核节点（ConsoleIO 必须提供答案）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 全链路端到端测试，多轮 human_approval
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4（with Tasks 14, 15）
  - **Blocks**: None
  - **Blocked By**: Tasks 3, 4, 5, 6, 7, 8, 9, 10, 11, 12（全部实现完成）

  **References**:
  - `tests/test_asset_catalog_workflow.py:340-387` — 手动上传路径端到端测试模板
  - `tests/test_asset_catalog_workflow.py:359-372` — ConsoleIO canned answers 模式
  - `tests/test_storyboard_workflow.py:258-310` — storyboard 端到端测试模板

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_asset_storyboard_orchestration.py::test_orchestration_manual_upload_path -q` → PASS
  - [ ] result.task.status == "succeeded"
  - [ ] upload_images 执行但 generate_prompt/generate_image 不执行

  **QA Scenarios**:

  ```
  Scenario: 手动上传完整链路
    Tool: Bash (pytest)
    Preconditions: FakeRouter + ConsoleIO 就绪
    Steps:
      1. router = FakeOrchestrationRouter()
      2. answers = iter(["approved", "approved", "approved"])  # 3 轮审核
      3. runner = WorkflowTestRunner(session, ConsoleIO(input_func=lambda _: next(answers)))
      4. result = await runner.run_workflow_file(WORKFLOW_PATH, input_data)
      5. 验证 result.task.status == "succeeded"
      6. 验证 executed_node_ids 包含 "extract_characters", "enrich_characters", "review_assets", "upload_images", "split_script", "assign_assets_to_segments", "describe_panels", "review_storyboard_prompt", "generate_image_v2", "review_storyboard_image"
      7. 验证 executed_node_ids 不包含 "generate_prompt_v2"（手动上传路径）
      8. 验证最终 review_storyboard_image 输出含 selected_image_url
    Expected Result: 全链路通过，20 节点全部正确执行
    Failure Indicators: 任何节点失败、路径错误、输出 schema 不符
    Evidence: .sisyphus/evidence/task-13-manual-e2e.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): add manual upload path e2e test (GREEN)`
  - Files: `tests/test_asset_storyboard_orchestration.py`

- [ ] 14. 自动生成路径端到端测试（TDD — GREEN）

  **What to do**:
  - 添加 `test_orchestration_auto_generate_path` 测试
  - 与 Task 13 类似，但使用 `generate_assets="自动生成"`
  - 需要 seed 一个模板资产到数据库（`_seed_file_asset` 提供 template_image_url）
  - 验证：
    - `generate_prompt_v2` 和 `generate_image_v2` 执行（而非 `upload_images`）
    - RunningHub 被调用（通过 `router.requests` 中 provider=="runninghub_image" 的请求）
    - `generate_image_v2` 输出 `asset_images` 数组，source == "ai_generated"
  - 还需额外验证 FakeRouter 中所有 pre-programmed 响应被正确消费

  **Must NOT do**:
  - 不使用真实 DeepSeek/RunningHub API

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 全链路端到端测试，需 seed 资产 + 验证 AI 调用序列
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4（with Tasks 13, 15）
  - **Blocks**: None
  - **Blocked By**: Same as Task 13

  **References**:
  - `tests/test_asset_catalog_workflow.py:285-338` — 自动生成路径端到端测试模板
  - `tests/test_asset_catalog_workflow.py:304-308` — _seed_file_asset 调用
  - `tests/test_asset_catalog_workflow.py:484-518` — _seed_file_asset 实现

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_asset_storyboard_orchestration.py::test_orchestration_auto_generate_path -q` → PASS
  - [ ] generate_image_v2 执行，upload_images 不执行
  - [ ] asset_images[0].source == "ai_generated"

  **QA Scenarios**:

  ```
  Scenario: 自动生成完整链路
    Tool: Bash (pytest)
    Preconditions: FakeRouter + seed 资产就绪
    Steps:
      1. await _seed_file_asset(database_path, user_id, "模板角色", "https://cdn.test/template.png")
      2. router = FakeOrchestrationRouter()
      3. answers = iter(["approved", "approved", "approved"])
      4. result = await runner.run_workflow_file(WORKFLOW_PATH, input_data={"script":"林冲踏雪而来。","background":"水浒传","generate_assets":"自动生成","template_image_url":"https://cdn.test/template.png"})
      5. 验证 executed_node_ids 包含 generate_prompt_v2, generate_image_v2
      6. 验证 executed_node_ids 不包含 upload_images
      7. 验证 generate_image_v2 输出 output.asset_images 数组
      8. 验证 asset_images[0].source == "ai_generated"
    Expected Result: AI 生成路径全部通过
    Evidence: .sisyphus/evidence/task-14-auto-e2e.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): add auto-generate path e2e test (GREEN)`
  - Files: `tests/test_asset_storyboard_orchestration.py`

- [ ] 15. Schema 测试 + 边界测试（TDD — GREEN）

  **What to do**:
  - 添加以下 schema 测试：
    - `test_assign_assets_to_segments_output_schema`：验证 segment_asset_assignments 的嵌套结构
    - `test_assemble_storyboard_context_output_schema`：验证 context_string 存在
    - `test_extract_panel_image_urls_output_schema`：验证 image_urls 数组 + minItems
    - `test_prompt_assembler_v2_output_schema`：验证 prompt + image_urls + aspect_ratio + resolution
    - `test_review_storyboard_image_output_schema`：验证 decision + selected_image_url
    - `test_asset_image_result_schema`：验证统一的 AssetImageResult（auto + manual 两种 source）
  - 添加边界测试：
    - `test_orchestration_empty_script`：空剧本 → task 成功但无角色（优雅处理非崩溃）
    - `test_orchestration_storyboard_target_default`：不传 storyboard_target → 默认 segment=0, panel=0
    - `test_orchestration_all_new_characters`：所有角色均为新角色（匹配失败 → 新变体路径）
  - 使用 `validate_json_value()` 验证每个 schema 的合法/非法样例

  **Must NOT do**:
  - 不要在边界测试中使用真实 API

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Schema 验证 + 边界测试，遵循已有模式
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4（with Tasks 13, 14）
  - **Blocks**: None
  - **Blocked By**: Tasks 5-12（需要所有 schema 定义完成）

  **References**:
  - `tests/test_asset_catalog_workflow.py:111-138` — extract_characters schema 测试模板
  - `tests/test_asset_catalog_workflow.py:140-160` — semantic_match schema 测试模板
  - `tests/test_asset_catalog_workflow.py:162-189` — match_variants schema 测试模板
  - `tests/test_asset_catalog_workflow.py:191-214` — check_accessories schema 测试模板
  - `tests/test_storyboard_workflow.py:98-113` — structured LLM output schema 测试模板

  **Acceptance Criteria**:
  - [ ] 所有 schema 测试 PASS（合法数据通过，非法数据被拒绝）
  - [ ] 空剧本测试 PASS（task.succeeded，不崩溃）
  - [ ] storyboard_target 默认值测试 PASS
  - [ ] 全新角色测试 PASS

  **QA Scenarios**:

  ```
  Scenario: 全新角色路径不崩溃
    Tool: Bash (pytest)
    Preconditions: FakeRouter 预编程 "无匹配" 响应
    Steps:
      1. input_data = {"script": "无名角色登场。", "background": "未知作品", "generate_assets": "手动上传"}
      2. result = await runner.run_workflow_file(WORKFLOW_PATH, input_data)
      3. 验证 result.task.status == "succeeded"
      4. 验证 enrich_characters 输出的 characters[0].matched == False
    Expected Result: 全链路完成，角色标记为 unmatched
    Failure Indicators: task.failed、NullPointer
    Evidence: .sisyphus/evidence/task-15-new-characters.txt

  Scenario: 空剧本优雅处理
    Tool: Bash (pytest)
    Preconditions: FakeRouter 就绪
    Steps:
      1. input_data = {"script": "", "background": "水浒传", "generate_assets": "手动上传"}
      2. result = await runner.run_workflow_file(WORKFLOW_PATH, input_data)
      3. 验证 task 最终状态（succeeded 或 failed 均可，但不能崩溃）
    Expected Result: 不崩溃，正确处理空输入
    Failure Indicators: 未捕获的异常、无限等待
    Evidence: .sisyphus/evidence/task-15-empty-script.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): add schema tests and boundary tests (GREEN)`
  - Files: `tests/test_asset_storyboard_orchestration.py`

- [ ] 16. 场景提取管道（YAML 节点 + prompt 设计）

  **What to do**:
  - 在工作流 YAML 中新增场景提取管道（与角色管道并行）：
    1. `extract_scenes` — `ai.deepseek_structured_json.v1`，prompt：从剧本提取所有场景（地点名称、描述、时间特征）
    2. `lookup_scene_assets` — `tool.asset_lookup.v1`，tags: `["场景"]`
    3. `match_scenes_by_name` — `tool.asset_lookup.v1`，用场景名称精确匹配
    4. `enrich_scenes` — `tool.enrich_characters.v1`，合并匹配结果
  - ⚠️ 场景**不需要**变体匹配和配件检查（场景只有一个样子）
  - extract_scenes 输出 schema：
    ```yaml
    type: object
    required: ["reasoning", "scenes", "scene_names"]
    properties:
      reasoning: {type: string}
      scenes: {type: array, items: {required: ["name", "description", "time_of_day", "location_type"]}}
      scene_names: {type: array, items: {type: string}}
    ```
  - 场景管道边缘：`START → extract_scenes → lookup_scene_assets → match_scenes_by_name → enrich_scenes → review_assets`

  **Must NOT do**:
  - 不为场景添加 variant/accessory 节点
  - 不修改角色管道节点

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 复用已有节点 ref，仅设计 prompt 和 schema
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 5, 6, 7, 8, 17）
  - **Blocks**: Task 12
  - **Blocked By**: Task 2（YAML 草稿存在）

  **References**:
  - `workflows/global/asset_catalog.workflow.yaml:27-114` — extract_characters 节点定义模板（prompt 结构参考）
  - `workflows/global/asset_catalog.workflow.yaml:116-157` — lookup_existing_assets 模板（tags 参数）
  - `workflows/global/asset_catalog.workflow.yaml:159-202` — match_by_name 模板
  - `workflows/global/asset_catalog.workflow.yaml:264-314` — enrich_characters 模板

  **Acceptance Criteria**:
  - [ ] 4 个场景管道节点在 YAML 中定义完整
  - [ ] edges 正确（START → extract_scenes → ... → review_assets）
  - [ ] extract_scenes 的 prompt 明确要求提取场景

  **QA Scenarios**:

  ```
  Scenario: 场景提取 prompt 正确
    Tool: Bash (pytest)
    Preconditions: YAML 已包含场景管道
    Steps:
      1. contract = load_workflow_file(WORKFLOW_PATH)
      2. 验证 nodes 中 extract_scenes 存在，ref == "ai.deepseek_structured_json.v1"
      3. 验证 lookup_scene_assets 的 tags == ["场景"]
      4. 验证编排节点不包含 match_variants 或 check_accessories（场景不需要）
    Expected Result: 场景管道结构正确
    Evidence: .sisyphus/evidence/task-16-scene-pipeline.txt
  ```

  **Commit**: YES（groups with Task 17）
  - Message: `feat(orchestration): add scene extraction pipeline (extract → lookup → match → enrich)`
  - Files: `workflows/global/asset_storyboard_generation.workflow.yaml`

- [ ] 17. 道具提取管道（YAML 节点 + prompt 设计）

  **What to do**:
  - 在工作流 YAML 中新增道具提取管道（与角色、场景管道并行）：
    1. `extract_props` — `ai.deepseek_structured_json.v1`，prompt：从剧本提取所有道具（武器、物品、服饰配件等）
    2. `lookup_prop_assets` — `tool.asset_lookup.v1`，tags: `["道具"]`
    3. `match_props_by_name` — `tool.asset_lookup.v1`，用道具名称精确匹配
    4. `enrich_props` — `tool.enrich_characters.v1`，合并匹配结果
  - ⚠️ 道具**不需要**变体匹配、配件检查和语义匹配（比场景更简单）
  - extract_props 输出 schema：
    ```yaml
    type: object
    required: ["reasoning", "props", "prop_names"]
    properties:
      reasoning: {type: string}
      props: {type: array, items: {required: ["name", "description", "category"]}}
      prop_names: {type: array, items: {type: string}}
    ```
  - 道具管道边缘：`START → extract_props → lookup_prop_assets → match_props_by_name → enrich_props → review_assets`

  **Must NOT do**:
  - 不为道具添加 semantic_match/variant/accessory 节点
  - 不修改角色和场景管道

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 比场景管道更简单，纯 prompt + schema 设计
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2（with Tasks 5, 6, 7, 8, 16）
  - **Blocks**: Task 12
  - **Blocked By**: Task 2

  **References**:
  - 同 Task 16 的参考模板
  - `workflows/global/asset_catalog.workflow.yaml:27-114` — extract 模板（prompt 中需强调"仅提取独立道具，服装本身的配件不算道具"）

  **Acceptance Criteria**:
  - [ ] 4 个道具管道节点在 YAML 中定义完整
  - [ ] edges 正确（START → extract_props → ... → review_assets）
  - [ ] extract_props 不包含 variant 或 semantic_match 相关节点

  **QA Scenarios**:

  ```
  Scenario: 道具管道最简结构
    Tool: Bash (pytest)
    Preconditions: YAML 已包含道具管道
    Steps:
      1. contract = load_workflow_file(WORKFLOW_PATH)
      2. 验证 nodes 中 extract_props 存在
      3. 验证 lookup_prop_assets 的 tags == ["道具"]
      4. 验证不存在 semantic_match_props 节点（道具不需要语义匹配）
      5. 验证不存在 match_variants 或 check_accessories for props
    Expected Result: 道具管道仅 4 节点，结构最简
    Evidence: .sisyphus/evidence/task-17-prop-pipeline.txt
  ```

  **Commit**: YES（groups with Task 16）
  - Message: `feat(orchestration): add prop extraction pipeline (extract → lookup → match → enrich)`
  - Files: `workflows/global/asset_storyboard_generation.workflow.yaml`

- [ ] 18. 场景管道端到端测试

  **What to do**:
  - 在 `tests/test_asset_storyboard_orchestration.py` 中添加 `test_scene_pipeline_execution`
  - 使用 FakeOrchestrationRouter（需扩展响应队列包含场景提取的 LLM 调用）
  - 验证：extract_scenes → lookup → match → enrich → review 序列正确执行
  - 验证 extract_scenes 输出了有意义的场景列表（从测试剧本中提取）
  - 种子场景资产到数据库（`_seed_file_asset`），验证 lookup 和 match 正常工作

  **Must NOT do**:
  - 不要启动完整的 26 节点工作流（仅测场景管道相关节点）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 遵循已有 e2e 测试模式
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4（with Tasks 13, 14, 15, 19）
  - **Blocks**: None
  - **Blocked By**: Tasks 12, 16

  **References**:
  - `tests/test_asset_catalog_workflow.py:285-338` — 自动生成 e2e 模板
  - `tests/test_asset_catalog_workflow.py:484-518` — _seed_file_asset 模板

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_asset_storyboard_orchestration.py::test_scene_pipeline_execution -q` → PASS
  - [ ] extract_scenes 执行并输出 scenes 数组

  **QA Scenarios**:

  ```
  Scenario: 场景管道完整执行
    Tool: Bash (pytest)
    Preconditions: FakeRouter 扩展 + seed 场景资产
    Steps:
      1. seed 场景资产（"山神庙" with tags=["场景"]）
      2. runner.run_workflow_file() with script="林冲在山神庙外踏雪而来。"
      3. 验证 executed_node_ids 包含 extract_scenes, lookup_scene_assets, match_scenes_by_name, enrich_scenes
      4. 验证 enrich_scenes 输出的 scenes 中 "山神庙" 被匹配到
    Expected Result: 场景管道正确执行，匹配到已有场景资产
    Evidence: .sisyphus/evidence/task-18-scene-e2e.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): add scene pipeline e2e test`
  - Files: `tests/test_asset_storyboard_orchestration.py`

- [ ] 19. 道具管道端到端测试

  **What to do**:
  - 添加 `test_prop_pipeline_execution`
  - 类似 Task 18，但验证道具管道（extract_props → lookup → match → enrich）
  - 种子道具资产到数据库（`_seed_file_asset` with tags=["道具"]）
  - 验证道具提取成功，并且 props 管道不执行 semantic_match（确认结构最简）

  **Must NOT do**:
  - 不要执行不必要的节点

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 与 Task 18 几乎相同，替换为道具管道
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4（with Tasks 13, 14, 15, 18）
  - **Blocks**: None
  - **Blocked By**: Tasks 12, 17

  **References**:
  - 同 Task 18

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_asset_storyboard_orchestration.py::test_prop_pipeline_execution -q` → PASS
  - [ ] extract_props 执行，不执行 semantic_match_props（不存在的节点）

  **QA Scenarios**:

  ```
  Scenario: 道具管道不执行语义匹配
    Tool: Bash (pytest)
    Preconditions: FakeRouter 扩展
    Steps:
      1. seed 道具资产（"花枪" with tags=["道具"]）
      2. runner.run_workflow_file() with script="林冲握紧花枪。"
      3. 验证 executed_node_ids 包含 extract_props, lookup_prop_assets, match_props_by_name, enrich_props
      4. 验证不存在 semantic_match_props 的执行记录
    Expected Result: 道具管道正确执行，无多余的语义匹配步骤
    Evidence: .sisyphus/evidence/task-19-prop-e2e.txt
  ```

  **Commit**: YES（独立提交）
  - Message: `test(orchestration): add prop pipeline e2e test`
  - Files: `tests/test_asset_storyboard_orchestration.py`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  读取计划全文。对每个 "Must Have"：验证实现存在（读文件、curl 端点、执行命令）。对每个 "Must NOT Have"：搜索代码库中禁用模式 — 发现则 REJECT。检查 evidence 文件存在于 `.sisyphus/evidence/`。
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  运行 `ruff check .` + `python -m pytest tests/test_asset_storyboard_orchestration.py -q`。审查所有变更文件：类型注解完整性、空 catch 块、注释掉的代码、未使用导入。检查 AI slop：过度注释、过度抽象、通用命名。
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  从干净状态开始。执行每个任务的 QA 场景 — 精确实步骤，捕获证据。测试跨任务集成（功能协作，非孤立）。测试边缘情况：空输入、全新增角色、RunningHub 超时。
  保存至 `.sisyphus/evidence/final-qa/`。
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  对每个任务：读取 "What to do"，读取实际 diff（git log/diff）。验证 1:1 — 规格中所有内容已构建（无遗漏），规格外无内容已构建（无蔓延）。检查 "Must NOT do" 合规性。检测跨任务污染：Task N 接触 Task M 的文件。
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `feat(orchestration): define unified asset result schema and workflow skeleton`
- **Wave 2**: `feat(nodes): add assign_assets_to_segments, assemble_storyboard_context, extract_panel_image_urls` — + `feat(orchestration): add scene and prop extraction pipelines`
- **Wave 3**: `feat(nodes): add v2 endpoints for unified fork-merge output; register all new nodes`
- **Wave 4**: `test(orchestration): add TDD test suite for orchestration workflow (characters + scenes + props)`

---

## Success Criteria

### Verification Commands
```bash
python -m pytest tests/test_asset_storyboard_orchestration.py -q -v
# Expected: ALL PASS (0 failures, 0 errors)

python -m xiagent.workflows.testing_cli workflows/global/asset_storyboard_generation.workflow.yaml --input '{"script":"林冲踏雪而来。","background":"水浒传"}'
# Expected: task.status = "succeeded", output contains selected_image_url

ruff check xiagent/nodes/ai/assign_assets_to_segments.py xiagent/nodes/tools/assemble_storyboard_context.py xiagent/nodes/tools/extract_panel_image_urls.py
# Expected: All checks passed!
```

### Final Checklist
- [ ] 所有 "Must Have" 存在
- [ ] 所有 "Must NOT Have" 缺席
- [ ] 全部测试通过
- [ ] 工作流通过 `validate_workflow_contract()` 校验
