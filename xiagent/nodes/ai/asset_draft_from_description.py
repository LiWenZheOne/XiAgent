from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.ai import PromptDraftCapability, asset_draft_output_schema
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
            name="补充缺失资产",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_type": {
                        "type": "string",
                        "enum": ["auto", "character", "scene", "prop"],
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
            output_schema=asset_draft_output_schema("auto"),
            description="根据用户描述补充缺失资产，并草拟结构化角色、地点或道具行。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        result = await PromptDraftCapability(
            model_router=self._model_router,
            provider=self._provider,
            model=self._model,
        ).draft_asset_from_description(
            asset_type=str(inputs.get("asset_type", "auto")),
            description=inputs.get("description"),
            script=inputs.get("script"),
            background=inputs.get("background"),
            current_assets=inputs.get("current_assets"),
            max_attempts=inputs.get("max_attempts", 2),
        )
        return NodeResult(status="succeeded", output=result.output, metadata=result.metadata)


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
        "asset": "scene",
        "scene": "scene",
        "location": "scene",
        "地点": "scene",
        "场景": "scene",
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
            "asset_type": {"type": "string", "enum": [type_name]},
            "asset_name": {"type": "string", "minLength": 1},
            "asset_tags": {"type": "array", "items": {"type": "string"}},
            "matched": {"type": "boolean"},
            "matched_asset_id": {"type": ["string", "null"]},
            "matched_asset_name": {"type": "string"},
        }
        required = ["asset_type", "asset_name", "asset_tags", "matched", "matched_asset_id", "matched_asset_name"]
        if type_name == "character":
            asset_properties.update(
                {
                    "aliases": {"type": "string"},
                    "summary": {"type": "string"},
                    "character_status": {"type": "string"},
                    "appearance_description": {"type": "string"},
                }
            )
            required.extend(["aliases", "summary", "character_status", "appearance_description"])
        elif type_name == "scene":
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

    asset_schema = typed_asset_schema(asset_type) if asset_type in {"character", "scene", "prop"} else {
        "oneOf": [
            typed_asset_schema("character"),
            typed_asset_schema("scene"),
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
    labels = {"auto": "角色、地点或道具", "character": "角色", "scene": "地点", "prop": "道具"}
    return f"""
仅返回合法 JSON。你是资产编目助手，负责把用户在资产汇总阶段补充的自然语言描述，转换成结构化{labels[asset_type]}资产草稿。

提问式分析要求：
请按以下问题完成内部分析，最终只返回 JSON，不要输出推理过程、Markdown 或代码块。
1. 用户要求新增几个资产？如果一句描述中包含多个独立资产，必须拆成多项。
2. 每个新增资产分别是什么类型：character、scene 还是 prop？用户没有明说类型时，根据资产本体判断；地点统一输出 scene，不要输出 location/asset/角色/地点/道具等类型名。
3. 每个新增资产能从“用户描述的新资产需求”“原始剧本文本”“世界背景”中确认哪些事实？严格区分这些输入分区，不要把当前已确认资产列表或资产库匹配字段当作新资产事实来源。
4. 每个新增资产应该按对应提取规则补全哪些字段？角色按角色提取规则补 asset_type、asset_name、asset_tags、aliases、summary、character_status、appearance_description；地点按地点提取规则补 asset_type、asset_name、asset_tags、description、location_type、time_of_day；道具按道具提取规则补 asset_type、asset_name、asset_tags、description、category、related_character。
5. 哪些字段无法确认？无法确认的字段返回空字符串，不要编造具体情节、身份、地点或关联关系。
6. 新增资产默认 matched=false、matched_asset_id=null、matched_asset_name=""，输出字段必须适合继续进入后续图像提示词和入库流程。

角色规则：
- 角色变体只包括稳定服装、稳定外貌造型、可穿戴或携带配件。
- 补全角色标签时，先根据用户描述、原始剧本、世界背景、角色身份、职业/阶层、地点和剧情阶段推断当前情景下最合理的稳定服装、稳定造型和稳定配件，再写入 asset_tags。
- 不要把“原文没有直接写衣服”当成“默认”。必须从身份、职业/阶层、时代、地点和当前情景推导一个具体稳定造型名，如“官兵装束”“渔民短打”“道士服”“僧衣”“旅人布衣”“水军装束”“囚服”“夜行衣”。
- asset_tags 必须直接使用服装名、稳定造型名或稳定配件名；不要包含角色名，不要用被绑、受伤、押送等剧情状态命名；禁止填“默认”“基础”“普通”“无特殊造型”等空泛标签，信息有限时也必须根据情景推导身份/职业/处境造型标签。
- appearance_description 必须比 asset_tags 更详细，至少 40 字，只描述图像中角色可见的外貌特征和稳定造型，按头部/发型、上身、下装、鞋履、颜色搭配、身份识别特征、稳定配件描述；不要写用途、生成目的、剧情作用；不要描述任何材质、布料质感、纹理或面料工艺。禁止输出“默认装束，无特殊造型描述”这类空泛描述。
- 被绑、受伤、奔跑、打斗、表情、姿态、镜头动作、地点、天气、光照、临时剧情处境都不是变体。
- summary 只描述角色的生平背景、身份定位或原作人物背景，不描述当前剧情状态。
- character_status 只描述当前剧情阶段的身份、处境或状态，不描述生平背景，且不得反推成 asset_tags。

地点规则：
- 这里的地点不是戏剧场次，而是可复用视觉资产地点。
- 地点统一输出 asset_type="scene"。
- description 必须说明地点是什么、在哪里、在原作/世界背景中用来做什么，并根据时代背景描述空间结构、场景物件、陈设、布局和装饰风格。
- time_of_day 根据用户描述、原始剧本和世界背景填写时间、天气与环境氛围；原文未明说时，可结合当前情节推断最合理的可见时间和氛围，不要只写空泛“白天/夜晚”。
- 船、舟、渔船、官船、楼船、马车、轿子、房屋、店铺、桥、码头、城门、牢房等大型载具、建筑、场所或可供角色进入/停留的空间，应归入 scene，不得归入 prop。

道具规则：
- 描述实体道具本身，不要把角色动作写成道具。
- 衣服、服装、鞋帽、披风、围巾、面巾、斗笠、斗篷等穿戴类外观元素不作为 prop；它们属于角色稳定标签，应写入 character 的 asset_tags 或 appearance_description。
- 只有可从角色身上或场景中独立拿取、使用、赠予、争夺或作为剧情实体流转的小型/中型物件才可作为 prop；普通穿着状态、大型载具、建筑空间不能作为 prop。
- 如果文本明确说角色拿着“船桨、缆绳、船篙、灯笼、钥匙、酒壶”等可从大型场景中分离出来的小物件，才把这些小物件作为 prop；不要把承载它们的船或场所本身作为 prop。
- 道具 description 必须同时包含两类信息：一是来历/来源，说明它在原作桥段或当前剧本中从哪里出现、由谁持有/使用/争夺；二是外观/造型，结合世界背景和时代质感描述整体形制、尺寸比例、材质、颜色、装饰、磨损痕迹、用途和可见特征。不得只写来历。
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
    type_label = {"auto": "角色、地点和道具", "character": "角色", "scene": "地点", "prop": "道具"}[asset_type]
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

每个 asset.asset_type 必须是 character、scene 或 prop。地点统一输出 scene，不要输出 location/asset/角色/地点/道具等其他类型名。
character 字段：asset_type, asset_name, asset_tags, matched, matched_asset_id, matched_asset_name, aliases, summary, character_status, appearance_description。
角色 asset_tags 必须先根据当前情景和身份/职业推断服装/稳定造型/稳定配件，再直接写标签；禁止写“默认”“基础”“普通”“无特殊造型”等空泛标签；appearance_description 写至少 40 字的详细稳定视觉设定，禁止“默认装束，无特殊造型描述”。
scene 字段：asset_type, asset_name, asset_tags, matched, matched_asset_id, matched_asset_name, description, location_type, time_of_day。
scene 的 description 写地点本体、原作/世界背景用途、空间结构、场景物件、陈设、布局和装饰风格；time_of_day 写时间、天气和环境氛围；船、马车、建筑、可进入空间归 scene。
prop 字段：asset_type, asset_name, asset_tags, matched, matched_asset_id, matched_asset_name, description, category, related_character。
prop 只能是可独立拿取、使用、赠予、争夺或流转的小型/中型物件；description 必须同时写来历/来源和外观/造型，包含整体形制、尺寸比例、材质、颜色、装饰、磨损痕迹、用途和可见特征。
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
            message="补充缺失资产返回的 JSON 根对象必须是对象。",
            details={"type": type(parsed).__name__},
        )
    return parsed


def _schema_instruction(schema: dict[str, Any]) -> str:
    return f"Target JSON Schema:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"


def _string_input(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _record_input(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
