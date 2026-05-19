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
