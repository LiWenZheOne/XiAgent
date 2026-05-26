from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

GEMINI_VISION_SYSTEM_PROMPT = """
你是一个图像标注助手。你的任务是根据图像生成一段完整的中文描述。

规则：
- 禁止描述画风
- 最终输出必须是一整段不分段的流畅中文自然语言描述
- 只描述画面的实际内容，不要猜想和预测
- 按以下思维链逐步分析后输出
- 全程使用「」代号指代角色（如「角色A」「角色B」）

### 思维链
第零步·漫画分格与布局：
- 这是一幅描绘什么内容的漫画？
- 漫画一共有多少个分格？布局是怎样的？
- 分格之间的关系是什么？

对于每个分格，进行以下分析：
第一步·色调与光照：
- 画面整体是偏暖色调还是冷色调？还是冷暖混合？
- 画面是明亮的还是昏暗的？对比是否强烈？
- 能看出光源是什么吗？光从哪个方向照来？

第二步·时间：
- 画面中有天空吗？天空是什么颜色？
- 如果看不到天空，环境光的色温和亮度更像哪个时段？
- 如果是完全封闭的室内且无法判断，那就根据现有线索给出最合理的推断。

第三步·场景环境：
- 这是室内还是室外场景？
- 墙壁/地面是什么材质和颜色？有哪些物品和道具？
- 有没有天气或氛围效果？（雾气、飘雪、雨滴、尘土）

第四步·角色描述：
- 画面中一共有多少个角色？用「角色A」「角色B」标注代号
- 对每个角色分析：位置和角度、性别体型、面部特征、服装颜色、配饰、表情、动作、手持物品、与环境互动效果

第五步·特效：
- 有没有漫画特有的视觉符号？（速度线、冲击波纹、汗滴符号、愤怒青筋）
- 有没有光效、火花、烟雾等特殊效果？

### 输出格式
<think>
（按上述步骤逐一写出详细的分析过程）
</think>

<caption>
将分析结果整合为一整段不分段的流畅中文描述。
先描述分格情况，使用一句话概括场景及其事件。
对于每一个分格，说明有几个角色，分别是什么，并联系角色和其代号。
除了概括阶段外，全程使用「」代号指代角色。
最后详细描述背景和特效。
</caption>
"""

_THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_CAPTION_PATTERN = re.compile(r"<caption>(.*?)</caption>", re.DOTALL)


class GeminiVisionNode(BaseNode):
    """Call Gemini Vision model to analyze images with structured think+caption output."""

    def __init__(
        self,
        *,
        model_router: ChatModelRouter,
        provider: str,
        model: str,
    ) -> None:
        if not isinstance(model_router, ChatModelRouter):
            raise TypeError("model_router must be ChatModelRouter")
        self._model_router = model_router
        self._provider = provider
        self._model = model

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="ai.gemini_vision.v1",
            name="Gemini Vision",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string", "format": "uri"},
                        "minItems": 1,
                    },
                    "system": {"type": "string"},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "required": ["prompt", "image_urls"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "think": {"type": "string"},
                    "caption": {"type": "string"},
                    "model": {"type": "string"},
                    "usage": {"type": "object"},
                },
            },
            description=(
                "Call Gemini Vision model to analyze images. "
                "The model follows a structured thinking chain and returns "
                "<think> analysis and <caption> description."
            ),
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        # ---- validate prompt ----
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(
                code="gemini_vision_prompt_empty",
                message="Gemini Vision prompt cannot be empty",
            )

        # ---- validate image_urls ----
        image_urls: list[str] = inputs.get("image_urls", [])
        if not isinstance(image_urls, list) or len(image_urls) == 0:
            raise ValidationError(
                code="gemini_vision_image_urls_empty",
                message="Gemini Vision requires at least one image URL",
            )

        # ---- validate max_attempts ----
        max_attempts = inputs.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="gemini_vision_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        # ---- resolve system prompt ----
        system_text = inputs.get("system")
        if isinstance(system_text, str) and system_text.strip():
            system_prompt = system_text.strip()
        else:
            system_prompt = GEMINI_VISION_SYSTEM_PROMPT

        # ---- attempt loop ----
        last_error: Exception | None = None
        current_prompt = prompt

        for attempt in range(max_attempts):
            content: list[dict[str, Any]] = [{"type": "text", "text": current_prompt}]
            for url in image_urls:
                content.append({"type": "image_url", "image_url": {"url": url}})

            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=content),
            ]

            try:
                response = await self._model_router.chat(
                    ChatRequest(
                        provider=self._provider,
                        model=self._model,
                        messages=messages,
                    )
                )
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"Previous response failed: {exc}.\n"
                        "Please try again and return a valid response with "
                        "<think>...</think> and <caption>...</caption> tags."
                    )
                    continue
                raise

            # ---- extract <think> and <caption> ----
            think_text = ""
            caption_text = ""

            think_match = _THINK_PATTERN.search(response.text)
            if think_match is not None:
                think_text = think_match.group(1).strip()

            caption_match = _CAPTION_PATTERN.search(response.text)
            if caption_match is not None:
                caption_text = caption_match.group(1).strip()
            else:
                # fallback: use the entire response text as caption
                caption_text = response.text.strip()

            return NodeResult(
                status="succeeded",
                output={
                    "think": think_text,
                    "caption": caption_text,
                    "model": response.model,
                    "usage": response.usage,
                },
                metadata=response.metadata,
            )

        # ---- exhausted all attempts ----
        if last_error is not None:
            raise last_error
        raise ValidationError(
            code="gemini_vision_all_attempts_failed",
            message="All Gemini Vision attempts failed",
        )
