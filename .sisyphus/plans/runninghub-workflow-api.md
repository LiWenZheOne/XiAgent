# RunningHub Workflow API Integration

## TL;DR

> **Quick Summary**: 新建 `RunningHubWorkflowProvider` + `RunningHubImageToImageNodeV3`，将分镜图像生成从旧 flat payload 格式升级为新 `nodeInfoList` 格式，对接 RunningHub ComfyUI 工作流 API。旧 v1/v2 节点保持不变。
> 
> **Deliverables**:
> - `RunningHubWorkflowModelConfig` 配置类
> - `RunningHubWorkflowProvider`（含图片预上传 + nodeInfoList 构建 + submit/poll）
> - `RunningHubImageToImageNodeV3`（ref: `ai.runninghub_image_to_image.v3`）
> - 更新 `workflows/global/storyboard_from_sketch.workflow.yaml` Phase C
> - TDD 测试（provider + node + workflow）
> 
> **Estimated Effort**: Short-Medium
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Task 1 → Task 2 → Task 4 → Task 5

---

## Context

### Original Request
替换 `storyboard_from_sketch` 工作流中分镜图像生成步骤的 RunningHub API 格式，从旧的 `{imageUrls, prompt, aspectRatio, resolution}` flat payload 改为新的 `{nodeInfoList: [{nodeId, fieldName, fieldValue}]}` 格式，对接 ComfyUI 工作流 API。

### Interview Summary

**Key Discussions**:
- **架构决策**: 新建 provider 变体（`RunningHubWorkflowProvider`），不修改现有 `RunningHubImageProvider`，确保 v1/v2 节点向后兼容
- **Workflow ID**: `2059174216020357122`（仅用于分镜生成，角色资产生成继续用旧 API）
- **Node 映射**（硬编码到 config）:
  - nodeId "141": 线稿草图
  - nodeId "139/140/81": 角色参考图（按顺序分配）
  - nodeId "150": Gemini caption 描述文本
- **图片预上传**: 所有图片先通过 `/openapi/v2/media/upload/binary` 上传，获取文件名后填入 `fieldValue`
- **仅替换 Phase C**: 工作流 YAML 中只改分镜生成节点，Phase A/B 不动

### Research Findings
- 现有 `RunningHubImageProvider` (326行): 使用 `_UrllibJsonClient`，submit → poll → results 模式，`_task_url()` 构建端点 URL，`_request_payload()` 构建 flat payload
- `RunningHubImageToImageNode` (V1): input 为 prompt + image_urls + aspect_ratio + resolution
- `RunningHubImageToImageNodeV2` (V2): input 为 prompt_results[]（批量模式，逐角色生成）
- 现有 provider 保留 `endpoint` 配置字段；新 provider 需要 `workflow_id` + `instance_type`
- 查询端点 `/openapi/v2/query` 与新 API 完全兼容

### NodeId Mapping
```
nodeId: "141"   fieldName: "image"   → 线稿草图 (line_art_url)
nodeId: "139"   fieldName: "image"   → 角色参考图 1 (character_ref_1)
nodeId: "140"   fieldName: "image"   → 角色参考图 2 (character_ref_2)
nodeId: "81"    fieldName: "image"   → 角色参考图 3 (character_ref_3)
nodeId: "150"   fieldName: "text"    → Gemini caption 中文描述
```

---

## Work Objectives

### Core Objective
创建 RunningHub ComfyUI 工作流 API 的 provider 和节点实现，将 Gemini caption + 线稿 + 角色参考图按 nodeInfoList 格式提交生成分镜图像。

