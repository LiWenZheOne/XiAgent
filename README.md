# XiAgent

XiAgent 是一个契约驱动的智能体工作流后端平台。当前版本采用 Python 模块化单体架构，提供 FastAPI HTTP 接口、SQLite 本地持久化、工作流契约加载、节点注册与无 UI 工作流调试能力。

## 核心能力

- 用户注册、登录、项目创建与基础访问校验。
- 本地文件资产与文字资产管理，支持按全局或项目范围检索。
- YAML/JSON 工作流模板加载、契约校验、DAG 执行与人工恢复节点。
- 节点注册表，内置 Echo、DeepSeek Chat、DeepSeek 结构化 JSON、RunningHub 图像相关节点。
- 工作流测试 CLI，便于在没有 UI 的情况下验证工作流输入、输出、事件、节点快照和资产预览。

## 项目结构

```text
xiagent/
  api/              FastAPI 应用、路由、依赖装配和错误处理
  assets/           资产服务、本地存储和资产数据模型
  core/             跨模块核心错误、接口、ID、Schema 工具
  infrastructure/   配置、数据库连接和 SQLite 迁移
  models/           模型路由、模型配置和第三方模型提供者
  nodes/            BaseNode、节点注册表和内置节点实现
  runtime/          任务执行、节点快照、事件和恢复逻辑
  workflows/        工作流加载、目录服务、校验和测试工具
workflows/global/   全局工作流模板示例
docs/               架构、设计和开发文档
tests/              pytest 测试用例
```

## 环境要求

- Python 3.11 或更高版本。
- pip 与 venv。
- SQLite。Python 标准库自带 SQLite 驱动，项目通过 `aiosqlite` 异步访问数据库。
- 可选：DeepSeek API Key、RunningHub API Key，用于真实调用外部模型节点。

## 本地开发部署

1. 创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. 安装项目和开发依赖：

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

3. 配置本地环境变量：

```powershell
$env:XIAGENT_DATABASE_PATH=".data/xiagent.sqlite3"
$env:XIAGENT_ASSET_STORAGE_DIR="storage/assets"
$env:XIAGENT_WORKFLOW_DIR="workflows"
$env:DEEPSEEK_API_KEY="替换为真实 DeepSeek key"
```

4. 启动 API 服务：

```powershell
uvicorn xiagent.api.app:app --reload --host 127.0.0.1 --port 8000
```

服务启动时会自动对 `XIAGENT_DATABASE_PATH` 指向的 SQLite 数据库执行迁移。启动后可以访问：

- `GET http://127.0.0.1:8000/api/health`
- `GET http://127.0.0.1:8000/api/nodes`
- `GET http://127.0.0.1:8000/api/workflows`

## 生产式运行

当前仓库没有内置 Dockerfile、Compose 文件或 systemd 配置。部署到服务器时，建议使用独立虚拟环境安装正式依赖，并由系统进程管理器托管 Uvicorn 进程：

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

部署注意事项：

- 不要把 API Key 写入代码、文档、测试数据或 Git 提交。
- `.env` 和 `xiagent/models/local_config.toml` 已被 `.gitignore` 排除，但应用不会自动读取 `.env` 文件；需要由 shell、进程管理器或部署平台把变量注入进程环境。
- `xiagent/models/local_config.toml` 可从 `xiagent/models/local_config.example.toml` 复制生成，用于本机模型配置；生产环境优先使用环境变量。
- SQLite 适合第一版单体部署和本地测试。多实例部署前需要评估数据库文件锁、共享存储和未来数据库替换方案。
- 工作流模板目录由 `XIAGENT_WORKFLOW_DIR` 控制，默认读取 `workflows`。

## 常用接口流程

1. 注册用户：

```http
POST /api/auth/register
```

2. 登录并取得 Bearer Token：

```http
POST /api/auth/login
```

3. 访问受保护接口时添加请求头：

```text
Authorization: Bearer <access_token>
```

4. 创建项目、创建任务、查询任务或恢复人工等待节点：

```text
POST /api/projects
POST /api/tasks
GET  /api/tasks/{task_id}?project_id=<project_id>
POST /api/tasks/{task_id}/resume
```

## 无 UI 工作流测试

通过工作流文件直接执行：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input '{"prompt":"你好"}'
```

也可以从工作流目录按模板 ID 执行：

```powershell
python -m xiagent.workflows.testing_cli --workflow-id deepseek_echo --input '{"prompt":"你好"}'
```

默认测试配置：

- 数据库：`.data/workflow-test.sqlite3`
- 资产目录：`.data/workflow-test-assets`
- 测试用户：`workflow-test-admin`
- 测试项目：`Workflow Test Project`

生成 HTML 预览并尝试打开识别到的图片：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input-file .data/input.json --open-images --preview html --open-preview
```

## 测试与代码检查

```powershell
python -m pytest -q
ruff check .
```

## 依赖与部署文档

依赖库用途、配置项、安装方式和部署检查清单见 [依赖库与部署指南](docs/development/2026-05-21-01-dependency-and-deployment-guidelines.md)。

项目依赖统一声明在 `pyproject.toml`，pip 会在安装项目时自动拉取正式依赖：

```powershell
pip install .
pip install -e ".[dev]"
```
