# 硬编码清理 & 架构修正

## TL;DR

> **Quick Summary**: 系统性清除 Provider/Node/Config 中 14 处硬编码。核心架构修正：nodeId 映射从 Provider 移到 Node input，system prompt 从常量移到 workflow YAML，workflow_id 从默认值移到强制配置。
> 
> **Estimated Effort**: Medium（7 个文件，~205 行改动）
> **Parallel Execution**: YES - 2 waves

---

## Context

### 当前架构问题
```
Provider ←── 硬编码 nodeId 映射、API 路径、超时
Config  ←── 默认值含特定用户的 workflow_id
Node    ←── 硬编码 53 行中文 system prompt、maxItems
```

### 目标架构
```
Workflow YAML → system prompt, nodeId 映射
       ↓
V3 Node       → 接收映射，透传给 Provider
       ↓
Provider      → 纯 HTTP 管道（上传/提交/轮询），映射来自 Node
       ↓
Config        → API 路径、超时、密钥，无业务特定默认值
```

---

## 修改范围

| 文件 | 改动项 | 类型 |
|------|--------|------|
| `xiagent/models/types.py` | workflow_id 默认值改为 None | 🔴 |
| `xiagent/models/providers/runninghub.py` | 接受外部 nodeId 映射；提取 API 路径/超时为配置字段 | 🔴🟡 |
| `xiagent/nodes/ai/gemini_vision.py` | system prompt 默认值改为 None，无输入时报错 | 🔴 |
| `xiagent/nodes/ai/runninghub_image.py` | V3 接受 node_mapping input；maxItems 从映射推导 | 🔴🟡 |
| `xiagent/runtime/input_resolver.py` | 还原静默吞错 → 恢复抛 ValidationError | 🔴 |
| `xiagent/models/config.py` | 新增配置字段加载 | 🟡 |
| `xiagent/models/local_config.example.toml` | 新增配置节 | 🟡 |
| `workflows/global/storyboard_from_sketch.workflow.yaml` | V3 node 传入 node_mapping + system prompt | 🔴 |
| `tests/test_*.py` | 更新所有受影响测试 | 🟡 |

---

## TODOs

### Wave 1: 配置层 + Provider 重构（MAX PARALLEL）

- [x] 0. 还原 input_resolver.py 静默吞错 [quick]

  **What to do**: 还原 commit `7252e2d` 中对 `xiagent/runtime/input_resolver.py` 的行为变更——节点输出缺失时不应静默返回 `[]`，应抛 `ValidationError`。
  - 文件: `xiagent/runtime/input_resolver.py:112-113`
  - 改动: `return []` → 恢复为 `raise ValidationError(code="workflow_reference_missing_node_output", ...)`
  - 验证: 现有测试全部通过

- [x] 1. 清理 types.py + config.py — workflow_id 去默认值 + 新增配置字段 [quick]
  - `RunningHubWorkflowModelConfig.workflow_id` 改为 `str | None = None`
  - 新增字段: `api_prefix: str = "/openapi/v2"`, `http_timeout_seconds: float = 60.0`, `upload_timeout_seconds: float = 30.0`
  - `RunningHubImageModelConfig` / `RunningHubTextToImageModelConfig` 新增 `default_aspect_ratio: str = "9:16"`, `default_resolution: str = "1k"`
  - `config.py` 中 `load_model_config()` 加载新字段
  - `local_config.example.toml` 更新样例
  - `infrastructure/config.py` Settings 新增对应字段

- [x] 2. 重构 Provider — 接受外部 node_mapping + 使用配置字段 [deep]
  - `_build_payload(request)` 改为从 `request.metadata["node_mapping"]` 读取映射
  - `node_mapping` 结构: `{"images": ["81","141","139","140","176","182"], "text": {"nodeId":"150","fieldName":"text"}, "select": {"nodeIds":["190","191"],"fieldName":"select"}}`
  - 去掉所有硬编码 nodeId/fieldName
  - `_task_url()` / `_query_url()` 改用 `self._config.api_prefix`
  - `_upload_image` 改用 `self._config.upload_timeout_seconds`
  - `_UrllibJsonClient` 改用 `self._config.http_timeout_seconds`
  - `aspect_ratio` / `resolution` 默认值改用 `self._config.default_aspect_ratio` / `default_resolution`
  - `_validate_config()` 新增 `workflow_id is None` 校验
  - 提取重复的 helper 方法到 `_ProviderBase` mixin

- [x] 3. 清理 GeminiVisionNode — system prompt 去默认值 [quick]
  - `GEMINI_VISION_SYSTEM_PROMPT` 常量保留（作为文档/参考）
  - `run()` 中：若 `system` input 为空，抛 `ValidationError("system prompt required")`
  - 不再使用 `GEMINI_VISION_SYSTEM_PROMPT` 作为 fallback

### Wave 2: Node 层 + Workflow YAML + 测试（全部依赖 Wave 1）

- [x] 4. 更新 V3 Node — 接受 node_mapping input [deep]
  - `_input_schema` 新增 `node_mapping` (dict, optional，有默认值)
  - 默认值: `{"images": ["81","141","139","140","176","182"], "text": {"nodeId":"150","fieldName":"text"}, "select": {"nodeIds":["190","191"],"fieldName":"select"}}`
  - 去掉 `maxItems: 3`
  - `run()` 中将 `node_mapping` 传入 metadata
  - V3 的 `_input_schema` 去掉独立的 `aspect_ratio` / `resolution` 字段

- [x] 5. 更新 workflow YAML — 传入 system prompt + node_mapping [unspecified-high]
  - `gemini_vision_analysis` 节点的 `system` input 从空字符串改为模板引用:
    ```yaml
    system:
      template: |
        你是一个图像标注助手...(完整六步思维链)
    ```
  - `generate_storyboard_image` 节点的 V3 ref 确保 `node_mapping` 显式传入

- [x] 6. 更新测试 [deep]
  - Provider 测试: mock 传入 `node_mapping` metadata
  - V3 node 测试: 验证 `node_mapping` 正确传入 provider
  - Gemini node 测试: 验证空 system prompt 报错
  - 全量回归: `python -m pytest -q` ≥ 299

---

## Final Verification

- [x] F1. Oracle Plan Compliance Audit
- [x] F2. Code Quality Review
- [x] F3. Real Manual QA
- [x] F4. Scope Fidelity Check

---

## Commit Strategy

- **Wave 1**: `refactor: clean up hardcoded values in types/config/provider`
- **Wave 2**: `refactor: update nodes and workflow to pass config externally`

---

## Success Criteria

```bash
python -m pytest -q           # ≥ 299 passed, zero regressions
ruff check xiagent/            # clean
python -c "from xiagent.models.types import RunningHubWorkflowModelConfig; c = RunningHubWorkflowModelConfig(); assert c.workflow_id is None"
```
