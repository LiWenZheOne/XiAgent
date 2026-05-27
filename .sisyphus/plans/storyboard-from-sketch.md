# Storyboard from Sketch Workflow

## TL;DR

> **Quick Summary**: 新建工作流 `storyboard_from_sketch`，基于预画分镜线稿 + 剧本 → Gemini 视觉分析生成 `<think>+<caption>` 中文描述 → RunningHub 生成最终图像。复用现有资产提取管道，新增 Gemini Provider 及 Vision 节点。
> 
> **Deliverables**:
> - `ChatMessage` 扩展（支持多模态 content）
> - `GeminiChatProvider`（OpenAI 兼容 `/v1/chat/completions` 接口）
> - `GeminiVisionNode`（ref: `ai.gemini_vision.v1`）
> - `workflows/global/storyboard_from_sketch.workflow.yaml`
> - 全套 TDD 测试（单元测试 + 集成测试 + 工作流测试）
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: Task 1 → Task 5 → Task 7 → Task 9

---

## Context

### Original Request
新建一个工作流，与 `workflows/global/asset_storyboard_generation.workflow.yaml` 不同：需要额外输入已画好的分镜线稿，根据线稿和剧本生成提示词。生成的提示词使用特定格式（六步思维链分析 → `<think>` + `<caption>` 输出）。

### Interview Summary

**Key Discussions**:
- **视觉模型**: 新增 Gemini Provider（OpenAI 兼容 `/v1/chat/completions`），模型 `gemini-3-flash-preview`，仅用于视觉分析（看图生成描述），不用于图像生成
- **ChatMessage 扩展**: 将 `content: str` 改为 `content: str | list[dict[str, Any]]` 以支持多模态消息
- **线稿输入**: 程序按 `tool.script_split.v1` 拆分段落后，用户通过 `system.human_approval.v1` 为每个段落上传线稿 URL
- **工作流范围**: 完整版，复用现有 Phase A（资产提取+匹配）+ Phase B（资产图像获取），新增 Phase C（Gemini 视觉分析 → caption → RunningHub 图像生成）
- **输出**: `<think>` 丢弃，`<caption>` 作为分镜提示词传给 RunningHub 图像生成
- **测试策略**: TDD，每个任务先写测试 RED → 实现 GREEN → 重构 REFACTOR

**Research Findings**:
- 现有 `ChatMessage` 为 `frozen=True, slots=True` 的 dataclass，`content: str`
- `DeepSeekChatProvider` 使用 OpenAI SDK `AsyncOpenAI`，是 Gemini Provider 的标准参考模式
- 现有节点注册在 `xiagent/nodes/__init__.py` 的 `build_node_registry()`
- 测试基础设施: pytest + pytest-asyncio，`WorkflowTestBuilder` + `WorkflowTestRunner`
- 关键限制: DeepSeek provider 当前 `{"role": ..., "content": message.content}` 传递 content，需兼容 content 变为 list 的情况

### Metis Review

**Identified Gaps** (addressed):
- **ChatMessage 向后兼容**: 变化为 `content: str | list[dict[str, Any]]`。所有现有测试必须在变更前后都通过。DeepSeek provider 的 `message.content` 传递需验证两种类型都正确处理
- **`<think>+<caption>` 提取策略**: 新建 GeminiVisionNode 内置提取逻辑，处理标签缺失/格式异常/多 caption 等边界情况
- **线稿-段落映射**: human_approval 节点需严格要求输出 `segment_index` 字段，下游验证数量匹配
- **Gemini safety filter 处理**: 需处理 `finish_reason = "SAFETY"` 等情况
- **Context window 限制**: 可选的参考角色图像可能超 context，需截断策略

**Scope Creep Locks**:
- ❌ 不添加 streaming/function calling/Gemini 高级功能
- ❌ 不创建 workflow 组合/子工作流引用 — 在 YAML 中复制节点
- ❌ 不做线稿预处理（缩放/格式转换）
- ❌ 不做一批并行 Gemini 调用 — 先顺序处理
- ❌ 不将线稿存储为资产 — 仅作为 URL 传递

---

## Work Objectives

### Core Objective
创建完整的分镜线稿分析工作流：输入剧本 + 背景信息 + 分镜线稿草图 → 提取角色/场景/道具资产 → Gemini 视觉分析线稿生成中文描述 → RunningHub 根据描述生成最终图像。

### Concrete Deliverables
- `xiagent/models/types.py` — 扩展 ChatMessage，新增 GeminiModelConfig
- `xiagent/models/config.py` — 新增 Gemini 配置加载
- `xiagent/infrastructure/config.py` — 新增 Settings 字段
- `xiagent/models/local_config.example.toml` — 新增 `[gemini]` 节
- `xiagent/models/providers/gemini.py` — 新建 GeminiChatProvider
- `xiagent/nodes/ai/gemini_vision.py` — 新建 GeminiVisionNode
- `xiagent/nodes/__init__.py` — 注册 GeminiVisionNode
- `tests/test_chat_message.py` — ChatMessage 多模态测试
- `tests/test_gemini_provider.py` — Gemini Provider 测试
- `tests/test_gemini_vision_node.py` — GeminiVisionNode 测试
- `tests/test_workflow_storyboard_from_sketch.py` — 工作流集成测试
- `workflows/global/storyboard_from_sketch.workflow.yaml` — 新工作流定义

### Definition of Done
- [ ] `python -m pytest -q` — 所有测试通过（包括新测试 + 已有测试零回归）
- [ ] `python -m xiagent.workflows.testing_cli --workflow-id storyboard_from_sketch --input '{"script":"...", "background":"..."}'` — 工作流可加载执行
- [ ] Gemini 视觉分析生成可解析的 `<think>+<caption>` 输出
- [ ] `<caption>` 正确传入 RunningHub prompt assembler 并触发图像生成

