# Gemini Vision 图像识别 → RunningHub LLM 代理迁移

## TL;DR

> **Quick Summary**：将 storyboard_from_sketch 工作流中的 Gemini Vision 图像识别节点的底层 API 从 Google 直连切换到 RunningHub LLM 代理，复用现有 RunningHub API Key，零节点逻辑修改、零工作流 YAML 改动。
>
> **Deliverables**：
> - `[runninghub_llm]` 配置段（TOML + env var 支持）
> - 新 `RunningHubLLMChatProvider`（通用 OpenAI 兼容提供者）
> - `GeminiVisionNode` 改用 `runninghub_llm` provider
> - 保留现有 gemini 测试 + 新增 runninghub_llm 测试
>
> **Estimated Effort**：Quick（纯配置 + 注册改动，约 8 个文件）
> **Parallel Execution**：YES - 2 waves
> **Critical Path**：Task 1 → Task 3 → Task 5 → Task 7 → Task 9

---

## Context

### Original Request
用户发现 RunningHub 也提供 Gemini 模型的 LLM 代理接口（`https://llm.runninghub.ai/v1`），要求将工作流中识别分镜线稿的节点从 Google 直连切换为 RunningHub 代理，复用已有的 RunningHub API Key，并在 config 中添加对应配置。

### Interview Summary
**Key Discussions**：
- 确认 RunningHub LLM 代理支持多模态（image_url 格式）
- 确认当前架构：`GeminiVisionNode` → `ChatModelRouter` → `GeminiChatProvider` → Google OpenAI 兼容端点
- `GeminiChatProvider` 本质是通用 OpenAI 客户端，可直接复用（或同名复制）给 RunningHub
- `GeminiVisionNode` 是 provider 无关的——只需改注册时的 provider 名

**用户决策**：
- 保留 `GeminiChatProvider` 类（零成本），但不保留 `[gemini]` 配置段（原本就不存在于 `local_config.toml`）
- API Key 采用显式填写（不依赖自动回退到 `RUNNINGHUB_API_KEY`）
- 测试策略：保留现有 gemini 测试 + 新增 runninghub_llm 测试
- 不修改工作流 YAML（保持 `ref="ai.gemini_vision.v1"` 向后兼容）

**Research Findings**：
- `local_config.toml` 实际只有 `[deepseek]`、`[runninghub_image]`、`[runninghub_text_to_image]` 三段，无 `[gemini]` 段
- `GeminiChatProvider.chat()` 只访问 `config.api_key` 和 `config.base_url`，与具体配置类型解耦
- 现有 RunningHub 已有跨段 key 回退模式（`runninghub_text_to_image` → `RUNNINGHUB_API_KEY` → `runninghub_image`），但用户选择不复用此模式
- 修改涉及 7 层纵向切片：TOML → types.py → config.py → infrastructure/config.py → provider → node 注册 → tests

### Metis Review
**Identified Gaps**（addressed）：
- `ModelConfig` 容器 dataclass 需新增 `runninghub_llm` 字段 → 已纳入任务
- 需新增错误码 `runninghub_llm_api_key_missing` / `runninghub_llm_request_failed` → 已纳入
- `.env.example` 缺少 Gemini 相关变量，本次顺带补上 `RUNNINGHUB_LLM_API_KEY` → 已纳入
- 关键设计决策：key 复用策略 → 用户选择显式填写

**Metis 指令吸收**：
- 不修改 `GeminiVisionNode`（gemini_vision.py）
- 不修改 `ChatModelRouter` 内部
- 不修改任何工作流 YAML
- 不创建新节点类——复用 `GeminiVisionNode` 不同构造参数
- 遵循现有 7 层纵向切片模式

---

## Work Objectives

### Core Objective
将 `GeminiVisionNode` 的底层 API 调用从 Google Gemini 直连切换到 RunningHub LLM 代理，通过纯配置 + 注册改动实现，复用 RunningHub API Key。

