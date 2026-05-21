# XiAgent 依赖库与部署指南

## 目标

本文档说明 XiAgent 当前版本的依赖库职责、配置来源、安装方式和部署步骤。项目第一版是 Python 模块化单体后端，不包含前端构建、Docker 镜像、Compose 编排或独立数据库服务。

## 运行环境

- Python：`>=3.11`
- 包管理：`pip`
- 虚拟环境：`venv`
- 数据库：SQLite，本地文件由 `XIAGENT_DATABASE_PATH` 指定
- API 入口：`xiagent.api.app:app`
- 默认工作流目录：`workflows`
- 默认资产目录：`storage/assets`

## 正式依赖库

正式依赖定义在 `pyproject.toml` 的 `[project].dependencies` 中。执行 `pip install .` 时，pip 会读取这些声明并自动下载依赖库。

| 依赖 | 当前约束 | 项目用途 |
| --- | --- | --- |
| `fastapi` | `>=0.115.0` | 提供 HTTP API、路由、依赖注入、请求体验证和异常处理基础。 |
| `uvicorn[standard]` | `>=0.30.0` | ASGI 服务运行器，本地开发和服务器部署均使用它启动 `xiagent.api.app:app`。 |
| `aiosqlite` | `>=0.20.0` | 异步访问 SQLite，用于用户、项目、资产、任务、节点执行和事件持久化。 |
| `jsonschema` | `>=4.23.0` | 校验工作流输入输出 Schema、节点描述和运行时 JSON 值。 |
| `PyYAML` | `>=6.0.2` | 加载 `workflows/**/*.workflow.yaml` 工作流契约文件。 |
| `langgraph` | `>=1.0.0` | 工作流执行引擎适配层依赖，核心接口不直接依赖 LangGraph。 |
| `openai` | `>=1.0.0` | 通过 `AsyncOpenAI` 调用 DeepSeek 兼容的 Chat Completions 接口。 |
| `python-multipart` | `>=0.0.9` | FastAPI 表单和上传能力依赖，保留给资产上传等接口扩展使用。 |

`pydantic` 由 FastAPI 传递安装，当前 API 请求模型直接使用 `pydantic.BaseModel`。如果未来 API 层继续直接使用 Pydantic 且 FastAPI 依赖被替换，应把 `pydantic` 提升为显式正式依赖。

## 开发依赖库

开发依赖定义在 `pyproject.toml` 的 `[project.optional-dependencies].dev` 中。执行 `pip install -e ".[dev]"` 时，pip 会安装正式依赖、开发依赖，并以 editable 模式安装当前项目。

| 依赖 | 当前约束 | 项目用途 |
| --- | --- | --- |
| `pytest` | `>=8.0.0` | 运行单元测试、服务测试、工作流测试和节点测试。 |
| `pytest-asyncio` | `>=0.23.0` | 支持异步测试，项目配置 `asyncio_mode = "auto"`。 |
| `httpx` | `>=0.27.0` | FastAPI `TestClient` 和 HTTP 相关测试依赖。 |
| `ruff` | `>=0.6.0` | Python lint 和 import 排序检查。 |

## pip 安装方式

本项目不维护 `requirements.txt`，避免与 `pyproject.toml` 形成重复依赖源。依赖统一以 `pyproject.toml` 为准。

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 本地开发 | `pip install -e ".[dev]"` | 安装项目、正式依赖和 `dev` 额外依赖；源码改动无需重新安装。 |
| 服务器部署 | `pip install .` | 安装项目和正式运行依赖，不安装测试与 lint 工具。 |
| 从 Git 仓库安装 | `pip install "xiagent @ git+https://example.com/your-org/XiAgent.git@main"` | 直接从远程仓库拉取源码并安装正式依赖。 |
| 从 Git 仓库安装开发依赖 | `pip install "xiagent[dev] @ git+https://example.com/your-org/XiAgent.git@main"` | 直接从远程仓库拉取源码，并安装正式依赖和开发依赖。 |

本地开发完整命令：

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

服务器部署完整命令：

```bash
python -m pip install --upgrade pip
pip install .
```

`pyproject.toml` 中的 `[build-system]` 声明告诉 pip 使用 setuptools 构建和安装项目；`[project].dependencies` 声明正式依赖；`[project.optional-dependencies].dev` 声明开发依赖集合。部署时只需要执行 pip 安装项目命令，不需要单独维护依赖清单。

## 配置来源

XiAgent 配置分为基础运行配置和模型配置。

### 基础运行配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `XIAGENT_DATABASE_PATH` | `.data/xiagent.sqlite3` | SQLite 数据库文件路径。启动 API 或测试构建器时会自动创建父目录。 |
| `XIAGENT_ASSET_STORAGE_DIR` | `storage/assets` | 本地文件资产存储目录。 |
| `XIAGENT_WORKFLOW_DIR` | `workflows` | 工作流模板目录，启动时会加载该目录下的工作流契约。 |

### 模型配置

模型配置支持两种来源：