### Must Have
- ChatMessage 多模态支持（向后兼容）
- Gemini Provider 正常工作（API key 验证、错误处理、mock 测试）
- GeminiVisionNode 正确处理有/无 `<caption>` 标签的输出
- 工作流 Phase A/B 与 `asset_storyboard_generation` 节点配置一致
- 工作流 Phase C 的线稿输入 → 视觉分析 → 图像生成链路完整

### Must NOT Have (Guardrails)
- ❌ 不修改现有 DeepSeek / RunningHub provider 行为
- ❌ 不修改现有 workflow YAML 文件
- ❌ 不修改 AssetService / UserService / RuntimeService 核心服务
- ❌ ChatMessage 不新增 image_url / file_url / audio_url 等独立字段
- ❌ Gemini Provider 不实现 streaming / function calling / grounding
- ❌ 不创建 workflow composition / sub-workflow 引用机制
- ❌ 不做线稿图片预处理（resize / format conversion）
- ❌ 不做并行 Gemini 调用（初始版本顺序处理）
- ❌ 不将线稿存储为 AssetService 资产
- ❌ 不引入新第三方依赖（仅使用已有的 `openai` SDK）

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest 8.0+, pytest-asyncio, WorkflowTestBuilder)
- **Automated tests**: TDD — 每个任务: RED（先写测试）→ GREEN（最小实现）→ REFACTOR
- **Framework**: pytest + pytest-asyncio（asyncio_mode = auto）

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Unit tests**: `python -m pytest tests/test_<module>.py -v` — verify individual components
- **Integration tests**: `WorkflowTestBuilder` + mock providers — verify data flow
- **CLI test**: `python -m xiagent.workflows.testing_cli` — verify end-to-end workflow loading
- **API/Library tests**: Bash (Python REPL) — import and call functions, compare output

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately - foundation, MAX PARALLEL):
├── Task 1: ChatMessage 多模态扩展 (TDD) [deep]
├── Task 2: GeminiModelConfig + Settings + load_model_config [quick]
├── Task 3: local_config.example.toml [quick]
└── Task 4: GeminiVisionNode prompt template [quick]

Wave 2 (After Wave 1 - provider, MAX PARALLEL):
├── Task 5: GeminiChatProvider 创建 (TDD) [deep]
└── Task 6: build_node_registry 准备 [quick]

Wave 3 (After Wave 2 - node, MAX PARALLEL):
├── Task 7: GeminiVisionNode 实现 (TDD) [deep]
└── Task 8: 注册 GeminiVisionNode 到 registry [quick]

Wave 4 (After Wave 3 - workflow):
└── Task 9: 工作流 YAML 创建 [unspecified-high]

Wave 5 (After Wave 4 - testing):
├── Task 10: 工作流集成测试 + CLI 测试 (TDD) [deep]
└── Task 11: 边界情况测试 [deep]

Wave FINAL (After ALL tasks):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

**Critical Path**: Task 1 → Task 5 → Task 7 → Task 9 → Task 10
**Parallel Speedup**: ~60% faster than sequential (Wave 1 runs 4 parallel; Waves 2-5 limited by inherent dependencies)
**Max Concurrent**: 4 (Wave 1)

### Dependency Matrix

- **1**: - - 5, 7
- **2**: - - 5
- **3**: - - 5
- **4**: - - 7
- **5**: 1, 2, 3 - 7
- **6**: 5 - 7
- **7**: 5, 4 - 9
- **8**: 7 - 9
- **9**: 8 - 10, 11
- **10**: 9 - F1-F4
- **11**: 9 - F1-F4

---

## TODOs

