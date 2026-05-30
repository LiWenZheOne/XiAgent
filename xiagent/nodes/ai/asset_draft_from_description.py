from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


class AssetDraftFromDescriptionNode(BaseNode):
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
            ref="ai.asset_draft_from_description.v1",
            name="资产分析",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_type": {
                        "type": "string",
                        "enum": ["auto", "character", "location", "prop"],
                        "default": "auto",
                    },
                    "description": {"type": "string", "minLength": 1},
                    "script": {"type": "string"},
                    "background": {"type": "string"},
                    "current_assets": {"type": "object", "additionalProperties": True},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "required": ["description"],
                "additionalProperties": False,
            },
            output_schema=_asset_draft_output_schema("auto"),
            description="Analyze user-described assets and draft structured character, location, or prop rows.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        asset_type = _draft_asset_type(str(inputs.get("asset_type", "auto")))
        description = inputs.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValidationError(
                code="asset_draft_description_required",
                message="请先描述需要新增的资产特征。",
            )

        max_attempts = inputs.get("max_attempts", 2)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="asset_draft_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        schema = _asset_draft_output_schema(asset_type)
        schema_instruction = _schema_instruction(schema)
        system_prompt = _asset_draft_system_prompt(asset_type)
        prompt = _asset_draft_user_prompt(
            asset_type=asset_type,
            description=description.strip(),
            script=_string_input(inputs.get("script")),
            background=_string_input(inputs.get("background")),
            current_assets=_record_input(inputs.get("current_assets")),
        )
        current_prompt = prompt
        last_error: ValidationError | None = None

        for attempt in range(max_attempts):
            response = await self._model_router.chat(
                ChatRequest(
                    provider=self._provider,
                    model=self._model,
                    messages=[
                        ChatMessage(role="system", content=f"{system_prompt}\n\n{schema_instruction}"),
                        ChatMessage(role="user", content=current_prompt),
                    ],
                )
            )
            try:
                parsed = _parse_json_object(response.text)
                validate_json_value(schema, parsed)
            except json.JSONDecodeError as exc:
                last_error = ValidationError(
                    code="asset_draft_json_parse_failed",
                    message="资产分析返回的内容不是合法 JSON。",
                    details={"attempt": attempt + 1, "error": str(exc)},
                )
            except ValidationError as exc:
                last_error = ValidationError(
                    code="asset_draft_json_validation_failed",
                    message="资产分析返回的 JSON 不符合资产草稿结构。",
                    details={"attempt": attempt + 1, "error": exc.details},
                )
            else:
                return NodeResult(status="succeeded", output=parsed, metadata=response.metadata)

            current_prompt = (
                f"{prompt}\n\n"
                f"上一轮输出校验失败：{last_error.message if last_error else 'unknown error'}。\n"
                f"{schema_instruction}\n"
                "只返回一个合法 JSON 对象，不要输出解释、Markdown 或代码块。"
            )

        if last_error is not None:
            raise last_error
        raise ValidationError(
            code="asset_draft_json_parse_failed",
            message="资产分析返回的内容不是合法 JSON。",
        )