### Concrete Deliverables
- `xiagent/models/types.py` — 新增 `RunningHubWorkflowModelConfig`
- `xiagent/models/config.py` — 新增 `[runninghub_workflow]` 配置节
- `xiagent/infrastructure/config.py` — Settings 新增 workflow 字段
- `xiagent/models/local_config.example.toml` — 新增 `[runninghub_workflow]` 节
- `xiagent/models/providers/runninghub.py` — 新增 `RunningHubWorkflowProvider`
- `xiagent/nodes/ai/runninghub_image.py` — 新增 `RunningHubImageToImageNodeV3`
- `xiagent/nodes/__init__.py` — 注册新 node + provider
- `tests/test_runninghub_workflow.py` — TDD 测试
- `workflows/global/storyboard_from_sketch.workflow.yaml` — 更新 Phase C

### Definition of Done
- [ ] `python -m pytest tests/test_runninghub_workflow.py -v` → ALL pass
- [ ] `python -m pytest -q` → 全测试套件无回归（286+ 通过）
- [ ] 工作流 CLI: `python -m xiagent.workflows.testing_cli --workflow-id storyboard_from_sketch` 正常执行
- [ ] 旧工作流 `asset_storyboard_generation` 行为不变

### Must Have
- 图片预上传功能（`/openapi/v2/media/upload/binary`）
- nodeInfoList 动态构建（按 nodeId 映射分配图片和文本）
- 旧 v1/v2 provider 行为完全不变
- workflow YAML 中 Phase C 使用新节点

### Must NOT Have (Guardrails)
- ❌ 不修改 `RunningHubImageProvider` / `RunningHubTextToImageProvider` 任何代码
- ❌ 不修改 `RunningHubImageToImageNode`(V1) / `RunningHubImageToImageNodeV2` 任何代码
- ❌ 不修改 `RunningHubImageModelConfig` / `RunningHubTextToImageModelConfig`
- ❌ 不更改 Phase A / Phase B 工作流节点
- ❌ 不删除旧 provider 注册
- ❌ 不在新 provider 中使用 async with AsyncOpenAI（RunningHub 用 urllib 模式）
- ❌ 不添加重试逻辑以外的复杂错误恢复

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: TDD — RED → GREEN → REFACTOR
- **Framework**: pytest + pytest-asyncio

### QA Policy
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - MAX PARALLEL):
├── Task 1: RunningHubWorkflowModelConfig (types + config + settings + toml) [quick]
├── Task 2: RunningHubWorkflowProvider (TDD) [deep]
└── Task 3: RunningHubImageToImageNodeV3 (TDD) [deep]

Wave 2 (Integration - depends on Wave 1):
├── Task 4: 注册 provider + node，更新 workflow YAML [unspecified-high]
└── Task 5: 集成测试 + 回归测试 [deep]