- [x] 1. ChatMessage 多模态扩展 (TDD)

  **What to do**:
  - RED: 写测试 `tests/test_chat_message.py`，验证:
    - `ChatMessage(role="user", content="text")` 仍正常工作
    - `ChatMessage(role="user", content=[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}])` 支持多模态
    - 现有 `test_model_router.py` 全部通过（向后兼容）
  - GREEN: 修改 `xiagent/models/types.py`:
    - 将 `ChatMessage.content` 类型从 `str` 改为 `str | list[dict[str, Any]]`
    - 同时添加 GeminiModelConfig dataclass（`frozen=True, slots=True`）：字段 `api_key: str | None`, `base_url: str`, `model: str`
    - 更新 `ModelConfig` 添加 `gemini: GeminiModelConfig` 字段（`field(default_factory=GeminiModelConfig)`）
  - REFACTOR: 检查所有构造 `ChatMessage` 的代码（共 7 处），确保兼容
  - 验证 `<caption>` 中包含「」代号时不被破坏

  **Must NOT do**:
  - 不要添加 `image_url` / `file_url` / `audio_url` 等独立字段到 ChatMessage
  - 不要修改 Content 为其他类型（如 `Union[str, List[ContentPart]]`），只使用 `str | list[dict[str, Any]]`
  - 不要改动 GeminiModelConfig 以外的任何 ModelConfig 字段

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解现有所有 ChatMessage 使用点，确保零回归修改
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `git-master`: 不需要 — 改动集中在 2 个文件

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: None (can start immediately)

  **References**:
  - `xiagent/models/types.py` — ChatMessage 当前定义（line 7-10），需修改 content 类型
  - `xiagent/models/config.py` — load_model_config() 添加 gemini 节（模仿 deepseek 和 runninghub 的 [section] 模式）
  - `xiagent/models/types.py` — DeepSeekModelConfig 和 RunningHubImageModelConfig 作为 GeminiModelConfig 参考模式（line 29-54）
  - `xiagent/models/providers/deepseek.py:38-43` — provider 中使用 message.content 的方式（`{"role": message.role, "content": message.content}`），此代码必须在 content 为 list 时也能工作
  - `xiagent/nodes/ai/deepseek_chat.py:64-65` — ChatMessage 构造示例
  - `xiagent/nodes/ai/deepseek_structured_json.py:75,151,153,154` — _system_messages 中的 ChatMessage 构造
  - `xiagent/nodes/ai/runninghub_image.py:74,208` — RunningHub 中的 ChatMessage 构造
  - `ast_grep_search` pattern: `ChatMessage($$$)` — 找到所有 ChatMessage 构造点

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_model_router.py -v` → ALL tests pass (zero regression)
  - [ ] `python -m pytest tests/test_chat_message.py -v` → ALL new tests pass
  - [ ] `ChatMessage(role="user", content="hello")` 仍正常工作
  - [ ] `ChatMessage(role="user", content=[{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "https://x.com/a.png"}}])` 正常工作
  - [ ] `python -m pytest -q` → 完整测试套件无回归

  **QA Scenarios**:

  ```
  Scenario: ChatMessage backward compatibility
    Tool: Bash (bun/python REPL)
    Preconditions: Python 3.11+, xiagent installed in dev mode
    Steps:
      1. Run: python -c "from xiagent.models.types import ChatMessage; msg = ChatMessage(role='user', content='hello'); assert msg.content == 'hello'; print('PASS')"
      2. Verify output: "PASS"
    Expected Result: Outputs "PASS", no errors
    Failure Indicators: TypeError, assertion error
    Evidence: .sisyphus/evidence/task-1-backward-compat.txt

  Scenario: ChatMessage multimodal content
    Tool: Bash (bun/python REPL)  
    Preconditions: Same as above
    Steps:
      1. Run: python -c "
  from xiagent.models.types import ChatMessage
  content = [{'type': 'text', 'text': 'Describe'}, {'type': 'image_url', 'image_url': {'url': 'https://example.com/test.png'}}]
  msg = ChatMessage(role='user', content=content)
  assert isinstance(msg.content, list)
  assert len(msg.content) == 2
  assert msg.content[0]['type'] == 'text'
  print('PASS')
  "
      2. Verify output: "PASS"
    Expected Result: Outputs "PASS", no errors
    Evidence: .sisyphus/evidence/task-1-multimodal.txt

  Scenario: Full test suite regression check
    Tool: Bash
    Preconditions: ChatMessage changed, all implementation complete
    Steps:
      1. Run: python -m pytest -q
      2. Verify exit code: 0
      3. Verify no test failures
    Expected Result: All existing tests pass (27 files, zero failures)
    Failure Indicators: Any FAILED test, non-zero exit code
    Evidence: .sisyphus/evidence/task-1-regression.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(models): extend ChatMessage for multimodal support`
  - Files: `xiagent/models/types.py`
  - Pre-commit: `python -m pytest tests/test_model_router.py -q`

- [x] 2. Gemini 模型配置集成

  **What to do**:
  - RED: 写测试验证 GeminiModelConfig 结构和默认值
  - GREEN:
    - 修改 `xiagent/infrastructure/config.py` — Settings dataclass 新增 `gemini_api_key`, `gemini_base_url`, `gemini_model` 字段
    - 修改 `xiagent/models/config.py` — `load_model_config()` 新增 `[gemini]` section 解析逻辑（参考 deepseek section 模式）
    - env var 优先级: `GEMINI_API_KEY`, `GEMINI_BASE_URL`, `GEMINI_MODEL`
    - 默认值: `base_url="https://generativelanguage.googleapis.com/v1beta/openai/"`, `model="gemini-3-flash-preview"`
  - REFACTOR: 确保 local_config.toml 中的值可被覆盖

  **Must NOT do**:
  - 不要修改 DeepSeek 或 RunningHub 的配置逻辑
  - 不要在 Settings 中添加非 Gemini 的字段

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 遵循已有模式添加配置，改动少量文件，低风险
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Task 5
  - **Blocked By**: None

  **References**:
  - `xiagent/infrastructure/config.py` — Settings dataclass，需新增 gemini 字段
  - `xiagent/models/config.py:63-73` — DeepSeek 配置加载模式（`_section(raw, "deepseek")` → env var override → default）
  - `xiagent/models/types.py:29-34` — DeepSeekModelConfig 模式参考
  - `xiagent/models/local_config.example.toml:1-4` — 现有 `[deepseek]` 节格式参考

  **Acceptance Criteria**:
  - [ ] `GeminiModelConfig()` 默认值正确：`base_url="https://generativelanguage.googleapis.com/v1beta/openai/"`, `model="gemini-3-flash-preview"`
  - [ ] `GEMINI_API_KEY` 环境变量优先级高于 `local_config.toml`
  - [ ] `GEMINI_MODEL` 环境变量可覆盖默认 model
  - [ ] `load_model_config()` 返回的 `ModelConfig.gemini` 非 None

  **QA Scenarios**:

  ```
  Scenario: Default config values
    Tool: Bash (Python REPL)
    Preconditions: No GEMINI_* env vars set
    Steps:
      1. Run: python -c "from xiagent.models.types import GeminiModelConfig; c = GeminiModelConfig(); print(f'model={c.model}, url={c.base_url}')"
      2. Verify: model=gemini-3-flash-preview, url contains generativelanguage
    Expected Result: Default values match spec
    Evidence: .sisyphus/evidence/task-2-defaults.txt

  Scenario: Env var override
    Tool: Bash
    Preconditions: None
    Steps:
      1. Set GEMINI_MODEL=gemini-2.5-pro
      2. Run: python -c "from xiagent.models.config import load_model_config; c = load_model_config(); print(c.gemini.model)"
      3. Verify output: gemini-2.5-pro
    Expected Result: Env var takes priority
    Failure Indicators: Still shows gemini-3-flash-preview
    Evidence: .sisyphus/evidence/task-2-env-override.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `feat(models): add Gemini model config`
  - Files: `xiagent/models/types.py`, `xiagent/models/config.py`, `xiagent/infrastructure/config.py`
  - Pre-commit: `python -m pytest -q`