def _draft_asset_type(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "": "auto",
        "auto": "auto",
        "all": "auto",
        "mixed": "auto",
        "自动": "auto",
        "全部": "auto",
        "character": "character",
        "role": "character",
        "角色": "character",
        "asset": "location",
        "scene": "location",
        "location": "location",
        "地点": "location",
        "场景": "location",
        "prop": "prop",
        "accessory": "prop",
        "道具": "prop",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError(
            code="asset_draft_type_invalid",
            message="新增资产类型只能是自动、角色、地点或道具。",
            details={"asset_type": value},
        ) from exc


def _asset_draft_output_schema(asset_type: str) -> dict[str, Any]:
    def typed_asset_schema(type_name: str) -> dict[str, Any]:
        asset_properties: dict[str, Any] = {
            "type": {"type": "string", "enum": [type_name]},
            "name": {"type": "string", "minLength": 1},
            "matched": {"type": "boolean"},
            "matched_asset_id": {"type": ["string", "null"]},
            "matched_asset_name": {"type": "string"},
        }
        required = ["type", "name", "matched", "matched_asset_id", "matched_asset_name"]
        if type_name == "character":
            asset_properties.update(
                {
                    "aliases": {"type": "string"},
                    "summary": {"type": "string"},
                    "character_status": {"type": "string"},
                    "variant_name": {"type": "string"},
                    "variant_description": {"type": "string"},
                    "accessories": {"type": "string"},
                }
            )
            required.extend(["aliases", "summary", "character_status", "variant_name", "variant_description", "accessories"])
        elif type_name == "location":
            asset_properties.update(
                {
                    "description": {"type": "string"},
                    "location_type": {"type": "string"},
                    "time_of_day": {"type": "string"},
                }
            )
            required.extend(["description", "location_type", "time_of_day"])
        else:
            asset_properties.update(
                {
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "related_character": {"type": "string"},
                }
            )
            required.extend(["description", "category", "related_character"])
        return {
            "type": "object",
            "required": required,
            "properties": asset_properties,
            "additionalProperties": True,
        }

    asset_schema = typed_asset_schema(asset_type) if asset_type in {"character", "location", "prop"} else {
        "oneOf": [
            typed_asset_schema("character"),
            typed_asset_schema("location"),
            typed_asset_schema("prop"),
        ]
    }
    return {
        "type": "object",
        "required": ["assets", "confidence", "reasoning"],
        "properties": {
            "assets": {"type": "array", "items": asset_schema},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _asset_draft_system_prompt(asset_type: str) -> str:
    labels = {"auto": "角色、地点或道具", "character": "角色", "location": "地点", "prop": "道具"}
    return f"""
仅返回合法 JSON。你是资产编目助手，负责把用户在资产汇总阶段补充的自然语言描述，转换成结构化{labels[asset_type]}资产草稿。

提问式分析要求：
请按以下问题完成内部分析，最终只返回 JSON，不要输出推理过程、Markdown 或代码块。
1. 用户要求新增几个资产？如果一句描述中包含多个独立资产，必须拆成多项。
2. 每个新增资产分别是什么类型：character、location 还是 prop？用户没有明说类型时，根据资产本体判断，不要使用 scene/asset 等类型名。
3. 每个新增资产能从“用户描述的新资产需求”“原始剧本文本”“世界背景”中确认哪些事实？严格区分这些输入分区，不要把当前已确认资产列表或资产库匹配字段当作新资产事实来源。
4. 每个新增资产应该按对应提取规则补全哪些字段？角色按角色提取规则补 full_name/name、aliases、summary、character_status、variant_name、variant_description、accessories；地点按地点提取规则补 description、location_type、time_of_day；道具按道具提取规则补 description、category、related_character。
5. 哪些字段无法确认？无法确认的字段返回空字符串，不要编造具体情节、身份、地点或关联关系。
6. 新增资产默认 matched=false、matched_asset_id=null、matched_asset_name=""，输出字段必须适合继续进入后续图像提示词和入库流程。

角色规则：
- 角色变体只包括稳定服装、稳定外貌造型、可穿戴或携带配件。
- 补全角色变体时，先根据用户描述、原始剧本、世界背景、角色身份、职业/阶层、地点和剧情阶段推断当前情景下最合理的稳定服装或稳定造型，再用该服装/造型命名 variant_name。
- 不要把“原文没有直接写衣服”当成“默认”。必须从身份、职业/阶层、时代、地点和当前情景推导一个具体稳定造型名，如“官兵装束”“渔民短打”“道士服”“僧衣”“旅人布衣”“水军装束”“囚服”“夜行衣”。
- variant_name 必须直接使用服装名或稳定造型名；不要包含角色名，不要使用“角色名_服装名”，也不要用被绑、受伤、押送等剧情状态命名；禁止填“默认”“基础”“普通”“无特殊造型”等空泛标签，信息有限时也必须根据情景推导身份/职业/处境造型名。
- variant_description 必须比 variant_name 更详细，至少 40 字，按头部/发型、上身、下装、鞋履、颜色材质、身份识别特征、稳定配件描述；只写稳定视觉设定。禁止输出“默认装束，无特殊造型描述”这类空泛描述。
- 被绑、受伤、奔跑、打斗、表情、姿态、镜头动作、地点、天气、光照、临时剧情处境都不是变体。
- summary 只描述角色的生平背景、身份定位或原作人物背景，不描述当前剧情状态。
- character_status 只描述当前剧情阶段的身份、处境或状态，不描述生平背景，且不得反推成 variant_name。

地点规则：
- 这里的地点不是戏剧场次，而是可复用视觉资产地点。
- description 应说明地点是什么、在哪里、在原作/世界背景中用来做什么。

道具规则：
- 描述实体道具本身，不要把角色动作写成道具。
- 衣服、服装、鞋帽、披风、围巾、面巾、斗笠、斗篷等穿戴类外观元素不作为 prop；它们属于角色变体或角色配件，应写入 character 的 variant_name、variant_description 或 accessories。
- 只有可从角色身上独立拿取、使用、赠予、争夺或作为剧情实体流转的物件才可作为 prop；普通穿着状态不能作为 prop。
- related_character 是可选字段，只有用户描述或原文明确关联角色时才填写。
""".strip()


def _asset_draft_user_prompt(
    *,
    asset_type: str,
    description: str,
    script: str,
    background: str,
    current_assets: dict[str, Any],
) -> str:
    type_label = {"auto": "角色、地点和道具", "character": "角色", "location": "地点", "prop": "道具"}[asset_type]
    return f"""
请根据以下上下文生成新增{type_label}资产草稿。

## A. 用户描述的新资产需求
{description}

## B. 世界背景
{background}

## C. 原始剧本
{script}

## D. 当前已确认资产列表（只用于去重和上下文参考，不要改写）
{json.dumps(current_assets, ensure_ascii=False, indent=2)}

## E. 输出要求
返回一个 JSON 对象，包含：
- assets：结构化资产字段数组；如果用户描述包含多个明确资产，请返回多项
- confidence：0 到 1 的数字，表示字段补全可信度
- reasoning：一句话说明生成依据

每个 asset.type 必须是 character、location 或 prop。不要输出 scene/asset/角色/地点/道具等其他类型名。
character 字段：type, name, matched, matched_asset_id, matched_asset_name, aliases, summary, character_status, variant_name, variant_description, accessories。
角色 variant_name 必须先根据当前情景和身份/职业推断服装/稳定造型，再直接写服装名或稳定造型名；禁止写“默认”“基础”“普通”“无特殊造型”等空泛标签；variant_description 写至少 40 字的详细稳定视觉设定，禁止“默认装束，无特殊造型描述”。
location 字段：type, name, matched, matched_asset_id, matched_asset_name, description, location_type, time_of_day。
prop 字段：type, name, matched, matched_asset_id, matched_asset_name, description, category, related_character。
新增资产默认 matched=false、matched_asset_id=null、matched_asset_name=""。
""".strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    match = _JSON_FENCE_PATTERN.search(candidate)
    if match is not None:
        candidate = match.group(1).strip()
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValidationError(
            code="asset_draft_json_validation_failed",
            message="资产分析返回的 JSON 根对象必须是对象。",
            details={"type": type(parsed).__name__},
        )
    return parsed


def _schema_instruction(schema: dict[str, Any]) -> str:
    return f"Target JSON Schema:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"


def _string_input(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _record_input(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
