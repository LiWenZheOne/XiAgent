# 修复 httpx 生产依赖

## 问题
`httpx` 在 `[project.optional-dependencies] dev` 中（仅开发安装），但 `RunningHubWorkflowProvider._upload_image()` 使用 `import httpx`。生产环境 `pip install .` 不安装 httpx → ModuleNotFoundError → V3 节点崩溃。

## 修复
`pyproject.toml`: 将 `"httpx>=0.27.0"` 从 `dev` 移到 `[project] dependencies`

## 验证
```bash
pip install -e .
python -c "import httpx; print('OK')"
python -m pytest -q
```
