# XiAgent

XiAgent 是一个契约驱动的智能体工作流后端平台。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DEEPSEEK_API_KEY="替换为轮换后的 DeepSeek key"
uvicorn xiagent.api.app:app --reload
```

DeepSeek 测试节点使用：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

不要把 API key 写入代码、文档、测试数据或 Git 提交。如果曾经把 key 粘贴到聊天窗口、日志、Issue 或其他外部系统，请立即轮换该 key。

## 接口检查

- `GET /api/health` 返回服务健康状态。
- `GET /api/workflows` 在 `workflow_dir` 指向 `workflows` 目录时，应能看到 `deepseek_echo` 工作流。

## 测试

```powershell
python -m pytest -q
```

## 无 UI 工作流测试

可以通过 CLI 直接执行工作流文件：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input '{"prompt":"你好"}'
```

也可以从工作流目录按模板 ID 执行：

```powershell
python -m xiagent.workflows.testing_cli --workflow-id deepseek_echo --input '{"prompt":"你好"}'
```

默认使用测试数据库 `.data/workflow-test.sqlite3`、测试用户 `workflow-test-admin` 和测试项目 `Workflow Test Project`。遇到人工等待节点时，CLI 会提示输入恢复输出 JSON。

如果工作流输入或输出包含本地图片路径或图片 data URL，CLI 会打印识别到的图片路径。需要打开图片或生成 HTML 报告时：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input-file .data/input.json --open-images --preview html --open-preview
```

`--preview html` 会生成报告，并展示识别到的图片。