Wave FINAL:
├── Task F1: Oracle compliance audit
├── Task F2: Code quality review
├── Task F3: Real manual QA
└── Task F4: Scope fidelity check
```

**Critical Path**: Task 1 → Task 2 → Task 4 → Task 5
**Max Concurrent**: 3 (Wave 1)

### Dependency Matrix
- **1**: - - 2, 3
- **2**: 1 - 4
- **3**: 1 - 4
- **4**: 2, 3 - 5
- **5**: 4 - F1-F4

---

## TODOs

- [x] 1. RunningHubWorkflowModelConfig (types + config + settings + toml)

  **What to do**:
  - RED: 验证 config 默认值正确
  - GREEN: 
    - `xiagent/models/types.py`: 新增 `RunningHubWorkflowModelConfig(frozen=True, slots=True)` — `api_key: str | None`, `base_url: str = "https://www.runninghub.ai"`, `workflow_id: str = "2059174216020357122"`, `instance_type: str = "default"`, `use_personal_queue: bool = False`, `node_mapping: dict = field(default_factory=lambda: {"line_art": "141", "ref_images": ["139","140","81"], "text_prompt": "150"})`
    - `xiagent/models/config.py`: 新增 `[runninghub_workflow]` section（参考 deepseek 模式），env var `RUNNINGHUB_WORKFLOW_ID`, `RUNNINGHUB_WORKFLOW_INSTANCE_TYPE`
    - `xiagent/infrastructure/config.py`: Settings 新增 `runninghub_workflow_api_key`, `runninghub_workflow_base_url`, `runninghub_workflow_workflow_id`, `runninghub_workflow_instance_type`
    - `xiagent/models/local_config.example.toml`: 新增 `[runninghub_workflow]` 节

  **Must NOT do**: 不修改现有 `RunningHubImageModelConfig` 或相关字段

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 (with Tasks 2, 3)
  **Blocked By**: None

  **References**: `xiagent/models/types.py:37-53` (RunningHubImageModelConfig), `xiagent/models/config.py:75-141` (runninghub_image 配置模式)

  **Acceptance Criteria**:
  - [ ] `RunningHubWorkflowModelConfig().workflow_id == "2059174216020357122"`
  - [ ] `load_model_config().runninghub_workflow` 非 None
  - [ ] Env var 覆盖测试通过

  **QA Scenarios**:
  ```
  Scenario: Default config values
    Tool: Bash
    Steps:
      1. python -c "from xiagent.models.types import RunningHubWorkflowModelConfig; c = RunningHubWorkflowModelConfig(); print(c.workflow_id)"
    Expected: 2059174216020357122
    Evidence: .sisyphus/evidence/task-rh1-defaults.txt
  ```

  **Commit**: YES
  - Message: `feat(models): add RunningHubWorkflowModelConfig`
  - Files: `types.py`, `config.py`, `infrastructure/config.py`, `local_config.example.toml`

- [x] 2. RunningHubWorkflowProvider (TDD)

  **What to do**:
  - RED: 写 `tests/test_runninghub_workflow.py`:
    - `test_workflow_provider_requires_api_key`
    - `test_workflow_provider_uploads_images` — mock upload，验证 `/media/upload/binary` 被调用
    - `test_workflow_provider_builds_nodeinfo_list` — 验证 nodeInfoList 按 nodeId 映射正确构建
    - `test_workflow_provider_submits_and_polls` — mock submit + poll 流程
    - `test_workflow_provider_handles_upload_failure` — 上传失败处理
  - GREEN: 在 `xiagent/models/providers/runninghub.py` 新增 `RunningHubWorkflowProvider(ChatModelProvider)`:
    - 复用 `_UrllibJsonClient` 做 HTTP 请求
    - `_upload_image(file_url: str) -> str`: POST multipart form 到 `/media/upload/binary`，返回 `data.download_url` 中的文件名部分
    - `_request_payload(request)`: 从 metadata 取 prompt + image_urls + line_art_url → 上传所有图片 → 构建 nodeInfoList:
      ```python
      node_info_list = []
      # line_art → nodeId "141"
      node_info_list.append({"nodeId": "141", "fieldName": "image", "fieldValue": filename, "description": "line_art"})
      # ref images → nodeId "139", "140", "81"
      for i, url in enumerate(ref_image_urls[:3]):
          node_info_list.append({"nodeId": ["139","140","81"][i], "fieldName": "image", "fieldValue": filename})
      # caption → nodeId "150"
      node_info_list.append({"nodeId": "150", "fieldName": "text", "fieldValue": caption, "description": "text"})
      ```
    - `_task_url()`: `{base_url}/openapi/v2/run/ai-app/{workflow_id}`
    - 复用父类 `_poll_until_complete()` + `_query_url()` + `_chat_response()` 模式
  - REFACTOR: 确保与 `RunningHubImageProvider` 结构一致

  **Must NOT do**: 不修改现有 provider 类

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 1 (with Tasks 1, 3)
  **Blocked By**: Task 1

  **References**: `xiagent/models/providers/runninghub.py:58-298` (完整 provider 模式), `xiagent/models/providers/runninghub.py:151-159` (_post_json), `xiagent/models/providers/runninghub.py:161-205` (_poll_until_complete)

  **Acceptance Criteria**:
  - [ ] `test_runninghub_workflow.py` 5 个测试全部通过
  - [ ] Mock 验证 `/media/upload/binary` multipart 上传正确
  - [ ] nodeInfoList 顺序: line_art (141) → ref_images (139,140,81) → text (150)

  **QA Scenarios**:
  ```
  Scenario: Provider builds correct nodeInfoList
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_runninghub_workflow.py::test_workflow_provider_builds_nodeinfo_list -v
    Expected: PASSED — nodeInfoList 结构正确
    Evidence: .sisyphus/evidence/task-rh2-nodeinfo.txt
  ```

  **Commit**: YES
  - Message: `feat(models): add RunningHubWorkflowProvider`
  - Files: `xiagent/models/providers/runninghub.py`

- [x] 3. RunningHubImageToImageNodeV3 (TDD)

  **What to do**:
  - RED: 写测试（追加到 `test_runninghub_workflow.py`）:
    - `test_v3_node_describe_has_correct_ref` — ref == "ai.runninghub_image_to_image.v3"
    - `test_v3_node_rejects_missing_prompt`
    - `test_v3_node_rejects_missing_image_urls`
    - `test_v3_node_calls_workflow_provider` — mock provider 验证被调用
  - GREEN: 在 `xiagent/nodes/ai/runninghub_image.py` 新增 `RunningHubImageToImageNodeV3(BaseNode)`:
    - ref: `"ai.runninghub_image_to_image.v3"`
    - input_schema: `prompt` (str), `image_urls` (list[str]), `line_art_url` (str, optional), `aspect_ratio` (str, optional), `resolution` (str, optional), `poll_interval_seconds` (float, optional), `poll_timeout_seconds` (float, optional)
    - output_schema: 与 V1 相同 — `image_url`, `model`, `usage`, `results`
    - `run()`: 验证输入 → 构建 metadata（含 line_art_url + image_urls）→ 调用 `model_router.chat(provider="runninghub_workflow", model=..., messages=[ChatMessage(role="user", content=prompt)], metadata=metadata)` → 返回 NodeResult
  - REFACTOR: 确保与 V1 结构一致

  **Must NOT do**: 不修改 V1/V2 节点代码

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 1 (with Tasks 1, 2)
  **Blocked By**: Task 1 (config)

  **References**: `xiagent/nodes/ai/runninghub_image.py:103-125` (V1 完整实现), `xiagent/nodes/ai/runninghub_image.py:127-132` (_metadata 方法)

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_runninghub_workflow.py -v` → 9+ tests pass
  - [ ] `node.describe().ref == "ai.runninghub_image_to_image.v3"`
  - [ ] input schema 包含 `line_art_url` 可选字段

  **Commit**: YES
  - Message: `feat(nodes): add RunningHubImageToImageNodeV3`
  - Files: `xiagent/nodes/ai/runninghub_image.py`

