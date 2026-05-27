# RunningHub NodeId & Select 节点更新

## TL;DR

> **Quick Summary**: 更新 `RunningHubWorkflowProvider._build_payload()` — nodeId 从固定语义映射改为顺序槽位，新增 190/191 select 节点。V3 node schema 去掉 `maxItems:3` 限制。
> 
> **Estimated Effort**: Quick（3 个文件，~30 行改动）
> **Parallel Execution**: 顺序（单文件改动为主）

---

## Context

### 用户更新
RunningHub ComfyUI 工作流已更新，节点映射改为顺序槽位模式：
- 图片从 nodeId **81** 开始按顺序填充：81 → 141 → 139 → 140 → 176 → 182
- 190/191 是 select 节点，值 = 总上传图片数（含线稿）
- 线稿不再单独一个字段，而是图片序列的第一个

### 当前实现
```python
# 旧（语义绑定）
line_art → nodeId "141"
ref_images → nodeId "139", "140", "81"
text → nodeId "150"
```

### 目标实现
```python
# 新（顺序槽位）
all_images[0] → "81" (线稿)
all_images[1] → "141" (角色1)
all_images[2] → "139" (角色2)
all_images[3] → "140" (角色3)
all_images[4] → "176" (角色4)
all_images[5] → "182" (角色5)
text → "150"
select → "190" = "191" = str(len(all_images))
```

---

## 修改范围

| 文件 | 改动 | 行数 |
|------|------|------|
| `xiagent/models/providers/runninghub.py` | 重写 `_build_payload` | ~30行 |
| `xiagent/nodes/ai/runninghub_image.py` | V3 schema 去掉 `maxItems:3` | ~2行 |
| `tests/test_runninghub_workflow.py` | 更新 nodeInfoList 断言 | ~10行 |

---

## TODOs

- [ ] 1. 更新 `_build_payload` + 更新测试

  **What to do**:
  1. 修改 `xiagent/models/providers/runninghub.py` 中 `RunningHubWorkflowProvider._build_payload`:
     - 合并 `line_art_url` 和 `ref_image_urls` 为一个列表：`all_urls = [line_art_url] + ref_image_urls`（过滤空值）
     - node_ids 改为 `["81", "141", "139", "140", "176", "182"]`
     - 按顺序填充：`for i, url in enumerate(all_urls): if i < len(node_ids): ...`
     - 去掉 `nodeId "150"` 的 caption 部分改用 `request.messages[0].content`
     - 添加 190/191 select 节点：`str(len(all_urls))`

  2. 修改 `xiagent/nodes/ai/runninghub_image.py` V3 `_input_schema`:
     - `image_urls` 去掉 `maxItems: 3`，保留 `minItems: 1`

  3. 更新 `tests/test_runninghub_workflow.py`:
     - `test_workflow_provider_builds_nodeinfo_list` — 更新期望的 nodeId 序列和 select 值
     - 其他测试如果引用了旧 nodeId 也更新

  **Must NOT do**: 不修改 V1/V2，不修改 workflow YAML

  **Commit**: `fix(provider): update nodeId mapping to sequential slots with select nodes`

---

## Final Verification

- [ ] `python -m pytest tests/test_runninghub_workflow.py tests/test_runninghub_workflows.py -v` — ALL pass
- [ ] `python -m pytest -q` — 全量无回归

---

## Success Criteria

```bash
python -m pytest tests/test_runninghub_workflow.py -v  # 验证新 nodeInfoList 结构
python -m pytest -q  # 全量回归
```