- 环境变量，适合部署和 CI。
- `xiagent/models/local_config.toml`，适合本机调试；该文件已被 `.gitignore` 排除，可从 `xiagent/models/local_config.example.toml` 复制生成。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key。为空时真实 DeepSeek 节点会返回配置错误。 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 兼容 OpenAI SDK 的服务地址。 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | DeepSeek 默认模型名。 |
| `RUNNINGHUB_API_KEY` | 空 | RunningHub API Key，同时可作为图生图和文生图节点默认 Key。 |
| `RUNNINGHUB_BASE_URL` | `https://www.runninghub.ai` | RunningHub 服务地址。 |
| `RUNNINGHUB_IMAGE_MODEL` | `nano-banana2-gemini31flash/image-to-image-channel-low-price` | 图生图节点默认模型名。 |
| `RUNNINGHUB_IMAGE_ENDPOINT` | `/rhart-image-n-g31-flash/image-to-image` | 图生图任务提交接口。 |
| `RUNNINGHUB_TEXT_TO_IMAGE_MODEL` | `nano-banana-pro/text-to-image-channel-low-price` | 文生图节点默认模型名。 |
| `RUNNINGHUB_TEXT_TO_IMAGE_ENDPOINT` | `/rhart-image-n-pro/text-to-image` | 文生图任务提交接口。 |
| `RUNNINGHUB_POLL_INTERVAL_SECONDS` | `2.0` | RunningHub 任务轮询间隔。 |
| `RUNNINGHUB_POLL_TIMEOUT_SECONDS` | `180.0` | RunningHub 任务轮询超时时间。 |

不要提交真实 API Key。如果 API Key 曾经进入聊天窗口、日志、Issue、文档或 Git 提交，应立即轮换。

## 本地开发部署

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

$env:XIAGENT_DATABASE_PATH=".data/xiagent.sqlite3"
$env:XIAGENT_ASSET_STORAGE_DIR="storage/assets"
$env:XIAGENT_WORKFLOW_DIR="workflows"
$env:DEEPSEEK_API_KEY="替换为真实 DeepSeek key"

uvicorn xiagent.api.app:app --reload --host 127.0.0.1 --port 8000
```

Linux 或 macOS shell：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

export XIAGENT_DATABASE_PATH=.data/xiagent.sqlite3
export XIAGENT_ASSET_STORAGE_DIR=storage/assets
export XIAGENT_WORKFLOW_DIR=workflows
export DEEPSEEK_API_KEY=替换为真实 DeepSeek key

uvicorn xiagent.api.app:app --reload --host 127.0.0.1 --port 8000
```

启动后检查：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/nodes
curl http://127.0.0.1:8000/api/workflows
```

## 服务器部署方式

当前推荐的服务器部署方式是虚拟环境加 Uvicorn，由 systemd、Supervisor、容器平台或其他进程管理器负责守护进程。

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install .

export XIAGENT_DATABASE_PATH=/var/lib/xiagent/xiagent.sqlite3
export XIAGENT_ASSET_STORAGE_DIR=/var/lib/xiagent/assets
export XIAGENT_WORKFLOW_DIR=/opt/xiagent/workflows
export DEEPSEEK_API_KEY=替换为真实 DeepSeek key

python -m uvicorn xiagent.api.app:app --host 0.0.0.0 --port 8000
```

部署约束：

- API 启动时会自动执行 SQLite 迁移，迁移定义在 `xiagent/infrastructure/migrations.py`。
- `.env` 文件不会被应用自动读取；如果部署平台使用 `.env`，必须由进程管理器或启动脚本显式加载到环境变量。
- 第一版访问令牌存储在 API 进程内存中，服务重启后登录态会失效。
- SQLite 文件路径、资产目录和工作流目录需要部署进程具备读写权限。
- 多进程或多实例部署前，应评估进程内 token、SQLite 文件锁、资产目录一致性和未来 PostgreSQL 替换方案。

## 工作流测试部署

无 UI 工作流调试优先使用标准 CLI：

```bash
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input '{"prompt":"你好"}'
```

常用参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--database-path` | `.data/workflow-test.sqlite3` | 测试数据库路径。 |
| `--asset-storage-dir` | `.data/workflow-test-assets` | 测试资产目录。 |
| `--workflow-dir` | `workflows` | 按 `--workflow-id` 查找工作流时使用。 |
| `--username` | `workflow-test-admin` | 测试用户账号。 |
| `--password` | `secret-123` | 测试用户密码。 |
| `--project-name` | `Workflow Test Project` | 测试项目名称。 |
| `--show-json` | 关闭 | 输出任务、事件、节点执行和资产 JSON。 |
| `--preview html` | 关闭 | 生成 HTML 预览。 |
| `--open-images` | 关闭 | 尝试打开识别到的本地图片。 |

## 测试与检查

开发环境安装完成后运行：

```bash
python -m pytest -q
ruff check .
```

文档变更至少应确认：

- `README.md` 中的启动命令和当前 `pyproject.toml` 保持一致。
- 本文档列出的依赖与 `pyproject.toml` 保持一致。
- 配置项与 `xiagent/infrastructure/config.py`、`xiagent/models/config.py` 保持一致。

## 依赖变更流程

新增或调整依赖时按以下顺序处理：

1. 修改 `pyproject.toml`。
2. 如果是正式运行需要的库，放入 `[project].dependencies`。
3. 如果只用于测试、lint、调试或开发脚本，放入 `[project.optional-dependencies].dev`。
4. 更新本文档的依赖表和部署说明。
5. 重新安装本地环境：`pip install -e ".[dev]"`。
6. 运行 `python -m pytest -q` 和 `ruff check .`。