- [x] 4. 注册 provider + node，更新 workflow YAML

  **What to do**:
  - 在 `xiagent/nodes/__init__.py`:
    1. 导入和注册 `RunningHubWorkflowProvider`
    2. 导入和注册 `RunningHubImageToImageNodeV3`
  - 在 `xiagent/nodes/ai/__init__.py`: 导出 V3 node
  - 更新 `workflows/global/storyboard_from_sketch.workflow.yaml` Phase C:
    - 替换 `generate_storyboard_image` 节点的 ref 从 `ai.runninghub_image_to_image.v1` → `ai.runninghub_image_to_image.v3`
    - 确保 `assemble_prompt_v3` 输出的 `prompt` + `image_urls` + `line_art_url` 正确映射到 V3 节点的 input
    - 添加 `line_art_url` input 字段，从 `upload_line_art` 节点的输出获取

  **Must NOT do**: 不修改 Phase A/B 节点，不修改 V1/V2 注册

  **Recommended Agent Profile**: `unspecified-high`
  **Parallelization**: Wave 2 (with Task 5)
  **Blocked By**: Tasks 2, 3

  **References**: `xiagent/nodes/__init__.py` (注册模式), `workflows/global/storyboard_from_sketch.workflow.yaml` (Phase C 位置)

  **Acceptance Criteria**:
  - [ ] `registry.get("ai.runninghub_image_to_image.v3")` 可用
  - [ ] `workflow` 加载+校验通过
  - [ ] V1/V2 仍可注册（不冲突）

  **QA Scenarios**:
  ```
  Scenario: Node registered
    Tool: Bash
    Steps:
      1. python -c "from xiagent.nodes import build_node_registry; from xiagent.infrastructure.config import load_settings; r = build_node_registry(load_settings()); n = r.get('ai.runninghub_image_to_image.v3'); print(n.describe().ref)"
    Expected: ai.runninghub_image_to_image.v3
    Evidence: .sisyphus/evidence/task-rh4-reg.txt
  ```

  **Commit**: YES
  - Message: `feat: register v3 node and update workflow YAML`
  - Files: `nodes/__init__.py`, `nodes/ai/__init__.py`, `workflows/global/storyboard_from_sketch.workflow.yaml`

