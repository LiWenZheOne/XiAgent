# LLM 身份字段继承规范

## 背景

工作流中常见的逐项 LLM 节点会处理数组 item，例如分段剧本、资产候选、分镜段落或图片卡片。每个 item 通常包含 `index`、标题、原文、资产归属、上游上下文等身份字段。这些字段用于排序、回接上游数据、下游引用和 UI 展示，不属于 LLM 的生成职责。

如果提示词要求 LLM 返回这些身份字段，模型可能漏返、改写或返回错误值，导致运行时 JSON Schema 校验失败，或更隐蔽地造成下游数据错位。

## 规则

- 身份字段不得由 LLM 生成、修订或重写。
- 工作流可以在节点 `outputs` schema 中声明身份字段，因为下游需要稳定引用它们。
- 对支持透传的 LLM 节点，身份字段必须通过 `passthrough_fields` 或同等程序化机制从输入 item 继承。
- 对审查/修订类节点，LLM 只返回需要修订的业务字段；节点内部必须把修订字段合并回原始对象，并保留原始身份字段。
- 提示词不得写“返回完整对象”并列出身份字段，除非该节点确实由程序而非 LLM 负责补齐这些字段。
- 提示词应明确说明：不要返回 `index`、标题、原文、分段参数、资产归属等继承字段，这些字段由程序从输入 item 继承。

## 常见身份字段

以下字段通常属于身份或链路字段，应由程序继承：

- `index`
- `segment_index`
- `segment_title`
- `paragraph_text`
- `panel_count`
- `present_characters`
- `location`
- `key_props`
- `segment_assignment`
- 上游审查记录字段，例如 `review`、`review_history`

具体字段以当前工作流链路为准。判断标准是：如果字段用于排序、关联上游、保持上下文边界或供下游稳定引用，而不是当前 LLM 的新增内容，就应程序化继承。

## 工作流写法

并行结构化 LLM 节点应把身份字段放入 `passthrough_fields`：

```yaml
passthrough_fields:
  value:
    - index
    - paragraph_text
    - panel_count
```

提示词只要求 LLM 返回本步骤生成字段：

```text
输出一个 JSON 对象，只返回本步骤生成的字段：
- image_prompt

不要返回 index、paragraph_text、panel_count；这些字段会由程序从输入 item 继承。
```

输出 schema 仍可以声明完整结果：

```yaml
outputs:
  type: object
  required: ["results"]
  properties:
    results:
      type: array
      items:
        type: object
        required: ["index", "paragraph_text", "image_prompt"]
```

这里的 `index` 和 `paragraph_text` 是节点最终输出字段，不代表 LLM 需要生成它们。

## 审查修订节点

审查修订节点的修订 prompt 应写成：

```text
只返回需要修订的字段，不要返回 index、segment_title、paragraph_text 等继承字段。
身份字段会由程序从原始分段对象继承，不要尝试改写。
```

节点实现应把 LLM 返回的修订字段合并到原始对象，而不是用 LLM 返回对象替换原始对象。

## 测试要求

- 覆盖 LLM 只返回业务字段时，节点最终输出仍包含身份字段。
- 覆盖 LLM 返回错误身份字段时，节点忽略 LLM 的错误身份字段并保留原始值。
- 覆盖工作流契约校验，确认下游引用的身份字段仍在 `outputs` schema 中声明。