### Concrete Deliverables
- `xiagent/models/types.py`：新增 `RunningHubLLMModelConfig` + 更新 `ModelConfig` 容器
- `xiagent/models/config.py`：新增 `[runninghub_llm]` 配置加载 + 环境变量支持
- `xiagent/models/providers/runninghub.py`：新增 `RunningHubLLMChatProvider`
- `xiagent/infrastructure/config.py`：`Settings` 新增 `runninghub_llm_*` 字段
- `xiagent/models/local_config.toml`：新增 `[runninghub_llm]` 段
- `xiagent/models/local_config.example.toml`：同上
- `xiagent/nodes/__init__.py`：注册 `runninghub_llm` provider + 更新 `GeminiVisionNode` 注册
- `.env.example`：新增 `RUNNINGHUB_LLM_API_KEY` 变量
- `tests/conftest.py`：`test_settings` fixture 新增字段
- `tests/`：新增 `test_runninghub_llm_provider.py`

### Definition of Done
- [ ] `python -m pytest -q` 全部通过（含新测试）
- [ ] `[runninghub_llm]` 段缺 key 时 `GeminiVisionNode` 抛出清晰错误
- [ ] 现有 `test_gemini_provider.py` 和 `test_gemini_vision_node.py` 无回归
- [ ] `storyboard_from_sketch` 工作流测试通过（mock 模式）

### Must Have
- `[runninghub_llm]` 配置段，包含 `api_key`、`base_url`、`model` 三个字段
- 环境变量 `RUNNINGHUB_LLM_API_KEY`、`RUNNINGHUB_LLM_BASE_URL`、`RUNNINGHUB_LLM_MODEL` 支持
- `GeminiVisionNode` 注册改用 `provider="runninghub_llm"`
- 错误码 `runninghub_llm_api_key_missing`、`runninghub_llm_request_failed`

### Must NOT Have (Guardrails)
- 不修改 `GeminiVisionNode`（`gemini_vision.py`）——已证实 provider 无关
- 不修改 `ChatModelRouter` 内部逻辑
- 不修改任何工作流 YAML 文件
- 不创建新的节点类——复用 `GeminiVisionNode`
- 不添加 provider 间自动回退/重试逻辑
- 不添加 `[gemini]` 配置段到 `local_config.toml`（原本就不存在）
- 不移除 `GeminiChatProvider` 类（零成本保留）

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**：YES（pytest）
- **Automated tests**：Tests-after（保留现有 + 新增）
- **Framework**：pytest

### QA Policy
每任务包含 Agent-Executed QA Scenarios。前端/CLI 场景极少（纯后端配置改动），主要用 `bash` 验证。

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1（立即开始 — 基础配置层，MAX PARALLEL）：
├── Task 1: types.py — 新增 RunningHubLLMModelConfig + 更新 ModelConfig [quick]
├── Task 2: config.py — 加载 [runninghub_llm] 配置 [quick]
├── Task 3: infrastructure/config.py — Settings 新增字段 [quick]
├── Task 4: 配置文件 — local_config.toml/example.toml/.env.example [quick]
└── Task 5: 创建 RunningHubLLMChatProvider [quick]

Wave 2（依赖 Wave 1 — 注册层 + 测试）：
├── Task 6: nodes/__init__.py — 注册 provider + 更新节点 [quick]
├── Task 7: conftest.py — 更新 test_settings fixture [quick]
├── Task 8: 新增 test_runninghub_llm_provider.py [unspecified-low]
└── Task 9: 全量回归测试 + QA 验证 [unspecified-low]