- [x] 3. local_config.example.toml 模板更新

  **What to do**:
  - RED: 验证 example.toml 格式可被 `tomllib.loads()` 解析
  - GREEN: 在 `xiagent/models/local_config.example.toml` 末尾添加 `[gemini]` 节:
    ```toml
    [gemini]
    api_key = ""
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    model = "gemini-3-flash-preview"
    ```
  - REFACTOR: 确认注释说明清晰

  **Must NOT do**:
  - 不要包含真实 API key
  - 不要修改现有 `[deepseek]` / `[runninghub_image]` 节

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单文件追加配置，无逻辑改动
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Task 5 (provider 需要配置存在)
  - **Blocked By**: None

  **References**:
  - `xiagent/models/local_config.example.toml:1-4` — `[deepseek]` 节格式
  - `xiagent/models/config.py:63-73` — 确认 `_section(raw, "gemini")` 兼容 toml 格式
  - `xiagent/models/local_config.toml` — 实际配置文件（可能已存在，检查是否需要同步）

  **Acceptance Criteria**:
  - [ ] `tomllib.loads(Path("xiagent/models/local_config.example.toml").read_text())["gemini"]["model"]` 返回 `"gemini-3-flash-preview"`
  - [ ] `load_model_config()` 在无 `local_config.toml` 时使用 example.toml 作为 fallback... 不对，example 是模板。确保 `load_model_config()` 的行为不受影响
  - [ ] `.gitignore` 已排除 `local_config.toml`（已有，确认即可）

  **QA Scenarios**:

  ```
  Scenario: TOML format validation
    Tool: Bash
    Preconditions: File edited
    Steps:
      1. Run: python -c "import tomllib; from pathlib import Path; data = tomllib.loads(Path('xiagent/models/local_config.example.toml').read_text()); assert 'gemini' in data; print('model:', data['gemini']['model'])"
      2. Verify output: model: gemini-3-flash-preview
    Expected Result: TOML parses correctly, gemini section exists
    Failure Indicators: KeyError, toml parse error
    Evidence: .sisyphus/evidence/task-3-toml-validate.txt
  ```

  **Commit**: YES (groups with Tasks 1-2)
  - Message: `feat(config): add Gemini section to example config`
  - Files: `xiagent/models/local_config.example.toml`
  - Pre-commit: `python -c "import tomllib; tomllib.loads(open('xiagent/models/local_config.example.toml').read()); print('OK')"`

- [x] 4. GeminiVisionNode 提示词模板设计

  **What to do**:
  - 设计 Gemini 视觉分析的 system prompt + user prompt 模板，参考用户提供的六步思维链:
    - 第零步·漫画分格与布局
    - 第一步·色调与光照
    - 第二步·时间
    - 第三步·场景环境
    - 第四步·角色描述（使用「」代号）
    - 第五步·特效
  - 输出格式规范: `<think>详细分析过程</think><caption>整合后的流畅中文描述</caption>`
  - 规则约束: 禁止描述画风、不分段、只描述实际内容、按思维链输出
  - GREEN: 创建静态模板常量 `GEMINI_VISION_SYSTEM_PROMPT` 在 `xiagent/nodes/ai/gemini_vision.py`（仅模板部分）
  - 模板需包含: 世界背景上下文、剧本段落内容、角色资产参考信息

  **Must NOT do**:
  - 不要在此任务中实现节点逻辑（留给 Task 7）
  - 不要在模板中硬编码具体的角色名/场景名

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 7
  - **Blocked By**: None

  **References**:
  - 用户提供的 template_prompt（完整六步思维链）
  - `xiagent/nodes/ai/deepseek_structured_json.py:147-153` — _system_messages 模式参考
  - `workflows/global/asset_storyboard_generation.workflow.yaml:1266-1281` — describe_panels system prompt 风格参考

  **Acceptance Criteria**:
  - [ ] 模板包含全部六步思维链
  - [ ] 模板明确 `<think>...</think><caption>...</caption>` 输出格式
  - [ ] 模板包含占位符: `{background}`, `{segment_text}`, `{character_info}`

  **QA Scenarios**:

  ```
  Scenario: Template completeness check
    Tool: Bash
    Steps:
      1. python -c "from xiagent.nodes.ai.gemini_vision import GEMINI_VISION_SYSTEM_PROMPT; assert '第零步' in GEMINI_VISION_SYSTEM_PROMPT; assert '<caption>' in GEMINI_VISION_SYSTEM_PROMPT; print('OK')"
    Expected Result: Outputs "OK"
    Evidence: .sisyphus/evidence/task-4-template-checks.txt
  ```

  **Commit**: YES (groups with Tasks 1-3)
  - Message: `feat(nodes): add GeminiVisionNode prompt template`
  - Files: `xiagent/nodes/ai/gemini_vision.py` (skeleton with template)
  - Pre-commit: `python -c "from xiagent.nodes.ai.gemini_vision import GEMINI_VISION_SYSTEM_PROMPT; print('OK')"`