- [x] 5. 集成测试 + 回归测试 (TDD)

  **What to do**:
  - RED: 写集成测试（追加到 `test_runninghub_workflow.py`）:
    - `test_v3_integration_full_submit_poll_flow` — mock 完整上传→提交→轮询→返回流程
    - `test_v3_with_storyboard_workflow` — mock provider 注入 workflow test builder，验证完整链路
    - `test_v1_node_still_works` — 验证 V1 节点未受影响
    - `test_existing_workflows_still_load` — 验证 `asset_storyboard_generation` workflow 仍可加载
  - GREEN: 实现 mock 和测试
  - REFACTOR: 共享 mock fixtures

  **Must NOT do**: 不使用真实 RunningHub API key

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 2 (with Task 4)
  **Blocked By**: Task 4

  **References**: `tests/test_workflow_storyboard_from_sketch.py` (已有集成测试 mock 模式), `tests/test_model_router.py` (provider mock 模式)

  **Acceptance Criteria**:
  - [ ] 所有新测试通过
  - [ ] `python -m pytest -q` → 286+ 通过，无回归
  - [ ] V1 node 测试仍通过

  **QA Scenarios**:
  ```
  Scenario: Full v3 pipeline with mocks
    Tool: Bash
    Steps:
      1. python -m pytest tests/test_runninghub_workflow.py::test_v3_integration_full_submit_poll_flow -v
    Expected: PASSED
    Evidence: .sisyphus/evidence/task-rh5-integration.txt
  ```

  **Commit**: YES
  - Message: `test: add integration tests for v3 node`
  - Files: `tests/test_runninghub_workflow.py`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
- [x] F2. **Code Quality Review** — `unspecified-high`
- [x] F3. **Real Manual QA** — `unspecified-high`
- [x] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **Wave 1**: `feat(models): add RunningHubWorkflowModelConfig` — types.py, config.py, settings, toml
- **Wave 1**: `feat(models): add RunningHubWorkflowProvider` — providers/runninghub.py
- **Wave 1**: `feat(nodes): add RunningHubImageToImageNodeV3` — nodes/ai/runninghub_image.py
- **Wave 2**: `feat: register v3 node and update workflow YAML` — nodes/__init__.py, workflow yaml
- **Wave 2**: `test: add integration tests` — tests/

---

## Success Criteria

### Verification Commands
```bash
# New provider/node tests
python -m pytest tests/test_runninghub_workflow.py -v

# Full regression
python -m pytest -q

# Workflow loading validation
python -c "
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.validator import validate_workflow_contract
from xiagent.nodes import build_node_registry
from xiagent.infrastructure.config import load_settings
reg = build_node_registry(load_settings())
contract = load_workflow_file(Path('workflows/global/storyboard_from_sketch.workflow.yaml'))
validate_workflow_contract(contract, reg)
print('OK')
"
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent (v1/v2 unchanged)
- [ ] All 5 implementation tasks complete
- [ ] F1-F4 all APPROVE
- [ ] Full test suite zero regression
