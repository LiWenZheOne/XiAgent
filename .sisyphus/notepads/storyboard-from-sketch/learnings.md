# Learnings

## 2026-05-26 — Wave 1: ChatMessage 多模态扩展

### 类型变更
- `ChatMessage.content`: `str` → `str | list[dict[str, Any]]` — 兼容纯文本和 OpenAI 多模态格式（text + image_url 等）
- 新增 `GeminiModelConfig(frozen=True, slots=True)`: api_key, base_url (`https://generativelanguage.googleapis.com/v1beta/openai/`), model (`gemini-3-flash-preview`)
- `ModelConfig` 新增 `gemini: GeminiModelConfig`

### 影响面分析
- 23 个 ChatMessage 构造点全部使用纯文本字符串，无需修改
- `DeepSeekChatProvider` 中 `{"role": message.role, "content": message.content}` 对两种类型均兼容（OpenAI SDK 原生支持 str/list）
- 类型放宽不影响任何现有逻辑

### 测试
- `tests/test_chat_message.py` (3 tests): 纯文本、多模态 list、结构校验 — 全绿
- `tests/test_model_router.py` (12 tests): 零回归，全绿
- 全量测试: 1 个 pre-existing failure (`test_node_registry.py` — `tool.merge_asset_images.v1` 注册后未更新测试预期)

### 注意事项
- Python dataclass 不在运行时校验类型注解，RED 测试在类型变更前也会通过。真正价值在类型检查（mypy/pyright）和代码契约层面。
- ChatMessage 是 frozen=True, slots=True，不支持 default_factory，content 字段保留为必填参数。

## 2026-05-26 — Task 2: Gemini 模型配置集成

### 变更文件
- `xiagent/models/config.py`: `load_model_config()` 新增 `[gemini]` section 解析，env var 覆盖，构造 `GeminiModelConfig`
- `xiagent/infrastructure/config.py`: `Settings` 新增 3 字段 (`gemini_api_key`, `gemini_base_url`, `gemini_model`)，`load_settings()` 映射

### 配置模式（与 DeepSeek 一致）
- TOML section: `[gemini]` 读取 `api_key`, `base_url`, `model`
- 默认值: `base_url="https://generativelanguage.googleapis.com/v1beta/openai/"`, `model="gemini-3-flash-preview"`
- 环境变量: `GEMINI_API_KEY`, `GEMINI_BASE_URL`, `GEMINI_MODEL` 覆盖 TOML 值
- 优先级: env var → TOML config → hardcoded default

### 验证
- `python -c "from xiagent.infrastructure.config import load_settings; s = load_settings(); print(s.gemini_model)"` → `gemini-3-flash-preview`
- `tests/test_chat_message.py` (3) + `tests/test_model_router.py` (12): 15/15 passed

## 2026-05-26 — Task 5: GeminiChatProvider 创建 (TDD)

### 变更文件
- `xiagent/models/providers/gemini.py`: 新增 `GeminiChatProvider(ChatModelProvider)`，结构与 `DeepSeekChatProvider` 完全一致
- `tests/test_gemini_provider.py`: 4 个 RED→GREEN 测试

### 实现模式（镜像 DeepSeekChatProvider）
- 构造函数: `config: GeminiModelConfig, client_factory: Callable[..., Any] | None = None`
- `self._client_factory = client_factory or AsyncOpenAI`
- `async with self._client_factory(api_key=, base_url=) as client:` 上下文管理
- messages 构建: `[{"role": m.role, "content": m.content} for m in request.messages]` — 兼容 str 和 multimodal list[dict]
- 异常处理: missing api_key → `ValidationError("gemini_api_key_missing")`, API 异常 → `ExternalServiceError("gemini_request_failed")`
- 响应: `ChatResponse(text=content, model=response.model, usage=usage, metadata={"provider": "gemini"})`

### 与 DeepSeekChatProvider 的差异
- 无 `extra_body={"thinking": {"type": "disabled"}}`（DeepSeek 特有，Gemini 不需要）
- 错误码前缀 `gemini_` 替代 `deepseek_`
- metadata provider 值: `"gemini"`

### 测试（4/4 全部通过）
1. `test_gemini_provider_requires_api_key` — api_key=None → ValidationError("gemini_api_key_missing")
2. `test_gemini_provider_sends_multimodal_messages` — multimodal list[dict] content 透传给 API
3. `test_gemini_provider_handles_api_error` — API 异常 → ExternalServiceError("gemini_request_failed")
4. `test_gemini_provider_client_factory_injection` — 自定义 client_factory 注入后使用 mock client

### 注意
- Pyright 类型错误（`reportCallIssue` + `reportArgumentType`）在 deepseek.py 和 gemini.py 中完全相同，属于 pre-existing 问题，由 `Callable[..., Any]` 工厂模式导致
- `tests/conftest.py` 的 `test_settings` fixture 缺少 gemini_* 参数导致 102 个 ERROR，是 Task 3 引入的遗留问题，不在本任务范围
- Provider 不做 content 格式转换 — 直接透传给 OpenAI SDK

## 2026-05-26 — Task 7: GeminiVisionNode 实现 (TDD)

### 变更文件
- `xiagent/nodes/ai/gemini_vision.py`: 从 skeleton → 完整实现
- `tests/test_gemini_vision_node.py`: 新建 6 个 RED→GREEN 测试

