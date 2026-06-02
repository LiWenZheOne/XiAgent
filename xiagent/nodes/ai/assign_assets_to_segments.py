from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.ai.deepseek_structured_json import (
    _parse_json_object,
    _schema_instruction,
    _system_messages,
)
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_SEGMENT_ASSIGNMENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["segment_asset_assignments"],
    "properties": {
        "segment_asset_assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["index", "location", "time", "present_assets", "absent_assets", "reasoning"],
                "properties": {
                    "index": {"type": "integer", "minimum": 0},
                    "location": {"type": "string"},
                    "time": {"type": "string"},
                    "present_assets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["asset_type", "asset_name", "confidence", "reason"],
                            "properties": {
                                "asset_type": {"type": "string", "minLength": 1},
                                "asset_name": {"type": "string", "minLength": 1},
                                "asset_tags": {"type": "array", "items": {"type": "string"}},
                                "asset_id": {"type": "string"},
                                "image_url": {"type": "string"},
                                "confidence": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "reason": {"type": "string", "minLength": 1},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "absent_assets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["asset_type", "asset_name", "reason"],
                            "properties": {
                                "asset_type": {"type": "string", "minLength": 1},
                                "asset_name": {"type": "string", "minLength": 1},
                                "reason": {"type": "string", "minLength": 1},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "reasoning": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}

_DEFAULT_SYSTEM_PROMPT = """\
你是一个剧本分镜分析助手。你的任务是分析每个剧本段落中角色资产的实际在场状态。

核心规则：
1. 仅返回合法 JSON，不要包含 Markdown 代码块或解释文字。
2. 逐段判断每个可用角色资产是在场还是缺席。
3. **在场**: 角色在段落中实际出现、行动、参与场景或对场景产生直接影响。即使角色没有说话也算在场。
4. **缺席规则** — 以下情况不算在场，必须归入 absent_assets：
   - 对话中提及（他人谈论该角色）
   - 命令/指示中提到（如"去找XX"、"告诉XX"）
   - 计划/设想中提到（如"如果XX在就好了"）
   - 回忆/闪回/想象中提到
   - 旁白/叙述/背景介绍中提到
   - 角色在段落开始前已离开或段落后才到达
5. 如果角色在多个连续段落中持续在场，每个段落都要在 present_assets 中记录。
6. confidence 取值：high（明确在场有行动）、medium（很可能在场但有歧义）、low（线索不充分但倾向于在场）。
7. present_assets 的 reason 必须引用段落中的具体文本作为在场证据。
8. absent_assets 的 reason 必须解释为何不算在场（对话提及/回忆/已离开等）。
9. absent_assets 仅列出可用资产中不在本段在场的角色；未出场的一律不列。
10. reasoning 字段用一句话概括本段资产判断的整体逻辑。
11. present_assets 必须输出 asset_type、asset_name、asset_tags。asset_tags 只写本段需要的稳定服装、造型或配件标签，不写角色/地点/道具这类一级类型。
"""


class AssignAssetsToSegmentsNode(BaseNode):
    """将角色资产逐段分配到剧本段落，判断每个资产在场/缺席。

    通过调用 DeepSeek 结构化 JSON 接口，分析每个段落中角色的实际在场状态，
    排除对话提及、命令、计划、回忆等非在场情况。
    """

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
            ref="ai.assign_assets_to_segments.v1",
            name="Assign Assets to Segments",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "segments": {
                        "type": "array",
                        "items": {"type": "object"},
                        "minItems": 1,
                    },
                    "characters": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "variant_results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "accessory_results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "asset_images": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "system": {"type": "string"},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "required": ["segments"],
                "additionalProperties": False,
            },
            output_schema=_SEGMENT_ASSIGNMENT_OUTPUT_SCHEMA,
            description=(
                "调用 DeepSeek 结构化 JSON 逐段判断角色资产在场/缺席。"
                "对话提及、命令、计划、回忆不算在场。"
                "输入: segments（段落数组）、characters（角色定义）、"
                "variant_results（变体匹配）、accessory_results（配件匹配）、"
                "asset_images（可用资产图像）。"
                "输出: segment_asset_assignments（逐段资产分配结果）。"
            ),
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        segments = inputs.get("segments")
        if not isinstance(segments, list) or len(segments) == 0:
            raise ValidationError(
                code="assign_assets_segments_required",
                message="segments must be a non-empty array",
            )

        max_attempts_raw = inputs.get("max_attempts")
        max_attempts = 1
        if max_attempts_raw is not None:
            if not isinstance(max_attempts_raw, int) or isinstance(max_attempts_raw, bool) or max_attempts_raw < 1:
                raise ValidationError(
                    code="assign_assets_max_attempts_invalid",
                    message="max_attempts must be an integer >= 1",
                )
            max_attempts = max_attempts_raw

        asset_images = inputs.get("asset_images") or []
        characters = inputs.get("characters") or []
        variant_results = inputs.get("variant_results") or []
        accessory_results = inputs.get("accessory_results") or []

        system_input = inputs.get("system")
        system_text = system_input if isinstance(system_input, str) and system_input.strip() else None

        # Build the user prompt from structured inputs
        prompt = _build_assignment_prompt(
            segments=segments,
            characters=characters,
            asset_images=asset_images,
            variant_results=variant_results,
            accessory_results=accessory_results,
        )

        schema = ctx.output_schema if ctx is not None else self.describe().output_schema
        schema_instruction = _schema_instruction(schema)
        effective_system = system_text if system_text else _DEFAULT_SYSTEM_PROMPT

        last_error: ValidationError | None = None
        current_prompt = prompt

        for attempt in range(max_attempts):
            messages = _system_messages(effective_system, schema_instruction)
            messages.append(ChatMessage(role="user", content=current_prompt))

            response = await self._model_router.chat(
                ChatRequest(
                    provider=self._provider,
                    model=self._model,
                    messages=messages,
                )
            )

            try:
                parsed = _parse_json_object(response.text)
            except json.JSONDecodeError as exc:
                last_error = ValidationError(
                    code="assign_assets_json_parse_failed",
                    message="DeepSeek response is not valid JSON",
                    details={"attempt": attempt + 1, "error": str(exc)},
                )
            except ValidationError as exc:
                last_error = ValidationError(
                    code=exc.code,
                    message=exc.message,
                    details={"attempt": attempt + 1, "error": exc.details},
                )
            else:
                try:
                    validate_json_value(schema, parsed)
                except ValidationError as exc:
                    last_error = ValidationError(
                        code="assign_assets_validation_failed",
                        message="DeepSeek JSON response does not match output schema",
                        details={"attempt": attempt + 1, "error": exc.details},
                    )
                else:
                    return NodeResult(
                        status="succeeded",
                        output=parsed,
                        metadata=response.metadata,
                    )

            current_prompt = (
                f"{prompt}\n\n"
                f"前一次响应校验失败: "
                f"{last_error.message if last_error else '未知错误'}。\n"
                f"{schema_instruction}\n"
                "仅返回一个合法 JSON 对象。不要包含 Markdown 或解释文字。"
            )

        if last_error is not None:
            raise last_error
        raise ValidationError(
            code="assign_assets_json_parse_failed",
            message="DeepSeek response is not valid JSON",
        )


def _build_assignment_prompt(
    *,
    segments: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    asset_images: list[dict[str, Any]],
    variant_results: list[dict[str, Any]],
    accessory_results: list[dict[str, Any]],
) -> str:
    """从结构化输入构建发送给 LLM 的提示文本。"""
    parts: list[str] = []

    # ── 剧本段落 ──
    parts.append("## 剧本段落")
    for seg in segments:
        idx = seg.get("index", "?")
        location = seg.get("location", "")
        time_str = seg.get("time", "")
        text = seg.get("text", "")
        parts.append(f"### 段落 {idx}")
        parts.append(f"- 位置: {location}")
        parts.append(f"- 时间: {time_str}")
        parts.append(f"- 内容: {text}")
        parts.append("")

    # ── 可用角色资产 ──
    if asset_images:
        parts.append("## 可用角色资产图像")
        parts.append(json.dumps(asset_images, ensure_ascii=False, indent=2))
        parts.append("")

    # ── 角色定义 ──
    if characters:
        parts.append("## 角色定义")
        parts.append(json.dumps(characters, ensure_ascii=False, indent=2))
        parts.append("")

    # ── 变体匹配 ──
    if variant_results:
        parts.append("## 角色变体匹配结果")
        parts.append(json.dumps(variant_results, ensure_ascii=False, indent=2))
        parts.append("")

    # ── 配件匹配 ──
    if accessory_results:
        parts.append("## 配件匹配结果")
        parts.append(json.dumps(accessory_results, ensure_ascii=False, indent=2))
        parts.append("")

    # ── 任务指令 ──
    parts.append("## 任务")
    parts.append(
        "请为每个段落判断：哪些角色资产 actually present（在场/实际出现），"
        "哪些资产在对话、命令、计划或回忆中提及但不在场（absent），"
        "并逐项说明理由。"
    )
    parts.append(
        "present_assets 每项使用 asset_type、asset_name、asset_tags 描述资产："
        "asset_type 通常为 character；asset_name 是主名称；asset_tags 只写本段需要的稳定服装、造型或配件标签。"
    )
    parts.append("")
    parts.append(
        "返回一个 JSON 对象，根键为 segment_asset_assignments，"
        "数组长度与输入段落数量一致，按段落顺序排列。"
    )

    return "\n".join(parts)
