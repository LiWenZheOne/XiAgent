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
- `RunningHubImageModelConfig`：RunningHub 图生图 provider 的配置。
- `RunningHubTextToImageModelConfig`：RunningHub 文生图 provider 的配置。
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

RunningHub 图生图能力可以注册为内置工作流 AI 节点。节点只负责把工作流输入转换为 `ChatRequest`：`messages` 提供提示词，`metadata.image_urls` 提供参考图 URL 列表，`metadata.aspect_ratio` 与 `metadata.resolution` 覆盖图像比例和清晰度。节点必须通过 `ChatModelRouter` 调用 `models.providers.runninghub.RunningHubImageProvider`，不得直接依赖 RunningHub HTTP/API 实现、请求地址、轮询细节或密钥配置。`RunningHubImageProvider` 内部负责调用 RunningHub V2 标准接口、轮询 `/openapi/v2/query`，并把首个可用结果 URL 或文本放入 `ChatResponse.text`，完整结果列表放入 `ChatResponse.metadata.results`。

RunningHub 文生图能力同样可以注册为内置工作流 AI 节点。节点使用 `provider=runninghub_text_to_image` 构造 `ChatRequest`，通过 `messages` 或 `metadata.prompt` 提供提示词，`metadata.aspect_ratio` 与 `metadata.resolution` 覆盖输出比例和清晰度。节点必须通过 `ChatModelRouter` 调用 `models.providers.runninghub.RunningHubTextToImageProvider`，不得直接依赖 RunningHub HTTP/API 实现。`RunningHubTextToImageProvider` 调用 RunningHub V2 标准接口 `/openapi/v2/rhart-image-n-pro/text-to-image`，请求体只包含 `prompt`、`aspectRatio` 与 `resolution`，不要求参考图 URL。

## 配置规则

模型配置统一由 `load_settings()` 解析后进入 `Settings`，节点注册只使用传入的 `Settings`，不再自行读取配置文件。

配置来源优先级：

1. 环境变量：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`RUNNINGHUB_API_KEY`、`RUNNINGHUB_BASE_URL`、`RUNNINGHUB_IMAGE_MODEL`、`RUNNINGHUB_IMAGE_ENDPOINT`、`RUNNINGHUB_TEXT_TO_IMAGE_MODEL`、`RUNNINGHUB_TEXT_TO_IMAGE_ENDPOINT`、`RUNNINGHUB_POLL_INTERVAL_SECONDS`、`RUNNINGHUB_POLL_TIMEOUT_SECONDS`。
2. 本地配置文件：`xiagent/models/local_config.toml`。
3. 默认值：DeepSeek 使用 `base_url=https://api.deepseek.com`、`model=deepseek-v4-flash`、`api_key=None`；RunningHub 图生图使用 `base_url=https://www.runninghub.ai`、`model=nano-banana2-gemini31flash/image-to-image-channel-low-price`、`endpoint=/rhart-image-n-g31-flash/image-to-image`、`poll_interval_seconds=2.0`、`poll_timeout_seconds=180.0`、`api_key=None`；RunningHub 文生图使用 `base_url=https://www.runninghub.ai`、`model=nano-banana-pro/text-to-image-channel-low-price`、`endpoint=/rhart-image-n-pro/text-to-image`、`poll_interval_seconds=2.0`、`poll_timeout_seconds=180.0`、`api_key=None`。

RunningHub 文生图会优先读取 `[runninghub_text_to_image].api_key`。如果该字段为空，会复用同一个 `RUNNINGHUB_API_KEY` 或 `[runninghub_image].api_key`，避免同一个 RunningHub 账号密钥在本地配置中重复维护。

真实本地配置文件 `xiagent/models/local_config.toml` 被 `.gitignore` 忽略，不进入版本库。仓库只提交 `xiagent/models/local_config.example.toml` 作为模板。

## 错误语义

- 未配置 DeepSeek key：`ValidationError(code="deepseek_api_key_missing")`。
- 未配置 RunningHub key：`ValidationError(code="runninghub_api_key_missing")`。
- RunningHub 图生图缺少参考图 URL：`ValidationError(code="runninghub_image_urls_missing")`。
- RunningHub 文生图缺少提示词：`ValidationError(code="runninghub_prompt_missing")`。
- 未知模型 provider：`NotFoundError(code="model_provider_not_found")`。
- DeepSeek 上游调用失败：`ExternalServiceError(code="deepseek_request_failed")`。
- RunningHub 图生图上游调用失败：`ExternalServiceError(code="runninghub_image_request_failed")`。
- RunningHub 图生图轮询超时：`ExternalServiceError(code="runninghub_image_timeout")`。
- RunningHub 文生图上游调用失败：`ExternalServiceError(code="runninghub_text_to_image_request_failed")`。
- RunningHub 文生图轮询超时：`ExternalServiceError(code="runninghub_text_to_image_timeout")`。

错误详情不得包含 API key、完整请求头或其他敏感信息。

## 扩展方式

新增模型供应商时：

1. 在 `xiagent.models.providers` 下新增 provider 实现。
2. provider 继承 `ChatModelProvider`。
3. provider 内部可以依赖供应商 SDK，但不得把 SDK 类型暴露给节点、工作流、运行器或核心接口。
4. 在节点注册阶段把 provider 注册到 `ChatModelRouter`。
5. AI 节点通过 `ChatRequest` 调用 router，不直接感知供应商 SDK。