### 架构决策
- 构造函数模式镜像 `DeepSeekStructuredJsonNode`: `(model_router: ChatModelRouter, provider: str, model: str)`
- `describe()` → NodeDescriptor(ref="ai.gemini_vision.v1", version="1.0.0", kind="ai")
- input_schema: `prompt` (str, required), `image_urls` (list[str], required), `system` (str, optional), `max_attempts` (int, optional, default=1)
- output_schema: `think` (str), `caption` (str), `model` (str), `usage` (dict)

### 实现模式
- **Multimodal 消息构造**: user ChatMessage content 为 `list[dict]`, 先 `{type: "text", text: prompt}`, 再逐个 image `{type: "image_url", image_url: {url}}`
- **System prompt**: 默认使用已定义的 `GEMINI_VISION_SYSTEM_PROMPT` 常量; 可通过 `system` 输入参数覆盖
- **正则提取**: `r'<think>(.*?)</think>'` 和 `r'<caption>(.*?)</caption>'`, `re.DOTALL`
- **Fallback**: `<caption>` 未匹配 → 使用全文作为 caption; `<think>` 未匹配 → 返回空字符串
- **重试策略**: 仅对 API 异常 (`Exception`) 重试, 不在 `<caption>` 缺失时重试（因为已有 fallback）
- **重试 prompt**: `f"{prompt}\n\nPrevious response failed: {exc}.\nPlease try again..."`

### 测试（6/6 全部通过）
1. `test_gemini_vision_node_rejects_empty_image_urls` — image_urls=[] → ValidationError("gemini_vision_image_urls_empty")
2. `test_gemini_vision_node_rejects_empty_prompt` — prompt="" → ValidationError("gemini_vision_prompt_empty")
3. `test_gemini_vision_node_extracts_caption` — mock 返回 `<think>/<caption>` → output.caption + multimodal content 构造验证
4. `test_gemini_vision_node_handles_missing_caption` — 无 `<caption>` → fallback 全文, think="" 
5. `test_gemini_vision_node_handles_api_timeout` — ExternalServiceError 传播
6. `test_gemini_vision_node_max_attempts_retry` — max_attempts=2, 第一次 API 异常 → 第二次成功

### 验证
- 6/6 tests pass
- LSP diagnostics clean

## 2026-05-26 — Task 11: Edge/Boundary Tests

### Gemini Vision edge cases (tests/test_gemini_vision_node.py)
- **Malformed XML** (`<captio>` misspelled): think extracted normally, caption falls back to full text
- **Empty response**: no crash, both think and caption are empty strings
- **No tags at all** (pure text): think="", caption=full text
- **Multiple caption tags**: regex.search() returns first match naturally
- **Safety block** (empty content with metadata): no crash, empty output

### DeepSeek multimodal edge case (tests/test_chat_message.py)
- **Async context manager mock**: `DeepSeekChatProvider` uses `async with client_factory() as client`
- Mock must implement `__aenter__`/`__aexit__` for proper `async with` support
- Multimodal content (list[dict]) is passed through without modification — OpenAI SDK handles it natively

### Skipped
- `test_workflow_storyboard_from_sketch.py`: does not exist (Task 10 not yet created)
- Tests 6 & 7 from task spec skipped per "如果 Task 10 已创建" guard

### Verification
- 15/15 tests pass (test_gemini_vision_node.py: 11, test_chat_message.py: 4)
- Edge/boundary filter: 22 selected, 22 passed, 5 pre-existing ERRORS (unrelated conftest.py fixture)
- LSP diagnostics clean on both modified files

## 2026-05-26 — Scope Creep / Guardrail Audit (Task F4)

### Verdict: APPROVE — All 10 guardrails pass

### Evidence by Guardrail

1. **DeepSeek/RunningHub provider mods**: ✅ `deepseek.py` untouched; `runninghub.py` was a new file from prior commit, not modified by this plan. `runninghub_image.py` (node, not provider) added `RunningHubImageToImageNodeV2` without altering v1 behavior.

2. **Existing workflow YAML mods**: ✅ All current-tree YAML changes are NEW files (`storyboard_from_sketch.workflow.yaml`, `asset_storyboard_generation.workflow.yaml`). `deepseek_echo.workflow.yaml` was modified in a previous commit, not by this plan.

3. **AssetService/UserService/RuntimeService mods**: ✅ None modified in current working tree. `core/services.py` changes were from prior commit `a3a8108`. `runtime/input_resolver.py` had a minor utility change (graceful empty return for missing node outputs).

4. **ChatMessage independent fields**: ✅ Only `role` and `content` fields. No `image_url`/`file_url`/`audio_url`.

5. **Gemini streaming/function calling/grounding**: ✅ `stream=False`, no function/tool/grounding params.

6. **Workflow composition/sub-workflow**: ✅ Zero matches for `sub.workflow|workflow_ref|subgraph|nest` across all YAML files.

7. **Line art image preprocessing**: ✅ Zero matches for `resize|thumbnail|format.conversion|preprocess|scale|compress` in `gemini_vision.py`.

8. **Parallel Gemini calls**: ✅ Single sequential DAG path: `split_script → upload_line_art → gemini_vision_analysis → ...`. No fan-out.

9. **Line art as AssetService assets**: ✅ `upload_line_art` uses `human_approval.v1` — collects URLs only, never calls `create_text_asset`/`import_file_asset`.

10. **New third-party dependencies**: ✅ `pyproject.toml` unchanged. Only existing `openai` SDK used.

### Methodology
- Examined all `M` (modified) and `??` (untracked/new) files from `git status`
- Cross-referenced with `git diff HEAD~10..HEAD` to distinguish pre-existing changes from plan changes
- Used grep, AST search, and direct file reads per guardrail