- [x] 5. GeminiChatProvider 创建 (TDD)

  **What to do**:
  - RED: 写测试 `tests/test_gemini_provider.py` 包含:
    - `test_gemini_provider_requires_api_key` — 无 API key 抛 `ValidationError`
    - `test_gemini_provider_sends_multimodal_messages` — 验证 multimodal ChatMessage 传给 API
    - `test_gemini_provider_handles_api_error` — mock API 错误抛 `ExternalServiceError`
    - `test_gemini_provider_client_factory_injection` — mock client 可注入
  - GREEN: 创建 `xiagent/models/providers/gemini.py`，`GeminiChatProvider` 继承 `ChatModelProvider`
  - `chat()` 使用 `AsyncOpenAI(api_key=config.api_key, base_url=config.base_url).chat.completions.create(model=request.model, messages=[{"role": m.role, "content": m.content} for m in request.messages], stream=False)`
  - REFACTOR: 确保与 `DeepSeekChatProvider` 代码结构一致

  **Must NOT do**:
  - 不实现 streaming / function calling

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 6)
  - **Blocks**: Task 7
  - **Blocked By**: Tasks 1, 2, 3

  **References**:
  - `xiagent/models/providers/deepseek.py` — 完整参考（60行）
  - `xiagent/models/providers/deepseek.py:38-43` — messages 构建模式
  - `xiagent/models/router.py:15-32` — ChatModelRouter
  - `xiagent/core/errors.py` — ValidationError, ExternalServiceError

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_gemini_provider.py -v` → ALL pass
  - [ ] 无 API key 抛 `ValidationError(code="gemini_api_key_missing")`
  - [ ] API 异常抛 `ExternalServiceError(code="gemini_request_failed")`
  - [ ] Mock 测试验证 multimodal content 正确传递

  **QA Scenarios**:

  ```
  Scenario: Provider rejects missing API key
    Tool: Bash
    Steps:
      1. python -c "import asyncio; from xiagent.models.types import GeminiModelConfig, ChatRequest, ChatMessage; from xiagent.models.providers.gemini import GeminiChatProvider; async def t(): provider = GeminiChatProvider(config=GeminiModelConfig(api_key=None)); await provider.chat(ChatRequest(provider='gemini', model='t', messages=[ChatMessage(role='user', content='hi')])); asyncio.run(t())"
    Expected Result: ValidationError raised
    Evidence: .sisyphus/evidence/task-5-no-api-key.txt
  ```

  **Commit**: YES
  - Message: `feat(models): add GeminiChatProvider`
  - Files: `xiagent/models/providers/gemini.py`
  - Pre-commit: `python -m pytest tests/test_gemini_provider.py -q`

- [x] 6. build_node_registry 准备

  **What to do**:
  - 在 `xiagent/nodes/__init__.py` 注册 GeminiChatProvider（跟随 DeepSeek/RunningHub 模式）
  - 在 `xiagent/nodes/ai/__init__.py` 预留 GeminiVisionNode 导出
  - 为 GeminiVisionNode 预留注册位置但不导入（Task 7 创建类）

  **Must NOT do**:
  - 不实现 GeminiVisionNode（留给 Task 7）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 5)
  - **Blocks**: Task 8
  - **Blocked By**: Task 5

  **References**:
  - `xiagent/nodes/__init__.py` — build_node_registry()
  - `xiagent/nodes/ai/__init__.py` — AI 节点导出

  **Acceptance Criteria**:
  - [ ] Gemini provider 注册代码存在
  - [ ] GeminiVisionNode 导出预留

  **QA Scenarios**:

  ```
  Scenario: Provider registration check
    Tool: Bash
    Steps:
      1. python -c "from xiagent.models.router import ChatModelRouter; from xiagent.models.providers.gemini import GeminiChatProvider; router = ChatModelRouter(); router.register_provider('gemini', GeminiChatProvider(config=...)); print('OK')"
    Expected Result: Outputs "OK"
    Evidence: .sisyphus/evidence/task-6-registration.txt
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `feat(nodes): register Gemini provider`
  - Files: `xiagent/nodes/__init__.py`, `xiagent/nodes/ai/__init__.py`

