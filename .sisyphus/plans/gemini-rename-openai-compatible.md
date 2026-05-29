# Gemini → OpenAI Compatible 重命名 + vectorengine.cn 配置

## TL;DR

> **Quick Summary**：将项目中 "gemini" 命名体系重命名为 "openai_compatible"（纯 OpenAI 兼容协议），添加 `[openai_compatible]` 配置段指向 `https://api.vectorengine.cn`，GeminiVisionNode 改用通用 OpenAI 兼容 provider。节点逻辑零改动、工作流 YAML 零改动。
>
> **Deliverables**：
> - `GeminiModelConfig` → `OpenAICompatibleModelConfig`
> - `GeminiChatProvider` → `OpenAICompatibleChatProvider`
> - `[openai_compatible]` 配置段（vectorengine.cn）
> - `GeminiVisionNode` 注册改用 `provider="openai_compatible"`
>
> **Estimated Effort**：Quick（纯重命名 + 配置改动，~14 个文件）
> **Parallel Execution**：YES - 3 waves
> **Critical Path**：Task 1 → Task 5 → Task 6 → Task 9

---

## Context

### Original Request
用户要求：（1）用 `https://api.vectorengine.cn` 作为 OpenAI 兼容端点；（2）将现有 "gemini" 命名改为 "openai_compatible"，因为 `GeminiChatProvider` 本质是通用 OpenAI 兼容客户端，不应绑死 Google Gemini。

### Key Decisions
- **重命名而非新增**：不保留旧的 `GeminiModelConfig` / `GeminiChatProvider`，直接改名
- **GeminiVisionNode 节点不动**：节点类名和 `ref="ai.gemini_vision.v1"` 保持不变，只改注册时的 provider 名
- **不保留向后兼容**：当前 `local_config.toml` 没有 `[gemini]` 段，`.env.example` 没有 `GEMINI_API_KEY`，无破坏风险
- **vectorengine.cn** 作为默认 Base URL

### Research Findings
- `GeminiChatProvider` 仅 59 行，纯 OpenAI 客户端，零 Gemini 特有逻辑
- `GeminiModelConfig` 仅 3 字段（api_key, base_url, model），与 DeepSeek 同构
- 引用链：types → config → settings → provider → nodes → tests，共 6 层

---

## Work Objectives

### Core Objective
将所有 "gemini" 命名的配置、类型、提供者统一重命名为 "openai_compatible"，新增 `[openai_compatible]` 配置段，指向 `https://api.vectorengine.cn`。

### Concrete Deliverables
- `OpenAICompatibleModelConfig` 替代 `GeminiModelConfig`
- `OpenAICompatibleChatProvider` 替代 `GeminiChatProvider`
- `[openai_compatible]` TOML 配置段 + 环境变量支持
- `GeminiVisionNode` 注册改用 `"openai_compatible"` provider

### Definition of Done
- [ ] `python -m pytest -q` 全部通过
- [ ] `[openai_compatible]` 配置段存在且正确
- [ ] 所有 "gemini" 配置/类型/提供者命名已替换
- [ ] `GeminiVisionNode` 节点功能不变

### Must Have
- `[openai_compatible]` 段含 `api_key`、`base_url`（`https://api.vectorengine.cn`）、`model`
- 环境变量 `OPENAI_COMPATIBLE_API_KEY`、`OPENAI_COMPATIBLE_BASE_URL`、`OPENAI_COMPATIBLE_MODEL`
- 错误码：`openai_compatible_api_key_missing`、`openai_compatible_request_failed`

### Must NOT Have
- 不修改 `GeminiVisionNode` 节点逻辑（gemini_vision.py）
- 不修改任何工作流 YAML 文件
- 不保留旧 `GeminiModelConfig` / `GeminiChatProvider`（直接重命名）
- 不修改 `ChatModelRouter` 内部逻辑

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**：YES（pytest）
- **Automated tests**：Tests-after（适配已有测试）
- **Framework**：pytest

### QA Policy
每任务包含 Agent-Executed QA Scenarios。纯重命名改动，主要用 `pytest` + `bash` 验证。

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1（立即开始 — 配置层重命名，MAX PARALLEL）：
├── Task 1: types.py — GeminiModelConfig → OpenAICompatibleModelConfig [quick]
├── Task 2: config.py — [gemini] → [openai_compatible] 加载 [quick]
├── Task 3: infrastructure/config.py — Settings 字段重命名 [quick]
└── Task 4: 配置文件 — TOML + .env.example [quick]

