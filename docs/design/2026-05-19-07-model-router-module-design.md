# 模型路由模块设计

## 目标

模型路由模块负责隔离模型供应商 SDK、密钥配置和模型调用细节。工作流仍然只编排节点，节点仍然只暴露平台节点接口；AI 节点内部不直接调用 DeepSeek、OpenAI 或其他三方 SDK，而是通过 XiAgent 自己的模型路由接口发起请求。

这样未来替换 DeepSeek 官方 API、OpenAI 兼容 SDK、PydanticAI、HTTP 客户端或其他模型供应商时，只需要新增或替换模型 provider，不需要修改工作流契约、运行器或普通节点接口。

## 模块边界

`xiagent.models` 是模型调用边界模块，提供以下稳定对象：

- `ChatMessage`：聊天消息数据结构。
- `ChatRequest`：模型调用请求，包含 provider、model、messages 和 metadata。
- `ChatResponse`：模型响应，包含 text、model、usage 和 metadata。
- `DeepSeekModelConfig`：DeepSeek provider 的配置。
- `ModelConfig`：模型模块整体配置。
- `ChatModelProvider`：provider 抽象基类。
- `ChatModelRouter`：按 provider 路由模型请求。

正式代码不使用 `Protocol` 作为平台接口。模型 provider 必须继承 `ChatModelProvider`，节点必须继承 `BaseNode`。

## 调用链路

当前 DeepSeek 节点调用链路为：

```text
workflow ref: ai.deepseek_chat.v1
  -> NodeRegistry 找到 DeepSeekChatNode
  -> Runtime 调用 DeepSeekChatNode.run()
  -> DeepSeekChatNode 构造 ChatRequest
  -> ChatModelRouter.chat()
  -> DeepSeekChatProvider.chat()
  -> OpenAI 兼容 SDK 调用 DeepSeek API
```

DeepSeek SDK 依赖只能出现在 `xiagent.models.providers.deepseek` 内。`xiagent.nodes.ai.deepseek_chat` 不得导入 `openai.AsyncOpenAI`，也不得接收 api_key、base_url 或 client_factory。

## 配置规则

模型配置统一由 `load_settings()` 解析后进入 `Settings`，节点注册只使用传入的 `Settings`，不再自行读取配置文件。

配置来源优先级：

1. 环境变量：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。
2. 本地配置文件：`xiagent/models/local_config.toml`。
3. 默认值：`base_url=https://api.deepseek.com`，`model=deepseek-v4-flash`，`api_key=None`。

真实本地配置文件 `xiagent/models/local_config.toml` 被 `.gitignore` 忽略，不进入版本库。仓库只提交 `xiagent/models/local_config.example.toml` 作为模板。

## 错误语义

- 未配置 DeepSeek key：`ValidationError(code="deepseek_api_key_missing")`。
- 未知模型 provider：`NotFoundError(code="model_provider_not_found")`。
- DeepSeek 上游调用失败：`ExternalServiceError(code="deepseek_request_failed")`。

错误详情不得包含 API key、完整请求头或其他敏感信息。

## 扩展方式

新增模型供应商时：

1. 在 `xiagent.models.providers` 下新增 provider 实现。
2. provider 继承 `ChatModelProvider`。
3. provider 内部可以依赖供应商 SDK，但不得把 SDK 类型暴露给节点、工作流、运行器或核心接口。
4. 在节点注册阶段把 provider 注册到 `ChatModelRouter`。
5. AI 节点通过 `ChatRequest` 调用 router，不直接感知供应商 SDK。