- [x] 7. GeminiVisionNode 实现 (TDD)

  **What to do**:
  - RED: 写测试 `tests/test_gemini_vision_node.py`:
    - `test_gemini_vision_node_rejects_empty_image_urls` — 空 `image_urls` 抛 `ValidationError`
    - `test_gemini_vision_node_rejects_empty_prompt` — 空 `prompt` 抛 `ValidationError`
    - `test_gemini_vision_node_extracts_caption` — mock 返回含 `<think>...<think><caption>描述</caption>` 的响应，验证输出提取正确
    - `test_gemini_vision_node_handles_missing_caption` — mock 返回无 `<caption>` 标签，验证 fallback 处理
    - `test_gemini_vision_node_handles_gemini_api_timeout` — mock API 超时
    - `test_gemini_vision_node_max_attempts_retry` — 验证 max_attempts 重试逻辑
  - GREEN: 在 `xiagent/nodes/ai/gemini_vision.py` 中实现 `GeminiVisionNode(BaseNode)`:
    - ref: `ai.gemini_vision.v1`
    - input_schema: `prompt` (str), `image_urls` (list[str]), `system` (str, optional), `max_attempts` (int, optional, default=1)
    - output_schema: `think` (str), `caption` (str), `model` (str), `usage` (dict)
    - `run()`: 构建 multimodal ChatMessage → 调用 model_router.chat() → 提取 `<think>` 和 `<caption>` → 返回 NodeResult
    - `<caption>` 提取逻辑: 正则 `r'<caption>\s*(.*?)\s*</caption>'`，未匹配时取全文作为 caption
    - `<think>` 提取逻辑: 正则 `r'<think>\s*(.*?)\s*</think>'`
    - `max_attempts` 重试：失败时追加 "Previous response failed..." 到 prompt
  - REFACTOR: 将与 `DeepSeekStructuredJsonNode` 类似的重试逻辑提取为共享模块（如果合适）

  **Must NOT do**:
  - 不要将 vision 分析结果存入数据库
  - 不要在 node 中做线稿预处理

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要异步 API 调用 + XML 标签解析 + 重试逻辑 + mock 测试
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 8)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 5, 4 (provider + template)

  **References**:
  - `xiagent/nodes/ai/deepseek_structured_json.py` — 完整的重试 + 解析 + schema 验证模式（154行）
  - `xiagent/nodes/ai/deepseek_structured_json.py:53-128` — `run()` 方法的 try-except-retry 模式
  - `xiagent/nodes/ai/deepseek_structured_json.py:131-143` — `_parse_json_object()` 正则解析模式（类比 XML 标签解析）
  - `xiagent/nodes/base.py:52-59` — BaseNode ABC（describe() + run()）
  - `xiagent/models/types.py:7-10` — ChatMessage（已扩展支持 multimodal）
  - `xiagent/models/types.py:13-18` — ChatRequest 结构

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_gemini_vision_node.py -v` → ALL pass
  - [ ] `GeminiVisionNode.describe().ref == "ai.gemini_vision.v1"`
  - [ ] 有效响应正确提取 `<think>` 和 `<caption>`
  - [ ] 缺失 `<caption>` 时 fallback 到全文
  - [ ] `max_attempts=2` 时第一次失败自动重试第二次
  - [ ] 空 `image_urls` 抛 `ValidationError`

  **QA Scenarios**:

  ```
  Scenario: Node rejects empty image_urls
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_gemini_vision_node.py::test_gemini_vision_node_rejects_empty_image_urls -v
    Expected Result: PASSED
    Evidence: .sisyphus/evidence/task-7-empty-urls.txt

  Scenario: Node extracts caption from valid response
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_gemini_vision_node.py::test_gemini_vision_node_extracts_caption -v
    Expected Result: PASSED — caption extracted correctly from mock
    Evidence: .sisyphus/evidence/task-7-extract-caption.txt
  ```

  **Commit**: YES
  - Message: `feat(nodes): add GeminiVisionNode`
  - Files: `xiagent/nodes/ai/gemini_vision.py`
  - Pre-commit: `python -m pytest tests/test_gemini_vision_node.py -q`

- [x] 8. 注册 GeminiVisionNode 到 build_node_registry

  **What to do**:
  - 在 `xiagent/nodes/__init__.py` 的 `build_node_registry()` 中正式注册 GeminiVisionNode:
    - 创建 `GeminiVisionNode(model_router=chat_router, provider="gemini", model=model_config.gemini.model)`
    - 调用 `registry.register(node)`
  - 更新 `xiagent/nodes/ai/__init__.py` 导出 `GeminiVisionNode`
  - 确保 `workflow` 加载时 `ai.gemini_vision.v1` 可用

  **Must NOT do**:
  - 不要修改其他节点的注册逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 在已有 registry 添加一行注册代码
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 7)
  - **Blocks**: Task 9
  - **Blocked By**: Task 7

  **References**:
  - `xiagent/nodes/__init__.py` — build_node_registry()，观察 DeepSeekStructuredJsonNode 注册模式
  - `xiagent/nodes/ai/__init__.py` — 导出列表

  **Acceptance Criteria**:
  - [ ] `registry.get("ai.gemini_vision.v1")` 返回 GeminiVisionNode 实例
  - [ ] workflow validator 识别 `ai.gemini_vision.v1` 为有效 ref
  - [ ] `python -c "from xiagent.nodes import build_node_registry; r = build_node_registry(...); node = r.get('ai.gemini_vision.v1'); print(node.describe().ref)"` → 输出 `ai.gemini_vision.v1`

  **QA Scenarios**:

  ```
  Scenario: Node is registered and retrievable
    Tool: Bash
    Steps:
      1. python -c "
  from xiagent.nodes import build_node_registry
  from xiagent.models.router import ChatModelRouter
  from xiagent.models.types import ModelConfig
  mc = ModelConfig()
  cr = ChatModelRouter()
  reg = build_node_registry(chat_router=cr, model_config=mc, ...)
  node = reg.get('ai.gemini_vision.v1')
  print('REF:', node.describe().ref)
  "
    Expected Result: REF: ai.gemini_vision.v1
    Evidence: .sisyphus/evidence/task-8-node-registered.txt
  ```

  **Commit**: YES (groups with Task 7)
  - Message: `feat(nodes): register GeminiVisionNode`
  - Files: `xiagent/nodes/__init__.py`, `xiagent/nodes/ai/__init__.py`
  - Pre-commit: `ruff check xiagent/nodes/`

- [x] 9. 工作流 YAML 创建

  **What to do**:
  - RED: 写测试验证 workflow YAML 可被 `load_workflow_file()` 加载且通过 `validate_workflow_contract()` 校验
  - GREEN: 创建 `workflows/global/storyboard_from_sketch.workflow.yaml`:
    - `workflow.id`: `storyboard_from_sketch`，scope: `global`
    - `input_schema`: `script` (str), `background` (str), `generate_assets` (enum: 手动上传/自动生成), `template_image_url` (str, optional), `storyboard_target` (object, optional)
    - **Phase A nodes**（复用 asset_storyboard_generation 配置）:
      - `extract_characters` → `lookup_existing_assets` → `match_by_name` → `semantic_match_characters` → `enrich_characters` → `match_variants` → `check_accessories`
      - `extract_scenes` / `extract_props`（并行，同 asset_storyboard_generation）
    - **Phase B nodes**（复用）:
      - `review_assets`（human_approval，审核资产匹配）
      - 条件分支: `generate_prompt_v2` / `upload_images` → `generate_asset_images_v2` / `merge_asset_images`
    - **Phase C nodes**（新）:
      - `split_script`（复用 tool.script_split.v1）
      - `upload_line_art`（human_approval，让用户为每个段落上传线稿URL，输出 `{segment_images: [{segment_index: 0, image_url: "https://..."}]}` ）
      - `gemini_vision_analysis`（新 ai.gemini_vision.v1，输入: segments + line_art_images + background）
      - `extract_captions`（从 Gemini 输出提取 caption）
      - `assemble_storyboard_prompt_v3`（装配 caption → 最终 prompt）
      - `generate_storyboard_image`（RunningHub 生成图像）
      - `review_storyboard_image`（human_approval）
    - `edges`: 定义完整 DAG，包含条件分支（`when: {path: "$workflow.input.generate_assets", equals: "手动上传/自动生成"}`）
  - REFACTOR: 确保 YAML 结构与现有 pattern 一致

  **Must NOT do**:
  - 不创建 `assemble_storyboard_prompt_v3` 新工具节点（使用现有 `tool.storyboard_prompt_assembler.v2` 如果兼容）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 复杂 YAML 编写，约 500-800 行，需仔细复制现有 node 配置 + 新增 Phase C
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (solo)
  - **Blocks**: Tasks 10, 11
  - **Blocked By**: Task 8 (node registered)

  **References**:
  - `workflows/global/asset_storyboard_generation.workflow.yaml` — Phase A + B node 配置完整参考（lines 1-1700）
  - `workflows/global/asset_storyboard_generation.workflow.yaml:50-141` — Phase A 节点（extract_characters 到 check_accessories）
  - `workflows/global/asset_storyboard_generation.workflow.yaml:875-981` — Phase B 审核 + 上传节点
  - `workflows/global/asset_storyboard_generation.workflow.yaml:1632-1700` — edges 参考
  - `workflows/global/storyboard_generation.workflow.yaml` — 简化版 edges（DAG 结构参考，lines 445-463）

  **Acceptance Criteria**:
  - [ ] YAML 文件存在且格式有效
  - [ ] `load_workflow_file(Path("workflows/global/storyboard_from_sketch.workflow.yaml"))` 成功
  - [ ] `validate_workflow_contract(contract, registry)` 通过（所有 node ref 被识别，edges DAG 有效）
  - [ ] Phase A/B 节点配置与 `asset_storyboard_generation` 保持一致性
  - [ ] `ai.gemini_vision.v1` 节点有正确配置（inputs/outputs schema）
  - [ ] human_approval 节点有正确的 `question` 模板
  - [ ] 条件分支 edges 正确

  **QA Scenarios**:

  ```
  Scenario: Workflow YAML loads and validates
    Tool: Bash
    Steps:
      1. python -c "
  from pathlib import Path
  from xiagent.workflows.loader import load_workflow_file
  from xiagent.workflows.validator import validate_workflow_contract
  from xiagent.nodes import build_node_registry
  from xiagent.models.router import ChatModelRouter
  from xiagent.models.types import ModelConfig
  mc = ModelConfig()
  cr = ChatModelRouter()
  reg = build_node_registry(chat_router=cr, model_config=mc, asset_service=None)
  contract = load_workflow_file(Path('workflows/global/storyboard_from_sketch.workflow.yaml'))
  validate_workflow_contract(contract, reg)
  print('VALID')
  "
      2. Verify output: VALID
    Expected Result: VALID (no errors)
    Failure Indicators: ValidationError, NotFoundError
    Evidence: .sisyphus/evidence/task-9-workflow-valid.txt
  ```

  **Commit**: YES
  - Message: `feat(workflows): add storyboard_from_sketch workflow`
  - Files: `workflows/global/storyboard_from_sketch.workflow.yaml`
  - Pre-commit: `python -c "from xiagent.workflows.loader import load_workflow_file; load_workflow_file('workflows/global/storyboard_from_sketch.workflow.yaml'); print('OK')"`

- [x] 10. 工作流集成测试 + CLI 测试 (TDD)

  **What to do**:
  - RED: 写测试 `tests/test_workflow_storyboard_from_sketch.py`:
    - `test_workflow_loads_and_validates` — workflow 加载 + 校验通过
    - `test_workflow_full_pipeline_with_mocks` — 使用 `WorkflowTestBuilder` + mock providers 执行完整工作流
    - `test_cli_accepts_workflow_id` — `python -m xiagent.workflows.testing_cli --workflow-id storyboard_from_sketch --input '{"script":"...", "background":"..."}'` 正常执行
    - `test_workflow_gemini_vision_called` — 验证 Phase C 中 gemini_vision 节点被调用
  - GREEN: 实现集成测试（采用 builder → build → run 模式，mock providers 注入）
  - 使用 mock `ChatModelProvider` 返回预设的 `<think>分析</think><caption>描述文本</caption>`
  - 使用 mock RunningHub provider 返回预设的图像 URL
  - REFACTOR: 提取共享的 mock fixtures

  **Must NOT do**:
  - 不要在集成测试中使用真实的 Gemini/RunningHub API key
  - 不在测试中做真实网络调用

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解 WorkflowTestBuilder + mock provider 注入 + 完整工作流执行
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Task 11)
  - **Blocks**: None (final wave)
  - **Blocked By**: Task 9 (workflow YAML)

  **References**:
  - `xiagent/workflows/testing/builder.py` — WorkflowTestBuilder（155行）
  - `xiagent/workflows/testing/runner.py` — WorkflowTestRunner（239行）
  - `xiagent/workflows/testing_cli.py` — CLI 入口（130行）
  - `tests/test_workflow_testing_runner.py` — 已有 workflow 测试模式参考
  - `tests/test_runtime_service.py` — 自定义 probe node 模式（可参考用于 mock）

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_workflow_storyboard_from_sketch.py -v` → ALL pass
  - [ ] Integration test 覆盖完整工作流（Phase A → B → C）
  - [ ] Mock Gemini provider 返回的 `<caption>` 正确流向 RunningHub
  - [ ] CLI 测试通过：`python -m xiagent.workflows.testing_cli --workflow-id storyboard_from_sketch --input '{"script":"test", "background":"test"}'` 返回 exit code 0

  **QA Scenarios**:

  ```
  Scenario: Full workflow execution with mocks
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_workflow_storyboard_from_sketch.py::test_workflow_full_pipeline_with_mocks -v
    Expected Result: PASSED — workflow runs start to end with mock providers
    Evidence: .sisyphus/evidence/task-10-integration.txt

  Scenario: CLI accepts workflow id
    Tool: Bash
    Steps:
      1. Run: python -m xiagent.workflows.testing_cli --workflow-id storyboard_from_sketch --input '{"script":"测试剧本\\n\\n第二段", "background":"武侠世界"}'
      2. Verify: exit code 0
    Expected Result: Workflow executes successfully
    Evidence: .sisyphus/evidence/task-10-cli-test.txt
  ```

  **Commit**: YES
  - Message: `test: add workflow integration tests for storyboard_from_sketch`
  - Files: `tests/test_workflow_storyboard_from_sketch.py`
  - Pre-commit: `python -m pytest tests/test_workflow_storyboard_from_sketch.py -q`

