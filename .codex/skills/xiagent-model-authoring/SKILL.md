---
name: xiagent-model-authoring
description: Use when creating or modifying XiAgent model providers, xiagent.models router/config/types, model SDK adapters, model error semantics, or tests for model routing and provider integration.
---

# XiAgent 模型编写

## Overview

新增或修改模型能力时，保持 `xiagent.models` 作为模型调用边界：节点和工作流只依赖 `ChatRequest`、`ChatResponse`、`ChatModelRouter` 与 `ChatModelProvider`，供应商 SDK、密钥、base URL、客户端工厂和请求细节只留在 provider 或配置层。

## Core Workflow

1. 明确需求类型：新增供应商、修改现有 provider、调整模型配置、扩展请求/响应契约、修改路由行为，或把模型能力接入节点注册。
2. 先检查现有边界是否足够：读取 `xiagent/models/types.py`、`router.py`、`config.py`、`providers/**`、`xiagent/nodes/__init__.py`、`tests/test_model_router.py`、`tests/test_model_config.py` 和相关节点测试。
3. 优先复用 `ChatModelRouter` 和 `ChatModelProvider`。不要为单个供应商复制一套路由接口；只有公共契约确实不足时才考虑框架级变更。
4. RED：先写失败测试。provider 行为放在 `tests/test_model_router.py` 或新建聚焦测试；配置行为放在 `tests/test_model_config.py`；节点注册接入放在 `tests/test_node_registry.py` 或对应节点测试。
5. 运行目标测试，确认失败原因是模型能力缺失，而不是导入、夹具或环境变量污染。
6. GREEN：实现最小改动。新增 provider 放在 `xiagent/models/providers/<provider>.py`，必须继承 `ChatModelProvider` 并返回 `ChatResponse`。
7. 如需配置，新增 provider config dataclass 并接入 `ModelConfig`、`load_model_config()`、`load_settings()` 和示例配置文件；保持环境变量优先于本地配置，本地配置优先于默认值。
8. 如需让节点使用该 provider，只在节点注册阶段构造 provider 并注册到 `ChatModelRouter`；节点代码通过 `ChatRequest` 调用 router，不直接导入供应商 SDK。
9. REFACTOR：测试变绿后再整理命名、导出列表、重复映射逻辑和文档。公共契约变化必须同步更新模型设计文档。

## Boundary Rules

- 正式代码不使用 `Protocol` 作为模型接口；provider 必须继承 `ChatModelProvider` 这个 ABC。
- `ChatMessage`、`ChatRequest`、`ChatResponse` 是节点和模型 provider 的稳定边界。不要把 OpenAI、DeepSeek 或其他 SDK 类型泄露到这些 dataclass、节点、工作流、运行器或 API 层。
- 第三方 SDK 只能出现在 `xiagent.models.providers.<provider>` 或明确的适配器实现中。
- `ChatResponse.usage` 和 `metadata` 使用普通 dict，内容必须可序列化；`metadata` 不得包含 API key、完整请求头或敏感凭据。
- 未知 provider 继续使用 `NotFoundError(code="model_provider_not_found")`。供应商缺少凭据用 `ValidationError`，上游调用失败用 `ExternalServiceError`，错误 details 只放非敏感定位信息。
- `xiagent/models/local_config.toml` 是本地私有文件，不提交；只维护 `local_config.example.toml`。

## Provider Checklist

| Question | Action |
| --- | --- |
| 是否只是换模型名或 base URL？ | 优先改配置和测试，不新增 provider。 |
| 是否新增供应商 SDK？ | 新建 `xiagent/models/providers/<provider>.py`，SDK 类型不得外泄。 |
| 是否需要新配置项？ | 更新 config dataclass、loader、`Settings`、示例配置和配置测试。 |
| 节点是否需要使用 provider？ | 在 `build_node_registry(settings)` 注册 provider，节点继续依赖 router。 |
| 是否改变 `ChatRequest` 或 `ChatResponse`？ | 进入 Framework Change Gate，先说明影响面和迁移计划。 |
| 测试是否会真实调用模型 API？ | 不允许；用 fake client factory、fake router 或 provider 替身。 |

## Framework Change Gate

如果需求要求修改 `ChatRequest`、`ChatResponse`、`ChatModelProvider`、`ChatModelRouter`、`ModelConfig` 的公共语义，或改变节点与模型路由的调用链路，先暂停实现并向用户说明：

- 为什么现有 provider/config 扩展点不够。
- 影响哪些节点、工作流、运行时、测试和文档。
- 是否需要兼容旧字段、旧 provider 名或旧配置。
- RED/GREEN 验证计划和回归测试范围。

只有用户确认后再改公共模型框架。普通新增 provider、provider 内部请求映射、错误包装和配置读取可以直接按 TDD 推进。

## TDD Checklist

| Phase | Required Evidence |
| --- | --- |
| Reuse Check | 已确认现有 provider、router 和配置能力是否可复用。 |
| RED | 目标测试已运行并按预期失败。 |
| GREEN | 最小 provider/config/router 改动后目标测试通过。 |
| Boundary | 测试覆盖 SDK 类型不外泄、敏感信息不进入错误 details 或 metadata。 |
| Config | 覆盖环境变量、本地配置、默认值优先级。 |
| Integration | 如接入节点注册，注册表测试能证明 provider 被正确装配。 |

不能展示 RED 失败证据时，不要声称完成 TDD。

## Validation

常用命令：

```powershell
python -m pytest tests/test_model_router.py -q
python -m pytest tests/test_model_config.py -q
python -m pytest tests/test_node_registry.py -q
python -m pytest -q
```

如果模型 provider 被工作流节点使用，再运行对应节点测试和工作流测试：

```powershell
python -m pytest tests/test_deepseek_node.py -q
python -m xiagent.workflows.testing_cli workflows/global/<workflow-id>.workflow.yaml --input '{"topic":"测试"}'
```

## Common Mistakes

- 在节点里直接实例化供应商 SDK：改为 provider 处理 SDK，节点只构造 `ChatRequest`。
- 新增 provider 但绕过 `ChatModelRouter`：注册到 router 后再让节点使用。
- 测试依赖真实 API key：使用 fake client factory 或 fake provider。
- 错误 details 暴露 key、header 或完整请求：只保留 provider、model、错误代码等非敏感信息。
- 修改配置优先级却不测环境变量覆盖：配置读取最容易被本地环境污染，必须清理 env 并显式断言。
- 为某个工作流写死模型响应结构：业务结构属于节点输出 schema 或工作流契约，不属于 provider。