Wave 2（依赖 Wave 1 — provider + 注册）：
├── Task 5: providers/gemini.py — GeminiChatProvider → OpenAICompatibleChatProvider [quick]
└── Task 6: nodes/__init__.py — 注册改用 openai_compatible [quick]

Wave 3（依赖 Wave 2 — 测试适配 + 回归）：
├── Task 7: conftest.py — fixture 字段重命名 [quick]
├── Task 8: 测试文件适配（5 个测试文件）[unspecified-low]
└── Task 9: 全量回归 [unspecified-low]
```

### Agent Dispatch Summary
- **Wave 1**：4 - T1-T4 → `quick`
- **Wave 2**：2 - T5-T6 → `quick`
- **Wave 3**：3 - T7-T9 → `quick` / `unspecified-low`

---

## TODOs

- [x] 1. types.py — `GeminiModelConfig` → `OpenAICompatibleModelConfig`

  **What to do**：
  - 重命名类：`GeminiModelConfig` → `OpenAICompatibleModelConfig`
  - 默认值更新：`base_url` 默认 `"https://api.vectorengine.cn"`，`model` 保持 `"gemini-3-flash-preview"`
  - 更新 `ModelConfig` 容器字段：`gemini: GeminiModelConfig` → `openai_compatible: OpenAICompatibleModelConfig`
  - 更新对应的 `field(default_factory=...)` 调用

  **Must NOT do**：
  - 不修改其他已有 config 类
  - 不改变字段结构（仍为 api_key/base_url/model）

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 2, 3, 4）
  - **Blocks**：Task 5
  - **Blocked By**：None

  **References**：
  - `xiagent/models/types.py:75-78` — 当前 `GeminiModelConfig` 定义
  - `xiagent/models/types.py:82-93` — `ModelConfig` 容器，含 `gemini` 字段

  **Acceptance Criteria**：
  - [ ] `OpenAICompatibleModelConfig` 类存在，`base_url` 默认 `"https://api.vectorengine.cn"`
  - [ ] `ModelConfig.openai_compatible` 字段存在
  - [ ] 无 `GeminiModelConfig` 残留引用（在同一文件内）

  **QA Scenarios**：
  ```
  Scenario: 新类型导入成功
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.models.types import OpenAICompatibleModelConfig; c = OpenAICompatibleModelConfig(); assert c.base_url == 'https://api.vectorengine.cn'"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-1-import.txt

  Scenario: ModelConfig 包含 openai_compatible 字段
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.models.types import ModelConfig; m = ModelConfig(); assert hasattr(m, 'openai_compatible')"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-1-modelconfig.txt
  ```

  **Commit**：YES（groups with Task 2）
  - Message：`refactor(models): rename GeminiModelConfig → OpenAICompatibleModelConfig`
  - Files：`xiagent/models/types.py`

- [x] 2. config.py — `[gemini]` → `[openai_compatible]` 加载

  **What to do**：
  - 在 `load_model_config()` 中：
    1. `_section(raw, "gemini")` → `_section(raw, "openai_compatible")`
    2. `gemini_api_key = ...` → `openai_compatible_api_key = ...`（本地变量重命名）
    3. `os.getenv("GEMINI_API_KEY")` → `os.getenv("OPENAI_COMPATIBLE_API_KEY")`
    4. 同理更新 `GEMINI_BASE_URL` → `OPENAI_COMPATIBLE_BASE_URL`，`GEMINI_MODEL` → `OPENAI_COMPATIBLE_MODEL`
    5. `ModelConfig(gemini=GeminiModelConfig(...))` → `ModelConfig(openai_compatible=OpenAICompatibleModelConfig(...))`
  - 更新 imports：`GeminiModelConfig` → `OpenAICompatibleModelConfig`

  **Must NOT do**：
  - 不添加 key 自动回退逻辑
  - 不删除其他 provider 的加载代码

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 3, 4）
  - **Blocks**：Task 5
  - **Blocked By**：Task 1

  **References**：
  - `xiagent/models/config.py:68-69` — `_section(raw, "gemini")` → 改为 `"openai_compatible"`
  - `xiagent/models/config.py:208-214` — Gemini 配置加载全段
  - `xiagent/models/config.py:254-258` — `ModelConfig(gemini=...)` 构造

  **Acceptance Criteria**：
  - [ ] 加载 `[openai_compatible]` TOML 段
  - [ ] `OPENAI_COMPATIBLE_API_KEY` 环境变量覆盖 TOML
  - [ ] `ModelConfig.openai_compatible` 正确构造

  **QA Scenarios**：
  ```
  Scenario: 环境变量覆盖
    Tool: Bash (PowerShell)
    Steps:
      1. $env:OPENAI_COMPATIBLE_BASE_URL = "https://test.proxy/v1"
      2. python -c "from xiagent.models.config import load_model_config; c = load_model_config(); assert c.openai_compatible.base_url == 'https://test.proxy/v1'"
    Expected Result: 退出码 0，环境变量优先级高于 TOML
    Evidence: .sisyphus/evidence/task-2-env-override.txt
  ```

  **Commit**：YES（groups with Task 1）
  - Message：`refactor(models): rename GeminiModelConfig → OpenAICompatibleModelConfig`
  - Files：`xiagent/models/types.py`, `xiagent/models/config.py`

- [x] 3. infrastructure/config.py — Settings 字段重命名

  **What to do**：
  - 在 `Settings` dataclass 中重命名 3 字段：
    - `gemini_api_key` → `openai_compatible_api_key`
    - `gemini_base_url` → `openai_compatible_base_url`
    - `gemini_model` → `openai_compatible_model`
  - 在 `load_settings()` 中更新映射：
    - `model_config.gemini.api_key` → `model_config.openai_compatible.api_key`
    - 同理更新 base_url 和 model

  **Must NOT do**：
  - 不修改已有字段
  - 不添加 key 回退逻辑

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 2, 4）
  - **Blocks**：Task 6
  - **Blocked By**：Task 1

  **References**：
  - `xiagent/infrastructure/config.py:30-32` — 当前 `gemini_*` 字段声明
  - `xiagent/infrastructure/config.py:76-78` — `model_config.gemini.*` 映射

  **Acceptance Criteria**：
  - [ ] `Settings` 含 `openai_compatible_api_key/base_url/model` 三字段
  - [ ] `load_settings()` 正确映射 `ModelConfig.openai_compatible`

  **QA Scenarios**：
  ```
  Scenario: Settings 含新字段名
    Tool: Bash (python -c)
    Steps:
      1. python -c "from xiagent.infrastructure.config import load_settings; s = load_settings(); assert hasattr(s, 'openai_compatible_api_key')"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-3-settings.txt
  ```

  **Commit**：YES
  - Message：`refactor(infra): rename gemini_* → openai_compatible_* in Settings`
  - Files：`xiagent/infrastructure/config.py`

- [x] 4. 配置文件 — TOML + .env.example

  **What to do**：
  1. 在 `xiagent/models/local_config.toml` 末尾新增 `[openai_compatible]` 段：
     ```toml
     [openai_compatible]
     api_key = ""
     base_url = "https://api.vectorengine.cn"
     model = "gemini-3-flash-preview"
     ```
  2. 在 `xiagent/models/local_config.example.toml` 中将原有 `[gemini]` 段改为 `[openai_compatible]` 段，`base_url` 改为 `"https://api.vectorengine.cn"`
  3. 在 `.env.example` 中新增（替换原可能遗漏的 GEMINI 行）：
     ```
     OPENAI_COMPATIBLE_API_KEY=
     OPENAI_COMPATIBLE_BASE_URL=https://api.vectorengine.cn
     OPENAI_COMPATIBLE_MODEL=gemini-3-flash-preview
     ```

  **Must NOT do**：
  - 不删除已有 `[deepseek]`、`[runninghub_*]` 段

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 1（with Tasks 1, 2, 3）
  - **Blocks**：Task 6（间接）
  - **Blocked By**：None

  **References**：
  - `xiagent/models/local_config.example.toml:26-29` — 旧 `[gemini]` 段（需改为 `[openai_compatible]`）
  - `.env.example:5-7` — 环境变量格式参考

  **Acceptance Criteria**：
  - [ ] `local_config.toml` 含 `[openai_compatible]` 段，`base_url = "https://api.vectorengine.cn"`
  - [ ] `local_config.example.toml` 含 `[openai_compatible]` 段，`api_key = ""`
  - [ ] `.env.example` 含 `OPENAI_COMPATIBLE_*` 三行

  **QA Scenarios**：
  ```
  Scenario: TOML 段可解析
    Tool: Bash (python -c)
    Steps:
      1. python -c "import tomllib; d = tomllib.loads(open('xiagent/models/local_config.toml','rb').read()); assert 'openai_compatible' in d"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-4-config.txt
  ```

  **Commit**：YES
  - Message：`config: rename [gemini] → [openai_compatible], add vectorengine.cn`
  - Files：`xiagent/models/local_config.toml`, `xiagent/models/local_config.example.toml`, `.env.example`

- [x] 5. 重命名文件 + provider 类

  **What to do**：
  1. 重命名文件：`xiagent/models/providers/gemini.py` → `xiagent/models/providers/openai_compatible.py`
  2. 在文件内重命名类：`GeminiChatProvider` → `OpenAICompatibleChatProvider`
  3. 更新 config 类型：`GeminiModelConfig` → `OpenAICompatibleModelConfig`
  4. 更新错误码：`gemini_api_key_missing` → `openai_compatible_api_key_missing`；`gemini_request_failed` → `openai_compatible_request_failed`
  5. 更新错误消息文本和 metadata provider 标识：`"gemini"` → `"openai_compatible"`
  6. 更新 import：`GeminiModelConfig` → `OpenAICompatibleModelConfig`
  7. 更新所有引用此文件的 import（共 2 处）：
     - `xiagent/nodes/__init__.py:6` → `from xiagent.models.providers.openai_compatible import OpenAICompatibleChatProvider`
     - `tests/test_gemini_provider.py:10` → `from xiagent.models.providers.openai_compatible import OpenAICompatibleChatProvider`

  **Must NOT do**：
  - 不修改 chat 逻辑（API 调用部分不动）

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：NO（依赖 Wave 1）
  - **Parallel Group**：Wave 2（with Task 6）
  - **Blocks**：Task 6, Task 8
  - **Blocked By**：Task 1, Task 2

  **References**：
  - `xiagent/models/providers/gemini.py:1-59` — 完整 provider 代码（59 行，全部需改名）

  **Acceptance Criteria**：
  - [ ] `OpenAICompatibleChatProvider` 类存在
  - [ ] 错误码 `openai_compatible_api_key_missing` 正确
  - [ ] 错误码 `openai_compatible_request_failed` 正确

  **QA Scenarios**：
  ```
  Scenario: 缺 key 时新错误码
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/ -xvs -k "test.*provider.*requires_api_key" 
    Expected Result: 匹配新错误码 openai_compatible_api_key_missing
    Evidence: .sisyphus/evidence/task-5-error-code.txt
  ```

  **Commit**：YES
  - Message：`refactor(models): rename gemini.py → openai_compatible.py, GeminiChatProvider → OpenAICompatibleChatProvider`
  - Files：`xiagent/models/providers/openai_compatible.py`（新文件）, `xiagent/models/providers/gemini.py`（删除）

- [x] 6. nodes/__init__.py — 注册改用 `openai_compatible` provider

  **What to do**：
  1. 更新 imports：`GeminiChatProvider` → `OpenAICompatibleChatProvider`，`GeminiModelConfig` → `OpenAICompatibleModelConfig`
  2. 重命名局部变量：`gemini_config` → `openai_compatible_config`，类型改为 `OpenAICompatibleModelConfig`
  3. 更新 provider 注册：`router.register_provider("gemini", GeminiChatProvider(...))` → `router.register_provider("openai_compatible", OpenAICompatibleChatProvider(...))`
  4. 更新 `GeminiVisionNode` 注册：`provider="gemini"` → `provider="openai_compatible"`，`model=gemini_config.model` → `model=openai_compatible_config.model`

  **Must NOT do**：
  - 不修改 `GeminiVisionNode` 节点代码
  - 不修改其他节点的 provider 注册

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：NO（依赖 Wave 1）
  - **Parallel Group**：Wave 2（with Task 5）
  - **Blocks**：Task 9
  - **Blocked By**：Tasks 3, 4, 5

  **References**：
  - `xiagent/nodes/__init__.py:6` — `GeminiChatProvider` import
  - `xiagent/nodes/__init__.py:14` — `GeminiModelConfig` import
  - `xiagent/nodes/__init__.py:85-89` — `gemini_config = GeminiModelConfig(...)` 
  - `xiagent/nodes/__init__.py:107-110` — `router.register_provider("gemini", ...)`
  - `xiagent/nodes/__init__.py:182-188` — `GeminiVisionNode(provider="gemini", ...)`

  **Acceptance Criteria**：
  - [ ] `router.register_provider("openai_compatible", ...)` 调用存在
  - [ ] `GeminiVisionNode` 注册中 `provider="openai_compatible"`
  - [ ] `test_node_registry.py` 中 `"ai.gemini_vision.v1"` 断言仍通过

  **QA Scenarios**：
  ```
  Scenario: 节点注册表含 ai.gemini_vision.v1
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_node_registry.py -xvs -k "gemini_vision"
    Expected Result: ai.gemini_vision.v1 存在于注册表
    Evidence: .sisyphus/evidence/task-6-node-registry.txt
  ```

  **Commit**：YES
  - Message：`refactor(nodes): switch to openai_compatible provider for GeminiVisionNode`
  - Files：`xiagent/nodes/__init__.py`

- [x] 7. conftest.py — fixture 字段重命名

  **What to do**：
  - 在 `tests/conftest.py` 的 `test_settings()` fixture 中重命名 3 字段：
    - `gemini_api_key="test-gemini-key"` → `openai_compatible_api_key="test-openai-compatible-key"`
    - `gemini_base_url="..."` → `openai_compatible_base_url="https://api.vectorengine.cn"`
    - `gemini_model="..."` → `openai_compatible_model="gemini-3-flash-preview"`

  **Must NOT do**：
  - 不修改已有 fixture 其他字段

  **Recommended Agent Profile**：
  - **Category**：`quick`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 3（with Task 8）
  - **Blocks**：Task 8, Task 9
  - **Blocked By**：Task 3

  **References**：
  - `tests/conftest.py:21-33` — `test_settings()` fixture 定义

  **Acceptance Criteria**：
  - [ ] fixture 含 `openai_compatible_api_key` 等新字段名
  - [ ] fixture 不含 `gemini_*` 字段名

  **QA Scenarios**：
  ```
  Scenario: fixture 使用新字段名
    Tool: Bash (python -c)
    Steps:
      1. python -c "from tests.conftest import test_settings; s = test_settings(); assert s.openai_compatible_base_url == 'https://api.vectorengine.cn'"
    Expected Result: 退出码 0
    Evidence: .sisyphus/evidence/task-7-fixture.txt
  ```

  **Commit**：YES
  - Message：`test: rename gemini_* → openai_compatible_* in conftest`
  - Files：`tests/conftest.py`

- [x] 8. 测试文件适配（5 个文件）

  **What to do**：
  逐一更新以下测试文件中所有 `GeminiModelConfig` → `OpenAICompatibleModelConfig` 和 `GeminiChatProvider` → `OpenAICompatibleChatProvider` 引用：

  1. `tests/test_gemini_provider.py` — 重命名 imports + 类引用 + error code 断言
  2. `tests/test_gemini_vision_node.py` — 更新 `provider="gemini"` → `provider="openai_compatible"`、`metadata={"provider": "gemini"}` → `"openai_compatible"`
  3. `tests/test_workflow_storyboard_from_sketch.py` — 更新 provider 注册中 `GeminiVisionNode(provider="gemini", ...)` → `provider="openai_compatible"`
  4. `tests/test_model_config.py` — 如有直接引用 `GeminiModelConfig` 或 `.gemini` 字段则更新
  5. `tests/test_node_registry.py` — 检查无直接 "gemini" 引用需更新（该文件引用的是 node ref 字符串，不是类名）

  **Must NOT do**：
  - 不修改测试逻辑
  - 不删除测试用例

  **Recommended Agent Profile**：
  - **Category**：`unspecified-low`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（5 个文件各自独立）
  - **Parallel Group**：Wave 3（with Task 7）
  - **Blocks**：Task 9
  - **Blocked By**：Tasks 5, 6, 7

  **References**：
  - `tests/test_gemini_provider.py:10-11` — imports
  - `tests/test_gemini_provider.py:29-30,58-59,101-102,131-132` — 类引用
  - `tests/test_gemini_provider.py:35,107` — error code 断言
  - `tests/test_gemini_vision_node.py:17-18,94-95` — provider/model 字符串
  - `tests/test_workflow_storyboard_from_sketch.py:274` — GeminiVisionNode 构造
  - `tests/test_model_config.py` — 全文件搜索 gemini
  - `tests/test_node_registry.py:70` — ref 字符串

  **Acceptance Criteria**：
  - [ ] 无 `GeminiModelConfig` 和 `GeminiChatProvider` 残留引用（在测试文件中）
  - [ ] 所有 error code 断言更新到 `openai_compatible_*`

  **QA Scenarios**：
  ```
  Scenario: 测试文件无旧引用
    Tool: Bash (grep)
    Steps:
      1. grep -rn "GeminiModelConfig\|GeminiChatProvider" tests/
    Expected Result: 无输出（所有引用已替换）
    Evidence: .sisyphus/evidence/task-8-no-old-refs.txt
  ```

  **Commit**：YES
  - Message：`test: adapt tests for openai_compatible rename`
  - Files：`tests/test_gemini_provider.py`, `tests/test_gemini_vision_node.py`, `tests/test_workflow_storyboard_from_sketch.py`, `tests/test_model_config.py`, `tests/test_node_registry.py`

- [x] 9. 全量回归测试

  **What to do**：
  1. `python -m pytest -q --tb=short`
  2. 确认 0 failures
  3. `ruff check .` 确认无新增 lint 错误
  4. 关键验证：`test_gemini_provider.py`、`test_gemini_vision_node.py`、`test_workflow_storyboard_from_sketch.py` 全部通过

  **Must NOT do**：
  - 不修改任何源文件（仅验证）

  **Recommended Agent Profile**：
  - **Category**：`unspecified-low`
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：NO（最后执行）
  - **Parallel Group**：Wave 3（最后）
  - **Blocks**：None
  - **Blocked By**：Tasks 6, 7, 8

  **Acceptance Criteria**：
  - [ ] `python -m pytest -q` → 全部通过
  - [ ] `ruff check .` → 无新增错误

  **QA Scenarios**：
  ```
  Scenario: 全量测试
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest -q --tb=short
    Expected Result: 退出码 0，无 FAILED
    Evidence: .sisyphus/evidence/task-9-full.txt

  Scenario: 关键模块测试
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest tests/test_gemini_provider.py tests/test_gemini_vision_node.py tests/test_workflow_storyboard_from_sketch.py -xvs
    Expected Result: 全部 PASS
    Evidence: .sisyphus/evidence/task-9-key-modules.txt
  ```

  **Commit**：NO（验证步骤）

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  检查所有 Must Have / Must NOT Have，验证无遗漏、无越界。

- [x] F2. **Code Quality Review** — `unspecified-high`
  `ruff check .` + 搜索残留 `gemini_` 引用（排除 `GeminiVisionNode` 和 `gemini_vision` ref 字符串）。

- [x] F3. **Real Manual QA** — `unspecified-low`
  执行所有 QA scenarios，收集 evidence。

- [x] F4. **Scope Fidelity Check** — `deep`
  确认 diff 与计划一致，无 scope creep。

---

## Commit Strategy

| Wave | Commit Message | Files |
|------|---------------|-------|
| 1 | `refactor(models): rename GeminiModelConfig → OpenAICompatibleModelConfig` | `types.py`, `config.py` |
| 1 | `refactor(infra): rename gemini_* → openai_compatible_* in Settings` | `infrastructure/config.py` |
| 1 | `config: rename [gemini] → [openai_compatible], add vectorengine.cn` | `local_config.toml`, `local_config.example.toml`, `.env.example` |
| 2 | `refactor(models): rename gemini.py → openai_compatible.py, GeminiChatProvider → OpenAICompatibleChatProvider` | `openai_compatible.py`（新）, `gemini.py`（删） |
| 2 | `refactor(nodes): switch to openai_compatible provider for GeminiVisionNode` | `nodes/__init__.py` |
| 3 | `test: rename gemini_* → openai_compatible_* in conftest` | `conftest.py` |
| 3 | `test: adapt tests for openai_compatible rename` | 5 test files |

---

## Success Criteria

### Verification Commands
```bash
python -m pytest -q --tb=short    # 全量测试 0 失败
ruff check .                       # 无新增 lint
grep -rn "GeminiModelConfig\|GeminiChatProvider" xiagent/ tests/  # 残留检查（排除 GeminiVisionNode）
```

### Final Checklist
- [ ] 所有 Must Have 已实现
- [ ] 所有 Must NOT Have 未违反
- [ ] 全量测试 0 失败
- [ ] 配置中 `[openai_compatible]` 指向 `api.vectorengine.cn`
- [ ] `GeminiVisionNode` 使用 `provider="openai_compatible"`

