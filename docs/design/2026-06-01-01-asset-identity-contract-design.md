# 资产身份字段契约设计

## 背景

资产提取、资产匹配、资产补图和分镜参考图链路中曾同时使用 `full_name`、`name`、`asset_key`、`variant_name`、`variant` 等字段。这些字段承担了主名称、显示名称、匹配键、变体标签和兼容引用等多种职责，导致后续节点只能通过字符串猜测来匹配资产图像。

本设计把资产身份收口为一个主名称加一组类型内标签，保证第一次资产提取、LLM 资产匹配、资产选择框、资产图像生成和分镜参考图使用同一套语义。

## 标准字段

资产身份的标准字段为：

```json
{
  "asset_type": "character",
  "asset_name": "何涛",
  "asset_tags": ["官兵装束", "官帽", "佩刀"]
}
```

- `asset_type` 是一级系统类型，用于决定资产类别和筛选范围。常用值为 `character`、`scene`、`prop`、`episode_metadata`、`asset`。
- `asset_name` 是资产主名称，只回答“这是谁/这是什么”。例如角色用 `何涛`，地点用 `山神庙外`，道具用 `花枪`。
- `asset_tags` 是类型内部标签，只表达稳定造型、配件、地点属性、道具分类等信息。标签中不得包含 `角色`、`地点`、`道具` 这类一级类型，也不得重复 `asset_name`。

图像引用字段与资产身份组合使用：

```json
{
  "asset_type": "character",
  "asset_name": "何涛",
  "asset_tags": ["官兵装束", "官帽", "佩刀"],
  "image_ref": {"kind": "asset", "asset_id": "asset_xxx", "role": "reference"},
  "image_url": "https://..."
}
```

## 禁用旧字段

以下字段不再进入新工作流节点输入、节点输出、UI 提交 payload 或 LLM 结构化结果：

- `full_name`
- `asset_key`
- `variant_name`
- `variant`
- `new_variant_name`
- `matched_variant`
- `matched_variant_id`
- `required_tags`
- `reference_assets`
- `target_asset_key`
- 作为持久节点字段的 `image_refs`

角色稳定配件不再单独使用 `accessories` 字段表达，而是并入 `asset_tags`。例如 `["囚服", "毡笠"]` 表示同一个角色资产的稳定造型和稳定配件标签。

资产库底层记录仍可能有 `name` 和 `tags`，这是文件资产存储接口的字段，不是工作流业务身份字段。进入工作流节点后必须规范化为 `asset_name` 和 `asset_tags`。标准化由 `xiagent.nodes.tools.asset_identity.normalize_asset_record()` 负责，且只从标准字段或资产库 `name/tags` 转换，不从旧业务字段反推。

## LLM 资产匹配职责

资产提取工作流中的 LLM 匹配分为两类：

1. 角色主体匹配：判断新提取角色是否与已有角色是同一人物。只比较 `asset_name`、别名、身份和人物背景，不使用服装、配件、动作或临时剧情状态判断主体相同。
2. 角色造型匹配：判断同一角色的稳定造型和配件是否已有资产图。比较 `asset_tags` 与候选资产标签和外貌描述。

LLM 不负责拼接资产名，不负责生成 `image_ref`，也不负责把候选资产字段回写成提取结果。是否引用哪张图由确定性工具节点根据 `asset_type + asset_name + asset_tags` 匹配。

## 资产选择和筛选规则

资产选择框和资产匹配候选列表按结构化条件筛选：

1. 先按 `asset_type` 过滤，例如角色只看 `character`。
2. 再按 `asset_name` 精确或模糊匹配，例如只看 `何涛`。
3. 再按 `asset_tags` 计算标签重合度，例如 `官兵装束`、`佩刀` 命中越多越靠前。

UI 展示不应直接展示拼接字段作为主要信息。推荐展示：

```text
何涛
官兵装束 · 官帽 · 佩刀
```

## 分镜参考图规则

分镜生成工作流中，段落资产分配输出 `asset_type`、`asset_name` 和 `asset_tags`。`resolve_segment_image_refs` 根据集资产目录中的 `asset_images` 做确定性匹配：

```text
asset_type 相同
asset_name 相同
asset_tags 重合度最高
```

S8 `分镜汇总` 的主数据模型是 `reference_images`。图像生成接口需要的 `image_refs` 只能由前端临时从 `reference_images[].image_ref` 派生，不进入节点输出或提交结果。

## 维护要求

- 新增资产提取字段时，优先判断它是主名称、类型、标签还是图像引用，不得新增显示名、匹配键或变体别名字段。
- 新节点如果需要资产身份，必须调用统一规范化工具，不得自行遍历旧字段做匹配。
- 工作流 schema 必须声明标准字段，LLM prompt 必须明确禁止把角色名、类型和标签拼成一个匹配键。
- UI 提交资产图片、分镜参考图和人工选择结果时，必须携带标准字段，不得提交旧字段。
