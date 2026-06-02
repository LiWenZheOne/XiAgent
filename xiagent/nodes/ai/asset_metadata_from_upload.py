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


class AssetMetadataFromUploadNode(BaseNode):
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
            ref="ai.asset_metadata_from_upload.v1",
            name="资产上传信息补全",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "required": ["asset_name", "asset_type", "world_background"],
                "properties": {
                    "asset_id": {"type": "string"},
                    "asset_name": {"type": "string", "minLength": 1},
                    "asset_type": {"type": "string", "enum": ["character", "location", "prop"]},
                    "world_background": {"type": "string", "minLength": 1},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
            output_schema=_output_schema(),
            description="Complete asset metadata for a newly uploaded library image from its name, type, and source background.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        asset_name = _required_text(inputs.get("asset_name"), "asset_upload_name_required", "资产名称不能为空。")
        asset_type = _asset_type(inputs.get("asset_type"))
        world_background = _required_text(inputs.get("world_background"), "asset_upload_background_required", "世界背景不能为空。")
        max_attempts = inputs.get("max_attempts", 2)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="asset_upload_metadata_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        schema = _output_schema()
        schema_instruction = f"Target JSON Schema:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
        prompt = _user_prompt(asset_name=asset_name, asset_type=asset_type, world_background=world_background)
        current_prompt = prompt
        last_error: ValidationError | None = None

        for attempt in range(max_attempts):
            response = await self._model_router.chat(
                ChatRequest(
                    provider=self._provider,
                    model=self._model,
                    messages=[
                        ChatMessage(role="system", content=f"{_system_prompt(asset_type)}\n\n{schema_instruction}"),
                        ChatMessage(role="user", content=current_prompt),
                    ],
                )
            )
            try:
                parsed = _parse_json_object(response.text)
                validate_json_value(schema, parsed)
            except json.JSONDecodeError as exc:
                last_error = ValidationError(
                    code="asset_upload_metadata_json_parse_failed",
                    message="资产上传信息补全返回的内容不是合法 JSON。",
                    details={"attempt": attempt + 1, "error": str(exc)},
                )
            except ValidationError as exc:
                last_error = ValidationError(
                    code="asset_upload_metadata_json_validation_failed",
                    message="资产上传信息补全返回的 JSON 不符合资产 metadata 结构。",
                    details={"attempt": attempt + 1, "error": exc.details},
                )
            else:
                metadata = dict(parsed["metadata"])
                metadata["type"] = asset_type
                parsed["metadata"] = metadata
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
            code="asset_upload_metadata_json_parse_failed",
            message="资产上传信息补全返回的内容不是合法 JSON。",
        )


def _output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["metadata", "confidence", "reasoning"],
        "properties": {
            "metadata": {
                "type": "object",
                "required": [
                    "type",
                    "asset_tags",
                    "aliases",
                    "summary",
                    "relationships",
                    "character_status",
                    "appearance_description",
                    "description",
                    "location_type",
                    "time_of_day",
                    "category",
                    "related_character",
                ],
                "properties": {
                    "type": {"type": "string", "enum": ["character", "location", "prop"]},
                    "asset_tags": {"type": "array", "items": {"type": "string"}},
                    "aliases": {"type": "string"},
                    "summary": {"type": "string"},
                    "relationships": {"type": "string"},
                    "character_status": {"type": "string"},
                    "appearance_description": {"type": "string"},
                    "description": {"type": "string"},
                    "location_type": {"type": "string"},
                    "time_of_day": {"type": "string"},
                    "category": {"type": "string"},
                    "related_character": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _system_prompt(asset_type: str) -> str:
    label = {"character": "角色资产", "location": "地点资产", "prop": "道具资产"}[asset_type]
    return f"""
仅返回合法 JSON。你是资产库上传信息补全助手，负责根据用户上传时填写的资产名、资产类型和世界背景，为{label}补齐可入库 metadata。

提问式分析要求：
1. 资产名在这个世界背景或原作中指向什么对象？
2. 这个对象作为{label}，用户后续检索和图像生成最需要哪些稳定信息？
3. 哪些字段能从资产名和世界背景可靠推断？哪些字段不能确认？
4. 最终 metadata 要适合资产库详情页编辑和搜索；无法确认的字段返回空字符串，不要编造具体剧情。

通用规则：
- 不要描述材质、布料质感、纹理或面料工艺。
- 不要输出 Markdown、解释文本或代码块。
- metadata.type 必须使用英文类型：character、location、prop。

角色资产规则：
- summary 只写生平背景、身份定位或原作人物背景，不写当前镜头状态。
- relationships 写社会关系、阵营关系、师徒/亲友/敌对等关系。
- character_status 写可从资产名和世界背景推断的阶段性状态；不确定则留空。
- asset_tags 根据身份、职业、时代和世界背景推断稳定服装、稳定造型和稳定配件标签，禁止写“默认”“基础”“普通”等空泛词。
- appearance_description 只描述图像中角色可见的外貌特征和稳定造型，可包含头部/发型、上身、颜色搭配、身份识别特征、稳定配件；不要写用途、生成目的、动作、表情、受伤、奔跑、被绑等临时状态。
- 稳定配件写入 asset_tags，不单独输出配件字段。

地点资产规则：
- description 说明地点是什么、在哪里、在原作/世界背景中用来做什么。
- location_type 写简短地点类别，例如山寨、酒楼、江河、官府、民居、战场。
- time_of_day 只有资产名或世界背景明确暗示时填写，否则留空。

道具资产规则：
- description 说明道具是什么、用途和世界背景中的意义。
- category 写简短类别，例如武器、文书、载具、器皿、信物。
- related_character 只有资产名或世界背景明确关联角色时填写。
""".strip()


def _user_prompt(*, asset_name: str, asset_type: str, world_background: str) -> str:
    label = {"character": "角色", "location": "地点", "prop": "道具"}[asset_type]
    return f"""
请为上传到资产库的{label}补齐 metadata。

## 资产名
{asset_name}

## 资产类型
{asset_type}

## 世界背景 / 原作
{world_background}

## 输出要求
返回 JSON 对象：
- metadata：字段对象，必须包含 schema 要求的所有字段；与该类型无关且无法确认的字段用空字符串。
- confidence：0 到 1 的数字。
- reasoning：一句话说明补全依据。
""".strip()


def _asset_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "character": "character",
        "role": "character",
        "角色": "character",
        "location": "location",
        "scene": "location",
        "地点": "location",
        "场景": "location",
        "prop": "prop",
        "item": "prop",
        "道具": "prop",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError(
            code="asset_upload_type_invalid",
            message="资产类型只能是角色、地点或道具。",
            details={"asset_type": value},
        ) from exc


def _required_text(value: Any, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(code=code, message=message)
    return value.strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    match = _JSON_FENCE_PATTERN.search(candidate)
    if match is not None:
        candidate = match.group(1).strip()
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValidationError(
            code="asset_upload_metadata_json_validation_failed",
            message="资产上传信息补全返回的 JSON 根对象必须是对象。",
            details={"type": type(parsed).__name__},
        )
    return parsed
