# 外部 API 调用日志规范

## 目标

XiAgent 调用外部模型、图像生成、对象处理等第三方 API 时，必须能在本地和部署日志中追踪请求内容、响应内容和失败原因，便于复现工作流问题、检查提示词和定位供应商返回异常。

## 统一入口

外部 API 日志统一在 provider 或 HTTP 客户端边界记录，不放在工作流节点内重复实现。节点只负责组织业务输入，provider 负责把业务输入转换成第三方 API 请求，并在发出请求前后记录日志。

Python 代码统一使用 `xiagent.infrastructure.api_logging`：

- `log_api_request(provider, url, payload)`：记录即将发送的请求体。
- `log_api_response(provider, url, payload)`：记录第三方返回的响应体。
- `sanitize_api_payload(value)`：递归清理可记录内容。

## 记录内容

每次外部 API 调用至少记录：

- `provider`：供应商或模型 provider 名称，例如 `deepseek`、`openai_compatible`、`runninghub_image`。
- `url`：请求地址，不包含 Authorization。
- `payload`：请求或响应 JSON 内容。

日志正文必须直接包含脱敏后的 JSON，不能只依赖 logging `extra` 字段，否则默认运行日志中可能看不到实际内容。

## 脱敏与截断

日志不得完整记录密钥、访问令牌和超长图片数据：

- 以下字段必须替换为 `***redacted***`：`authorization`、`api_key`、`apikey`、`token`、`access_token`、`password`。
- `data:image/...;base64,...` 形式的图片只保留前缀和前 96 个 base64 字符，并追加原始长度标记。
- 普通文本提示词、结构化上下文、第三方错误信息应完整保留，便于复现。

## 扩展要求

新增外部 API provider 时，必须在其实际 HTTP 调用边界接入上述日志工具；不得只在节点、API 路由或前端记录调用信息。若 provider 使用第三方 SDK，也要在 SDK 调用前记录等价请求 payload，并在 SDK 返回后记录可序列化响应。