Critical Path: Task 1 → Task 5 → Task 6 → Task 9
Max Concurrent: 5 (Wave 1)
```

### Agent Dispatch Summary
- **Wave 1**：5 - T1-T5 → `quick`
- **Wave 2**：4 - T6-T9 → `quick` / `unspecified-low`

---

## TODOs

- [ ] 1. types.py — 新增 `RunningHubLLMModelConfig` + 更新 `ModelConfig` 容器

  **What to do**：
  - 在 `xiagent/models/types.py` 中新增 `RunningHubLLMModelConfig` 数据类：
    ```python
    @dataclass(frozen=True, slots=True)
    class RunningHubLLMModelConfig:
        api_key: str | None = None
        base_url: str = "https://llm.runninghub.ai/v1"
        model: str = "google/gemini-3-flash-preview"
    ```
  - 在 `ModelConfig` 容器中新增字段：
    ```python
    runninghub_llm: RunningHubLLMModelConfig = field(default_factory=RunningHubLLMModelConfig)
    ```

  **Must NOT do**：
  - 不修改任何已有 config 类
  - 不修改 `GeminiModelConfig` 类

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 2, 3, 4, 5）
  - **Blocks**：Task 5, Task 6
  - **Blocked By**：None

  **References**：
  - `xiagent/models/types.py:75-78` — `GeminiModelConfig` 模式参考（同结构：api_key, base_url, model）
  - `xiagent/models/types.py:82-93` — `ModelConfig` 容器参考（如何添加新字段）

  **Acceptance Criteria**：
  - [ ] `RunningHubLLMModelConfig` 类定义存在，三个字段（api_key, base_url, model）均有默认值
  - [ ] `ModelConfig` 容器包含 `runninghub_llm` 字段

  **QA Scenarios**：

  ```
  Scenario: 导入新类型成功
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.models.types import RunningHubLLMModelConfig; c = RunningHubLLMModelConfig(); assert c.base_url == 'https://llm.runninghub.ai/v1'"
    Expected Result: 退出码 0，无异常
    Evidence: .sisyphus/evidence/task-1-import.txt

  Scenario: ModelConfig 包含 runninghub_llm 字段
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.models.types import ModelConfig; m = ModelConfig(); assert hasattr(m, 'runninghub_llm')"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-1-modelconfig.txt
  ```

  **Commit**：YES（groups with Task 2）
  - Message：`feat(models): add RunningHubLLMModelConfig for LLM proxy`
  - Files：`xiagent/models/types.py`

- [ ] 2. config.py — 加载 `[runninghub_llm]` 配置

  **What to do**：
  - 在 `xiagent/models/config.py` 的 `load_model_config()` 中：
    1. 添加 `_section(raw, "runninghub_llm")` 解析 TOML 段
    2. 从 section 读取 `api_key`、`base_url`、`model`（跟现有 `[gemini]` 段相同的模式）
    3. 添加环境变量覆盖：`RUNNINGHUB_LLM_API_KEY`、`RUNNINGHUB_LLM_BASE_URL`、`RUNNINGHUB_LLM_MODEL`
    4. 在 `ModelConfig(...)` 构造中传入 `runninghub_llm=RunningHubLLMModelConfig(...)`

  **Must NOT do**：
  - 不添加 key 自动回退逻辑（用户选择显式填写）
  - 不删除现有 `[gemini]` 段加载代码

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 3, 4, 5）
  - **Blocks**：Task 6（通过 Settings 间接）
  - **Blocked By**：Task 1

  **References**：
  - `xiagent/models/config.py:68-69` — `_section(raw, "gemini")` 模式参考
  - `xiagent/models/config.py:208-214` — Gemini API key 加载 + env var 覆盖模式（完全照搬）
  - `xiagent/models/config.py:254-258` — `ModelConfig(gemini=...)` 构造模式

  **Acceptance Criteria**：
  - [ ] `[runninghub_llm]` 段从 TOML 正确解析
  - [ ] `RUNNINGHUB_LLM_API_KEY` 环境变量覆盖 TOML 值
  - [ ] `load_model_config()` 返回的 `ModelConfig` 包含完整的 `runninghub_llm` 字段

  **QA Scenarios**：

  ```
  Scenario: TOML 配置加载成功
    Tool: Bash (python -c)
    Preconditions: local_config.toml 包含 [runninghub_llm] 段（由 Task 4 创建）
    Steps:
      1. python -c "from xiagent.models.config import load_model_config; c = load_model_config(); assert c.runninghub_llm.base_url == 'https://llm.runninghub.ai/v1'"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-2-toml-load.txt

  Scenario: 环境变量覆盖 TOML
    Tool: Bash (PowerShell)
    Steps:
      1. $env:RUNNINGHUB_LLM_BASE_URL = "https://custom.proxy/v1"
      2. python -c "from xiagent.models.config import load_model_config; c = load_model_config(); assert c.runninghub_llm.base_url == 'https://custom.proxy/v1'"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-2-env-override.txt
  ```

  **Commit**：YES（groups with Task 1）
  - Message：`feat(models): add RunningHubLLMModelConfig for LLM proxy`
  - Files：`xiagent/models/config.py`

- [ ] 3. infrastructure/config.py — `Settings` 新增 `runninghub_llm_*` 字段

  **What to do**：
  - 在 `xiagent/infrastructure/config.py` 的 `Settings` dataclass 中新增 3 个字段：
    ```python
    runninghub_llm_api_key: str | None
    runninghub_llm_base_url: str
    runninghub_llm_model: str
    ```
  - 在 `load_settings()` 中从 `model_config.runninghub_llm` 映射值：
    ```python
    runninghub_llm_api_key=model_config.runninghub_llm.api_key,
    runninghub_llm_base_url=model_config.runninghub_llm.base_url,
    runninghub_llm_model=model_config.runninghub_llm.model,
    ```

  **Must NOT do**：
  - 不修改已有字段
  - 不添加 key 回退逻辑

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 2, 4, 5）
  - **Blocks**：Task 6
  - **Blocked By**：Task 1

  **References**：
  - `xiagent/infrastructure/config.py:30-32` — `gemini_api_key/base_url/model` 字段声明模式
  - `xiagent/infrastructure/config.py:76-78` — `model_config.gemini.*` 映射模式

  **Acceptance Criteria**：
  - [ ] `Settings` 包含 `runninghub_llm_api_key`、`runninghub_llm_base_url`、`runninghub_llm_model` 三个字段
  - [ ] `load_settings()` 正确从 `ModelConfig` 映射

  **QA Scenarios**：

  ```
  Scenario: Settings 包含 runninghub_llm 字段
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.infrastructure.config import load_settings; s = load_settings(); assert hasattr(s, 'runninghub_llm_base_url')"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-3-settings.txt
  ```

  **Commit**：YES
  - Message：`feat(infra): add runninghub_llm fields to Settings`
  - Files：`xiagent/infrastructure/config.py`

- [ ] 4. 配置文件更新 — TOML + example + .env.example

  **What to do**：
  1. 在 `xiagent/models/local_config.toml` 末尾新增 `[runninghub_llm]` 段，显式填写 RunningHub API Key：
     ```toml
     [runninghub_llm]
     api_key = "a85a043bd2bc4f36aad7e23021c7a894"
     base_url = "https://llm.runninghub.ai/v1"
     model = "google/gemini-3-flash-preview"
     ```
  2. 在 `xiagent/models/local_config.example.toml` 末尾新增同样结构但 `api_key = ""`（空值占位）
  3. 在 `.env.example` 末尾新增：
     ```
     RUNNINGHUB_LLM_API_KEY=
     RUNNINGHUB_LLM_BASE_URL=https://llm.runninghub.ai/v1
     RUNNINGHUB_LLM_MODEL=google/gemini-3-flash-preview
     ```

  **Must NOT do**：
  - 不新增 `[gemini]` 段
  - 不删除已有配置段

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 2, 3, 5）
  - **Blocks**：Task 6（间接，配置需先就位以便验证）
  - **Blocked By**：None

  **References**：
  - `xiagent/models/local_config.toml:1-20` — 现有配置结构
  - `xiagent/models/local_config.example.toml:26-29` — `[gemini]` 段模板格式（照搬结构）
  - `.env.example:5-7` — DEEPSEEK 环境变量格式

  **Acceptance Criteria**：
  - [ ] `local_config.toml` 末尾有 `[runninghub_llm]` 段，api_key 不为空
  - [ ] `local_config.example.toml` 末尾有 `[runninghub_llm]` 段，api_key 为空字符串
  - [ ] `.env.example` 末尾有 `RUNNINGHUB_LLM_*` 三行

  **QA Scenarios**：

  ```
  Scenario: local_config.toml runninghub_llm 段可解析
    Tool: Bash (python -c)
    Steps:
      1. python -c "import tomllib; d = tomllib.loads(open('xiagent/models/local_config.toml','rb').read()); assert 'runninghub_llm' in d; assert d['runninghub_llm']['api_key'] != ''"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-4-config-parse.txt

  Scenario: local_config.example.toml runninghub_llm 段存在且 api_key 为空
    Tool: Bash (python -c)
    Steps:
      1. python -c "import tomllib; d = tomllib.loads(open('xiagent/models/local_config.example.toml','rb').read()); assert 'runninghub_llm' in d; assert d['runninghub_llm']['api_key'] == ''"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-4-example-config.txt
  ```

  **Commit**：YES
  - Message：`config: add [runninghub_llm] section for RunningHub LLM proxy`
  - Files：`xiagent/models/local_config.toml`, `xiagent/models/local_config.example.toml`, `.env.example`

- [ ] 5. 创建 `RunningHubLLMChatProvider`

  **What to do**：
  - 在 `xiagent/models/providers/runninghub.py` 中新增 `RunningHubLLMChatProvider` 类
  - 结构与 `GeminiChatProvider`（`providers/gemini.py`）完全一致，差异仅在：
    - config 类型：`RunningHubLLMModelConfig`
    - 错误码：`runninghub_llm_api_key_missing`、`runninghub_llm_request_failed`
    - metadata provider 标识：`"runninghub_llm"`
  - provider 逻辑：`openai.AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)` → `chat.completions.create(model=request.model, messages=...)`

  **Must NOT do**：
  - 不修改 `GeminiChatProvider`
  - 不修改 `runninghub.py` 中已有的 `RunningHubImageProvider` 等类

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 2, 3, 4）
  - **Blocks**：Task 6
  - **Blocked By**：Task 1（需要 `RunningHubLLMModelConfig` 类型）

  **References**：
  - `xiagent/models/providers/gemini.py:1-59` — `GeminiChatProvider` 完整实现（逐行照搬模板）
  - `xiagent/models/providers/runninghub.py:1-11` — 现有 runninghub provider 的导入结构
  - `xiagent/models/types.py` — `RunningHubLLMModelConfig`（Task 1 产物）
  - `xiagent/models/router.py:9-12` — `ChatModelProvider` 抽象基类

  **Acceptance Criteria**：
  - [ ] `RunningHubLLMChatProvider` 类存在，继承 `ChatModelProvider`
  - [ ] `api_key` 为空时抛出 `ValidationError(code="runninghub_llm_api_key_missing")`
  - [ ] API 请求失败时抛出 `ExternalServiceError(code="runninghub_llm_request_failed")`

  **QA Scenarios**：

  ```
  Scenario: 缺少 api_key 时报错
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_runninghub_llm_provider.py::test_provider_requires_api_key -xvs
    Expected Result: 测试通过，捕获 runninghub_llm_api_key_missing 错误
    Evidence: .sisyphus/evidence/task-5-missing-key.txt

  Scenario: 正常调用返回 ChatResponse（mock）
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_runninghub_llm_provider.py::test_provider_sends_multimodal -xvs
    Expected Result: 测试通过，返回包含 text/model/usage 的 ChatResponse
    Evidence: .sisyphus/evidence/task-5-normal-call.txt
  ```

  **Commit**：YES
  - Message：`feat(models): add RunningHubLLMChatProvider for LLM proxy`
  - Files：`xiagent/models/providers/runninghub.py`

- [ ] 6. nodes/__init__.py — 注册 `runninghub_llm` provider + 更新节点

  **What to do**：
  1. 在 `build_node_registry()` 中构造 `RunningHubLLMModelConfig`：
     ```python
     runninghub_llm_config = RunningHubLLMModelConfig(
         api_key=settings.runninghub_llm_api_key,
         base_url=settings.runninghub_llm_base_url,
         model=settings.runninghub_llm_model,
     )
     ```
  2. 注册 provider：
     ```python
     router.register_provider("runninghub_llm", RunningHubLLMChatProvider(config=runninghub_llm_config))
     ```
  3. 更新 `GeminiVisionNode` 注册——将 `provider="gemini"` 改为 `provider="runninghub_llm"`，`model` 参数改为 `runninghub_llm_config.model`：
     ```python
     registry.register(
         GeminiVisionNode(
             model_router=router,
             provider="runninghub_llm",
             model=runninghub_llm_config.model,
         )
     )
     ```
  4. 更新 imports：新增 `RunningHubLLMModelConfig`、`RunningHubLLMChatProvider`

  **Must NOT do**：
  - 不移除 `GeminiChatProvider` 的 import 和 gemini provider 注册
  - 不修改 `GeminiVisionNode` 节点代码
  - 不修改其他节点的 provider 注册

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：NO（依赖 Wave 1 全部完成）
  - **Parallel Group**：Wave 2（with Tasks 7, 8）
  - **Blocks**：Task 9
  - **Blocked By**：Tasks 1, 2, 3, 5

  **References**：
  - `xiagent/nodes/__init__.py:85-89` — `gemini_config = GeminiModelConfig(...)` 构造模式
  - `xiagent/nodes/__init__.py:107-110` — `router.register_provider("gemini", ...)` 注册模式
  - `xiagent/nodes/__init__.py:182-188` — `GeminiVisionNode(...)` 注册（要改的行）

  **Acceptance Criteria**：
  - [ ] `router.register_provider("runninghub_llm", ...)` 调用存在
  - [ ] `GeminiVisionNode` 注册中 `provider="runninghub_llm"`
  - [ ] `test_node_registry.py` 中 `"ai.gemini_vision.v1"` 断言仍通过

  **QA Scenarios**：

  ```
  Scenario: 节点注册表包含 ai.gemini_vision.v1
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_node_registry.py -xvs -k "gemini_vision"
    Expected Result: 测试通过，ai.gemini_vision.v1 存在于注册表
    Evidence: .sisyphus/evidence/task-6-node-registry.txt

  Scenario: runninghub_llm provider 已注册
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.nodes import build_node_registry; from xiagent.infrastructure.config import load_settings; r = build_node_registry(load_settings()); assert 'runninghub_llm' in r._model_router._providers"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-6-provider-registered.txt
  ```

  **Commit**：YES
  - Message：`feat(nodes): switch GeminiVisionNode to runninghub_llm provider`
  - Files：`xiagent/nodes/__init__.py`

- [ ] 7. conftest.py — 更新 `test_settings` fixture

  **What to do**：
  - 在 `tests/conftest.py` 的 `test_settings()` fixture 中新增 3 个字段：
    ```python
    runninghub_llm_api_key="test-runninghub-llm-key",
    runninghub_llm_base_url="https://llm.runninghub.ai/v1",
    runninghub_llm_model="google/gemini-3-flash-preview",
    ```

  **Must NOT do**：
  - 不修改已有 fixture 字段

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 2（with Tasks 6, 8）
  - **Blocks**：Task 8（新测试依赖此 fixture）
  - **Blocked By**：Task 3

  **References**：
  - `tests/conftest.py:21-33` — `test_settings()` fixture 完整定义

  **Acceptance Criteria**：
  - [ ] `test_settings` fixture 包含 `runninghub_llm_api_key`、`runninghub_llm_base_url`、`runninghub_llm_model`
  - [ ] 已有测试通过（fixture 新增字段不影响已有测试）

  **QA Scenarios**：

  ```
  Scenario: test_settings fixture 包含新字段
    Tool: Bash (python -c)
    Steps:
      1. python -c "from tests.conftest import test_settings; import inspect; s = test_settings(); assert s.runninghub_llm_base_url == 'https://llm.runninghub.ai/v1'"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-7-fixture.txt
  ```

  **Commit**：YES
  - Message：`test: add runninghub_llm fields to test_settings fixture`
  - Files：`tests/conftest.py`

- [ ] 8. 新增 `test_runninghub_llm_provider.py`

  **What to do**：
  - 创建 `tests/test_runninghub_llm_provider.py`
  - 测试用例（参照 `test_gemini_provider.py` 结构）：
    1. `test_provider_requires_api_key`：config 无 key → `runninghub_llm_api_key_missing`
    2. `test_provider_sends_multimodal_messages`：mock client → 验证请求包含 image_url
    3. `test_provider_handles_api_error`：mock 抛异常 → `runninghub_llm_request_failed`
    4. `test_provider_client_factory_injection`：自定义 factory → 验证注入
  - 使用 `MagicMock(spec=AsyncOpenAI)` mock 模式

  **Must NOT do**：
  - 不修改 `test_gemini_provider.py`

  **Recommended Agent Profile**：
  - **Category**：`unspecified-low`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 2（with Tasks 6, 7）
  - **Blocks**：None
  - **Blocked By**：Task 5, Task 7

  **References**：
  - `tests/test_gemini_provider.py:1-135` — 测试结构和 mock 模式（逐行参照）
  - `xiagent/models/providers/runninghub.py` — `RunningHubLLMChatProvider` 实现（Task 5 产物）
  - `xiagent/models/types.py` — `ChatMessage`, `ChatRequest`, `ChatResponse`, `RunningHubLLMModelConfig`

  **Acceptance Criteria**：
  - [ ] 4 个测试方法全部通过
  - [ ] `test_provider_requires_api_key` 验证错误码 `runninghub_llm_api_key_missing`
  - [ ] `test_provider_handles_api_error` 验证错误码 `runninghub_llm_request_failed`

  **QA Scenarios**：

  ```
  Scenario: 全部新测试通过
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_runninghub_llm_provider.py -xvs
    Expected Result: 4 passed, 0 failed
    Evidence: .sisyphus/evidence/task-8-all-tests.txt
  ```

  **Commit**：YES
  - Message：`test: add RunningHubLLMChatProvider tests`
  - Files：`tests/test_runninghub_llm_provider.py`

- [ ] 9. 全量回归测试 + 最终验证

  **What to do**：
  1. 运行全量测试：`python -m pytest -q`
  2. 确认所有已有测试无回归
  3. 确认新测试全部通过
  4. 验证 `test_workflow_storyboard_from_sketch.py` 通过（mock 模式）
  5. 验证 `test_node_registry.py` 通过
  6. 运行 `ruff check .` 确认无 lint 错误

  **Must NOT do**：
  - 不修改任何测试文件（除 Task 7, 8 已改动的）

  **Recommended Agent Profile**：
  - **Category**：`unspecified-low`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：NO（依赖所有前序任务）
  - **Parallel Group**：Wave 2（最后执行）
  - **Blocks**：None（最终任务）
  - **Blocked By**：Tasks 6, 7, 8

  **References**：
  - 所有前序任务产物

  **Acceptance Criteria**：
  - [ ] `python -m pytest -q` → 全部通过（0 failures）
  - [ ] `ruff check .` → 无新增错误
  - [ ] `test_gemini_provider.py` 4 test → 全部 PASS
  - [ ] `test_gemini_vision_node.py` 全部 PASS
  - [ ] `test_runninghub_llm_provider.py` 4 test → 全部 PASS
  - [ ] `test_workflow_storyboard_from_sketch.py` → PASS
  - [ ] `test_node_registry.py` → PASS

  **QA Scenarios**：

  ```
  Scenario: 全量测试 0 失败
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest -q --tb=short
    Expected Result: 退出码 0，无 FAILED
    Evidence: .sisyphus/evidence/task-9-full-test.txt

  Scenario: gemini 测试无回归
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_gemini_provider.py tests/test_gemini_vision_node.py -xvs
    Expected Result: 全部 PASS
    Evidence: .sisyphus/evidence/task-9-gemini-regression.txt

  Scenario: storyboard workflow 测试通过
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_workflow_storyboard_from_sketch.py -xvs
    Expected Result: 全部 PASS
    Evidence: .sisyphus/evidence/task-9-workflow.txt
  ```

  **Commit**：NO（验证步骤，无需独立提交）

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  对照计划检查每个 Must Have / Must NOT Have，验证所有文件改动存在且无越界修改。

- [ ] F2. **Code Quality Review** — `unspecified-high`
  `ruff check .` + 检查是否有 `# type: ignore` / 未使用的 import / AI slop 模式。

