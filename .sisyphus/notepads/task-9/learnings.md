# Task 9: 工作流 YAML 创建

## 执行摘要
成功创建 `workflows/global/storyboard_from_sketch.workflow.yaml`，通过 `validate_workflow_contract()` 校验。

## 关键决策

1. **Phase A/B 完全复用**：从 `asset_storyboard_generation.workflow.yaml` 精确复制了 15 个 Phase A 节点（角色/场景/道具提取管道 + 变体匹配）和 5 个 Phase B 节点（资产审核/手动上传/自动生成/合并），保留全部 input/output schema 和 system prompts。

2. **Phase C 新节点**：
   - `split_script`：复用 `tool.script_split.v1`，从 workflow.input.script 获取剧本
   - `upload_line_art`：`system.human_approval.v1`，人工上传线稿 URL
   - `gemini_vision_analysis`：`ai.gemini_vision.v1`，system 为空字符串时节点回退到内置 `GEMINI_VISION_SYSTEM_PROMPT`
   - `assemble_prompt_v3`：`tool.storyboard_prompt_assembler.v2`，caption 作为 description，角色参考图从 merge_asset_images 获取
   - `generate_storyboard_image`：`ai.runninghub_image_to_image.v1`，标准图生图
   - `review_storyboard_image`：`system.human_approval.v1`，最终审核

3. **DAG 边设计**：
   - 3 条并行管道（角色/场景/道具）收敛到 `review_assets`
   - 条件分支：手动上传 vs 自动生成 → 汇聚到 `merge_asset_images`
   - Phase C 串行链路：merge_asset_images → split_script → upload_line_art → gemini → assemble → generate → review → END

## 验证结果
- 文件存在：`workflows/global/storyboard_from_sketch.workflow.yaml` ✓
- YAML 解析：成功 ✓
- `validate_workflow_contract()`：PASSED ✓
- 节点数：26（Phase A: 15, Phase B: 5, Phase C: 6）
- 边数：30（含 2 条条件边）
- 所有节点 ref 被注册表识别 ✓
- DAG 无环，所有节点可达且收敛到 END ✓