- [x] 11. 边界情况测试

  **What to do**:
  - RED: 写边界情况测试:
    - `test_workflow_rejects_empty_script` — 空 script 输入 → 清晰错误
    - `test_workflow_handles_zero_segments` — script 拆分出 0 段 → 正确处理
    - `test_workflow_line_art_count_mismatch` — 线稿数 ≠ 段落数 → 错误
    - `test_gemini_vision_handles_safety_block` — mock Gemini 返回 `finish_reason: "SAFETY"` → 正确处理
    - `test_gemini_vision_handles_empty_response` — Gemini 返回空 content → fallback
    - `test_gemini_vision_handles_malformed_xml` — `<captio>` 拼写错误 → 提取失败 fallback
    - `test_workflow_with_max_segments` — 大量段落（如 20+）→ 不超时
    - `test_chat_message_backward_compat_in_provider` — DeepSeek provider 收到 multimodal ChatMessage → 不崩溃
  - GREEN: 实现对应的错误处理和验证逻辑:
    - script_split 后验证 count > 0
    - human_approval 输出后验证 segment_images 数量 == segments 数量
    - 处理 Gemini safety_block 响应
    - `<caption>` 提取时容错常见拼写错误
  - REFACTOR: 提取共享的验证工具函数

  **Must NOT do**:
  - 不要在边界测试中使用真实 API

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解多个组件的边界行为和错误处理策略
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Task 10)
  - **Blocks**: None
  - **Blocked By**: Task 9

  **References**:
  - `xiagent/core/errors.py` — ValidationError, ExternalServiceError 定义
  - `xiagent/workflows/validator.py` — workflow 校验逻辑
  - `xiagent/nodes/ai/deepseek_structured_json.py:115-121` — 重试时的错误消息追加模式

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_workflow_storyboard_from_sketch.py -v` → 所有边缘用例 PASS
  - [ ] 空 script 抛清晰错误（不崩）
  - [ ] 线稿段落数不匹配时抛验证错误
  - [ ] safety block 正确处理（不抛未处理异常）
  - [ ] XML 标签容错提取（拼写错误仍能提取）

  **QA Scenarios**:

  ```
  Scenario: Empty script produces clear error
    Tool: Bash
    Steps:
      1. python -c "
  import asyncio
  from pathlib import Path
  from xiagent.workflows.loader import load_workflow_file
  # load and attempt run with empty script
  contract = load_workflow_file(Path('workflows/global/storyboard_from_sketch.workflow.yaml'))
  print('Contract loaded, input_schema:', contract['workflow']['input_schema']['required'])
  "
    Expected Result: input_schema shows 'script' is required
    Evidence: .sisyphus/evidence/task-11-empty-script.txt

  Scenario: Malformed XML tag extraction
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_workflow_storyboard_from_sketch.py::test_gemini_vision_handles_malformed_xml -v
    Expected Result: PASSED — caption extracted despite malformed tags
    Evidence: .sisyphus/evidence/task-11-malformed-xml.txt
  ```

  **Commit**: YES
  - Message: `test: add edge case tests for storyboard_from_sketch`
  - Files: `tests/test_workflow_storyboard_from_sketch.py` (追加)
  - Pre-commit: `python -m pytest tests/test_workflow_storyboard_from_sketch.py -q`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
- [x] F2. **Code Quality Review** — `unspecified-high`
- [x] F3. **Real Manual QA** — `unspecified-high` (+ playwright if UI)
- [x] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **Wave 1**: `feat(models): extend ChatMessage for multimodal support` — types.py, config.py, settings
- **Wave 2**: `feat(models): add GeminiChatProvider` — providers/gemini.py, types.py
- **Wave 3**: `feat(nodes): add GeminiVisionNode` — nodes/ai/gemini_vision.py, nodes/__init__.py
- **Wave 4**: `feat(workflows): add storyboard_from_sketch workflow` — workflows/global/
- **Wave 5**: `test: add integration and edge case tests` — tests/

---

## Success Criteria

### Verification Commands
```bash
# ChatMessage backward compatibility
python -m pytest tests/test_model_router.py -v

# Gemini provider unit tests
python -m pytest tests/test_gemini_provider.py -v

# GeminiVisionNode unit tests
python -m pytest tests/test_gemini_vision_node.py -v

# Full test suite (no regressions)
python -m pytest -q

# Workflow loading validation
python -m xiagent.workflows.testing_cli --workflow-id storyboard_from_sketch --validate

# Lint check
ruff check .
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All 11 implementation tasks complete
- [ ] All F1-F4 verification tasks APPROVE
- [ ] All existing tests pass (zero regression)
- [ ] Workflow loads and validates successfully