- [ ] F3. **Real Manual QA** — `unspecified-low`
  执行所有 QA scenarios，收集 evidence，验证跨任务集成。

- [ ] F4. **Scope Fidelity Check** — `deep`
  确认每个文件 diff 与计划一致，无 scope creep。

---

## Commit Strategy

| Wave | Commit Message | Files |
|------|---------------|-------|
| 1 | `feat(models): add RunningHubLLMModelConfig for LLM proxy` | `types.py`, `config.py` |
| 1 | `feat(infra): add runninghub_llm fields to Settings` | `infrastructure/config.py` |
| 1 | `config: add [runninghub_llm] section for RunningHub LLM proxy` | `local_config.toml`, `local_config.example.toml`, `.env.example` |
| 1 | `feat(models): add RunningHubLLMChatProvider for LLM proxy` | `providers/runninghub.py` |
| 2 | `feat(nodes): switch GeminiVisionNode to runninghub_llm provider` | `nodes/__init__.py` |
| 2 | `test: add runninghub_llm fields to test_settings fixture` | `conftest.py` |
| 2 | `test: add RunningHubLLMChatProvider tests` | `test_runninghub_llm_provider.py` |

---

## Success Criteria

### Verification Commands
```bash
python -m pytest -q                    # 全量测试 0 失败
python -m pytest tests/test_runninghub_llm_provider.py -xvs  # 新测试 4 passed
python -m pytest tests/test_gemini_provider.py tests/test_gemini_vision_node.py -xvs  # 无回归
python -m pytest tests/test_workflow_storyboard_from_sketch.py -xvs  # 工作流通
ruff check .                           # 无新增 lint 错误
```

### Final Checklist
- [ ] 所有 Must Have 已实现
- [ ] 所有 Must NOT Have 未违反
- [ ] 全量测试 0 失败
- [ ] GeminiVisionNode 使用 RunningHub LLM 代理作为 provider

