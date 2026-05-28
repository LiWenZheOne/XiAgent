<!-- gitnexus:start -->
# GitNexus 代码智能索引

本项目已通过 GitNexus 建立索引，仓库别名为 **XiAgent**（4517 个符号、9232 条关系、228 条执行流）。理解代码结构、评估改动影响和定位执行流程时，优先使用 GitNexus MCP 工具。

> 如果 GitNexus 工具提示索引过期，先在终端执行 `gitnexus analyze --name XiAgent .` 更新索引。
> 当前本机 GitNexus FTS 扩展不可用，索引未生成 embeddings；自然语言 `query` 可能命中较少。需要稳定结果时，优先使用 `context`、`impact`、`cypher` 和 `gitnexus://repo/XiAgent/...` 资源。

## 必须执行

- **修改任何符号前必须做影响分析。** 修改函数、类或方法前，运行 `gitnexus_impact({target: "symbolName", direction: "upstream", repo: "XiAgent"})`，并向用户说明影响范围，包括直接调用方、受影响执行流和风险等级。
- **提交前必须运行 `gitnexus_detect_changes({repo: "XiAgent"})`**，确认改动只影响预期符号和执行流。
- 如果影响分析返回 HIGH 或 CRITICAL 风险，继续编辑前必须先告知用户。
- 探索不熟悉代码时，优先使用 `gitnexus_query({query: "concept", repo: "XiAgent"})` 查找按执行流分组的结果，再补充文本搜索。
- 需要查看某个符号的完整上下文时，使用 `gitnexus_context({name: "symbolName", repo: "XiAgent"})` 查看调用方、被调用方和参与的执行流。

## 禁止事项

- 禁止在未运行 `gitnexus_impact` 的情况下直接修改函数、类或方法。
- 禁止忽略影响分析中的 HIGH 或 CRITICAL 风险。
- 禁止用普通查找替换重命名符号；应使用理解调用图的 `gitnexus_rename`。
- 禁止在未运行 `gitnexus_detect_changes()` 检查影响范围的情况下提交。

## 资源

| 资源 | 用途 |
|----------|---------|
| `gitnexus://repo/XiAgent/context` | 查看代码库概览与索引新鲜度 |
| `gitnexus://repo/XiAgent/clusters` | 查看全部功能区域 |
| `gitnexus://repo/XiAgent/processes` | 查看全部执行流 |
| `gitnexus://repo/XiAgent/process/{name}` | 查看单个执行流的逐步调用轨迹 |

## CLI

| 任务 | 阅读此技能文件 |
|------|---------------------|
| 理解架构或“X 如何工作” | `.codex/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| 评估“修改 X 会影响什么” | `.codex/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| 追踪“为什么 X 失败” | `.codex/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| 重命名、抽取、拆分或重构 | `.codex/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| 工具、资源和图谱 schema 参考 | `.codex/skills/gitnexus/gitnexus-guide/SKILL.md` |
| 索引、状态、清理、wiki 等 CLI 命令 | `.codex/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
