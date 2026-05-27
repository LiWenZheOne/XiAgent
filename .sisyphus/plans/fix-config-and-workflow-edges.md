# 修复 config 字段丢失 + 工作流条件分支

## TL;DR

> **Quick Summary**: 补全 `build_node_registry` 中丢失的 3 个配置字段 + Settings 新增 3 个字段。修复 workflow YAML 条件分支——每条分支独立走 `merge_asset_images`，避免引用未执行节点。
> 
> **Estimated Effort**: Quick（4 个文件，~20 行）

---

## 问题 1：config 字段丢失

`xiagent/nodes/__init__.py:72-77` 只传了 4 个字段给 `RunningHubWorkflowModelConfig`，漏了：
- `api_prefix`, `http_timeout_seconds`, `upload_timeout_seconds`（Settings 里有但没传）
- `use_personal_queue`, `poll_interval_seconds`, `poll_timeout_seconds`（Settings 里根本没有）

## 问题 2：工作流条件分支引用未执行节点

`merge_asset_images` 同时引用 `upload_images.output` 和 `generate_asset_images_v2.output`，但条件分支下只有一个会执行，另一个引用了不存在的节点输出。

---

## 修改范围

| 文件 | 改动 |
|------|------|
| `xiagent/nodes/__init__.py` | 补全 `RunningHubWorkflowModelConfig` 构造参数 |
| `xiagent/infrastructure/config.py` | Settings 新增 3 个字段 |
| `xiagent/models/config.py` | `load_model_config()` 加载新字段 |
| `workflows/global/storyboard_from_sketch.workflow.yaml` | 条件分支各自独立 merge |

---

## TODOs

- [x] 1. 补全 config 字段 + Settings [quick]
  - `xiagent/nodes/__init__.py:72-77` 补全 `api_prefix`, `http_timeout_seconds`, `upload_timeout_seconds`
  - `xiagent/infrastructure/config.py` Settings 新增 `runninghub_workflow_use_personal_queue`, `runninghub_workflow_poll_interval_seconds`, `runninghub_workflow_poll_timeout_seconds`
  - `xiagent/models/config.py` `load_model_config()` 加载新字段，env var 支持
  - 验证: `python -m pytest -q` ≥ 299

- [x] 2. 修复 workflow 条件分支 [unspecified-high]
  - 参考 `asset_storyboard_generation.workflow.yaml` 的条件分支模式（lines 1659-1672）
  - 手动上传分支: `review_assets → upload_images → merge_asset_images`（merge 只引用 upload_images）
  - 自动生成分支: `review_assets → generate_prompt_v2 → generate_asset_images_v2 → merge_asset_images`（merge 只引用 generate_asset_images_v2）
  - 两个 `merge_asset_images` 都应只有自己分支的 input，不引用对方分支的节点
  - 验证: workflow 加载+校验通过

---

## Final Verification

- [ ] `python -m pytest -q` → 全量通过
- [ ] workflow validation through node registry
