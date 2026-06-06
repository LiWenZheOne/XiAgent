from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest, ChatResponse

ImageRefResolver = Callable[[Any], Awaitable[str]]

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_JSON_OBJECT_RESPONSE_FORMAT = {"type": "json_object"}


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    output: dict[str, Any]
    metadata: dict[str, Any]


class PromptDraftCapability:
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

    async def draft_asset_from_description(
        self,
        *,
        asset_type: str = "auto",
        description: Any,
        script: Any = "",
        background: Any = "",
        current_assets: Any = None,
        max_attempts: Any = 2,
    ) -> CapabilityResult:
        normalized_asset_type = _draft_asset_type(str(asset_type or "auto"))
        if not isinstance(description, str) or not description.strip():
            raise ValidationError(
                code="asset_draft_description_required",
                message="请先描述需要新增的资产特征。",
            )
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="asset_draft_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        schema = asset_draft_output_schema(normalized_asset_type)
        schema_instruction = _schema_instruction(schema)
        system_prompt = _asset_draft_system_prompt(normalized_asset_type)
        prompt = _asset_draft_user_prompt(
            asset_type=normalized_asset_type,
            description=description.strip(),
            script=_string_input(script),
            background=_string_input(background),
            current_assets=_record_input(current_assets),
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
                    metadata=_json_object_response_metadata(),
                )
            )
            try:
                parsed = _parse_json_object(
                    response.text,
                    code="asset_draft_json_validation_failed",
                    message="补充缺失资产返回的 JSON 根对象必须是对象。",
                )
                validate_json_value(schema, parsed)
            except json.JSONDecodeError as exc:
                last_error = ValidationError(
                    code="asset_draft_json_parse_failed",
                    message="补充缺失资产返回的内容不是合法 JSON。",
                    details={"attempt": attempt + 1, "error": str(exc)},
                )
            except ValidationError as exc:
                last_error = ValidationError(
                    code="asset_draft_json_validation_failed",
                    message="补充缺失资产返回的 JSON 不符合资产草稿结构。",
                    details={"attempt": attempt + 1, "error": exc.details},
                )
            else:
                return CapabilityResult(output=parsed, metadata=response.metadata)

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
            message="补充缺失资产返回的内容不是合法 JSON。",
        )


class AssetMetadataCapability:
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

    async def complete_upload_metadata(
        self,
        *,
        asset_name: Any,
        asset_type: Any,
        world_background: Any,
        max_attempts: Any = 2,
    ) -> CapabilityResult:
        clean_name = _required_text(asset_name, "asset_upload_name_required", "资产名称不能为空。")
        normalized_asset_type = _upload_asset_type(asset_type)
        clean_background = _required_text(world_background, "asset_upload_background_required", "世界背景不能为空。")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="asset_upload_metadata_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        schema = asset_upload_metadata_output_schema()
        schema_instruction = _schema_instruction(schema)
        prompt = _asset_upload_user_prompt(
            asset_name=clean_name,
            asset_type=normalized_asset_type,
            world_background=clean_background,
        )
        current_prompt = prompt
        last_error: ValidationError | None = None

        for attempt in range(max_attempts):
            response = await self._model_router.chat(
                ChatRequest(
                    provider=self._provider,
                    model=self._model,
                    messages=[
                        ChatMessage(
                            role="system",
                            content=f"{_asset_upload_system_prompt(normalized_asset_type)}\n\n{schema_instruction}",
                        ),
                        ChatMessage(role="user", content=current_prompt),
                    ],
                    metadata=_json_object_response_metadata(),
                )
            )
            try:
                parsed = _parse_json_object(
                    response.text,
                    code="asset_upload_metadata_json_validation_failed",
                    message="资产上传信息补全返回的 JSON 根对象必须是对象。",
                )
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
                metadata["type"] = normalized_asset_type
                parsed["metadata"] = metadata
                return CapabilityResult(output=parsed, metadata=response.metadata)

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


class ImageGenerationCapability:
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

    async def generate_image_to_image(
        self,
        *,
        prompt: Any,
        image_refs: Any,
        image_ref_resolver: ImageRefResolver,
        aspect_ratio: Any = None,
        resolution: Any = None,
        temperature: Any = None,
        poll_interval_seconds: Any = None,
        poll_timeout_seconds: Any = None,
    ) -> CapabilityResult:
        clean_prompt = _required_mapping_text({"prompt": prompt}, "prompt", "runninghub_prompt_required")
        clean_refs = _required_image_refs(image_refs)
        metadata = _runninghub_metadata(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            temperature=temperature,
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
        )
        metadata["images"] = [await image_ref_resolver(image_ref) for image_ref in clean_refs]
        response = await self._model_router.chat(
            ChatRequest(
                provider=self._provider,
                model=self._model,
                messages=[ChatMessage(role="user", content=clean_prompt)],
                metadata=metadata,
            )
        )
        return CapabilityResult(output=_response_output(response), metadata=response.metadata)

    async def generate_text_to_image(
        self,
        *,
        prompt: Any,
        aspect_ratio: Any = None,
        resolution: Any = None,
        poll_interval_seconds: Any = None,
        poll_timeout_seconds: Any = None,
    ) -> CapabilityResult:
        clean_prompt = _required_mapping_text({"prompt": prompt}, "prompt", "runninghub_prompt_required")
        metadata = _runninghub_metadata(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
        )
        response = await self._model_router.chat(
            ChatRequest(
                provider=self._provider,
                model=self._model,
                messages=[ChatMessage(role="user", content=clean_prompt)],
                metadata=metadata,
            )
        )
        return CapabilityResult(output=_response_output(response), metadata=response.metadata)

    async def generate_asset_images(
        self,
        *,
        prompt_results: Any,
        image_ref_resolver: ImageRefResolver,
        prompt_prefix: Any = "",
        prompt_suffix: Any = "",
        aspect_ratio: Any = None,
        resolution: Any = None,
        poll_interval_seconds: Any = None,
        poll_timeout_seconds: Any = None,
    ) -> CapabilityResult:
        clean_prompt_results = _required_prompt_results(prompt_results)
        metadata_base = _runninghub_metadata(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
        )

        async def generate_one(item: Mapping[str, Any]) -> dict[str, Any]:
            normalized_item = _normalize_asset_record(item)
            legacy_full_name = _optional_text(item, "full_name")
            asset_name = _optional_text(normalized_item, "asset_name") or legacy_full_name
            if asset_name is None:
                raise ValidationError(
                    code="runninghub_asset_name_required",
                    message="RunningHub prompt result requires asset_name.",
                )
            if "asset_name" not in normalized_item:
                normalized_item["asset_name"] = asset_name
            prompt = _image_to_image_prompt(
                _required_mapping_text(item, "prompt", "runninghub_prompt_required"),
                prompt_prefix=prompt_prefix,
                prompt_suffix=prompt_suffix,
            )
            reference_image_ref = item.get("reference_image_ref")

            char_metadata = dict(metadata_base)
            char_metadata["reference_image_ref"] = _public_image_ref_metadata(reference_image_ref)
            char_metadata["images"] = [await image_ref_resolver(reference_image_ref)]

            response = await self._model_router.chat(
                ChatRequest(
                    provider=self._provider,
                    model=self._model,
                    messages=[ChatMessage(role="user", content=prompt)],
                    metadata=char_metadata,
                )
            )

            asset_result: dict[str, Any] = {
                "image_url": response.text,
                "source": "ai_generated",
            }
            for key in ("asset_type", "asset_name", "asset_tags"):
                value = normalized_item.get(key)
                if value:
                    asset_result[key] = value
            task_id = response.metadata.get("task_id")
            if isinstance(task_id, str):
                asset_result["runninghub_task_id"] = task_id
            asset_id = response.metadata.get("asset_id")
            if isinstance(asset_id, str):
                asset_result["asset_id"] = asset_id
            variant = response.metadata.get("variant")
            if isinstance(variant, str):
                asset_result["variant"] = variant
            if legacy_full_name is not None:
                asset_result["full_name"] = legacy_full_name
            return asset_result

        asset_images = await asyncio.gather(*(generate_one(item) for item in clean_prompt_results))
        return CapabilityResult(output={"asset_images": list(asset_images)}, metadata={})

    async def generate_runninghub_workflow_image(
        self,
        *,
        prompt: Any,
        image_urls: Any,
        node_mapping: Any,
        poll_interval_seconds: Any = None,
        poll_timeout_seconds: Any = None,
    ) -> CapabilityResult:
        clean_prompt = _required_mapping_text({"prompt": prompt}, "prompt", "runninghub_v3_prompt_required")
        clean_image_urls = [item for item in image_urls if isinstance(item, str) and item.strip()] if isinstance(image_urls, list) else []
        if not clean_image_urls:
            raise ValidationError(
                code="runninghub_v3_image_urls_required",
                message="V3 image_urls required",
            )
        if not isinstance(node_mapping, Mapping):
            raise ValidationError(
                code="runninghub_v3_node_mapping_required",
                message="V3 node_mapping required",
            )
        metadata: dict[str, Any] = {"image_urls": clean_image_urls, "node_mapping": dict(node_mapping)}
        poll_interval = _optional_number_value(poll_interval_seconds)
        if poll_interval is not None:
            metadata["poll_interval_seconds"] = poll_interval
        poll_timeout = _optional_number_value(poll_timeout_seconds)
        if poll_timeout is not None:
            metadata["poll_timeout_seconds"] = poll_timeout
        response = await self._model_router.chat(
            ChatRequest(
                provider=self._provider,
                model=self._model,
                messages=[ChatMessage(role="user", content=clean_prompt)],
                metadata=metadata,
            )
        )
        return CapabilityResult(output=_response_output(response), metadata=response.metadata)


def asset_draft_output_schema(asset_type: str) -> dict[str, Any]:
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


def asset_upload_metadata_output_schema() -> dict[str, Any]:
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
scene 的 description 写地点本体、原作/世界背景用途、空间结构、场景物件、陈设、布局和装饰风格；船、马车、建筑、可进入空间归 scene。
prop 字段：asset_type, asset_name, asset_tags, matched, matched_asset_id, matched_asset_name, description, category, related_character。
prop 只能是可独立拿取、使用、赠予、争夺或流转的小型/中型物件；description 必须同时写来历/来源和外观/造型，包含整体形制、尺寸比例、材质、颜色、装饰、磨损痕迹、用途和可见特征。
新增资产默认 matched=false、matched_asset_id=null、matched_asset_name=""。
""".strip()


def _asset_upload_system_prompt(asset_type: str) -> str:
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


def _asset_upload_user_prompt(*, asset_name: str, asset_type: str, world_background: str) -> str:
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


def _upload_asset_type(value: Any) -> str:
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


def _response_output(response: ChatResponse) -> dict[str, Any]:
    metadata = response.metadata
    results = metadata.get("results")
    output: dict[str, Any] = {
        "image_url": response.text,
        "model": response.model,
        "usage": response.usage,
        "results": _public_results(results),
    }
    task_id = metadata.get("task_id")
    if isinstance(task_id, str):
        output["task_id"] = task_id
    status = metadata.get("status")
    if isinstance(status, str):
        output["status"] = status
    return output


def _public_results(results: Any) -> list[dict[str, str]]:
    if not isinstance(results, list):
        return []
    public_results: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        public_result: dict[str, str] = {}
        url = _mapping_text(result, "url")
        if url is not None:
            public_result["url"] = url
        text = _mapping_text(result, "text")
        if text is not None:
            public_result["text"] = text
        output_type = _mapping_text(result, "output_type") or _mapping_text(result, "outputType")
        if output_type is not None:
            public_result["output_type"] = output_type
        if public_result:
            public_results.append(public_result)
    return public_results


def _runninghub_metadata(
    *,
    aspect_ratio: Any = None,
    resolution: Any = None,
    temperature: Any = None,
    poll_interval_seconds: Any = None,
    poll_timeout_seconds: Any = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    clean_aspect_ratio = _optional_text_value(aspect_ratio)
    if clean_aspect_ratio is not None:
        metadata["aspect_ratio"] = clean_aspect_ratio
    clean_resolution = _optional_text_value(resolution)
    if clean_resolution is not None:
        metadata["resolution"] = clean_resolution
    clean_poll_interval = _optional_number_value(poll_interval_seconds)
    if clean_poll_interval is not None:
        metadata["poll_interval_seconds"] = clean_poll_interval
    clean_poll_timeout = _optional_number_value(poll_timeout_seconds)
    if clean_poll_timeout is not None:
        metadata["poll_timeout_seconds"] = clean_poll_timeout
    clean_temperature = _optional_number_value(temperature)
    if clean_temperature is not None:
        metadata["temperature"] = clean_temperature
    return metadata


def _image_to_image_prompt(prompt: str, *, prompt_prefix: Any, prompt_suffix: Any) -> str:
    prefix = _optional_text_value(prompt_prefix) or ""
    suffix = _optional_text_value(prompt_suffix) or ""
    body = f"{prefix.strip()}{prompt.strip()}" if prefix else prompt.strip()
    body = _strip_trailing_prompt_punctuation(body)
    suffix = _strip_trailing_prompt_punctuation(suffix)
    return f"{body}，{suffix}" if suffix else body


def _strip_trailing_prompt_punctuation(value: str) -> str:
    return value.strip().rstrip("。．.，,、；;：:")


def _public_image_ref_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {"kind": value.get("kind")}
    asset_id = value.get("asset_id")
    if isinstance(asset_id, str) and asset_id.strip():
        result["asset_id"] = asset_id.strip()
    role = value.get("role")
    if isinstance(role, str) and role.strip():
        result["role"] = role.strip()
    if result.get("kind") == "data_uri":
        result["data_uri"] = True
    return result


_ASSET_TYPE_TAGS: dict[str, str] = {
    "character": "角色",
    "scene": "地点",
    "prop": "道具",
    "episode_metadata": "集元数据",
    "asset": "资产",
}
_ASSET_TAG_TYPES: dict[str, str] = {value: key for key, value in _ASSET_TYPE_TAGS.items()}
_REMOVED_ASSET_FIELDS = {
    "full_name",
    "asset_key",
    "variant_name",
    "variant",
    "new_variant_name",
    "matched_variant",
    "matched_variant_id",
    "required_tags",
    "reference_assets",
    "accessories",
}


def _normalize_asset_record(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: item for key, item in value.items() if key not in _REMOVED_ASSET_FIELDS}
    asset_type = _asset_type_from_record(value)
    asset_name = _asset_name_from_record(value)
    asset_tags = _asset_tags_from_record(value, asset_type=asset_type, asset_name=asset_name)
    if asset_type:
        result["asset_type"] = asset_type
    if asset_name:
        result["asset_name"] = asset_name
    if asset_tags:
        result["asset_tags"] = asset_tags
    return result


def _asset_type_from_record(value: Mapping[str, Any]) -> str:
    raw = _optional_text_value(value.get("asset_type")) or ""
    if raw in _ASSET_TYPE_TAGS:
        return raw
    if raw in _ASSET_TAG_TYPES:
        return _ASSET_TAG_TYPES[raw]
    tags = _string_list(value.get("tags"))
    if tags and tags[0] in _ASSET_TAG_TYPES:
        return _ASSET_TAG_TYPES[tags[0]]
    name = _optional_text_value(value.get("name")) or ""
    parts = _split_composite_name(name)
    if parts and parts[0] in _ASSET_TAG_TYPES:
        return _ASSET_TAG_TYPES[parts[0]]
    return ""


def _asset_name_from_record(value: Mapping[str, Any]) -> str:
    explicit = _optional_text_value(value.get("asset_name"))
    if explicit:
        return explicit
    raw = _optional_text_value(value.get("name")) or ""
    if raw:
        parts = _split_composite_name(raw)
        if len(parts) >= 2 and parts[0] in _ASSET_TAG_TYPES:
            return parts[1]
        return raw
    tags = _string_list(value.get("tags"))
    if len(tags) >= 2 and tags[0] in _ASSET_TAG_TYPES:
        return tags[1]
    return ""


def _asset_tags_from_record(value: Mapping[str, Any], *, asset_type: str, asset_name: str) -> list[str]:
    tags = _string_list(value.get("asset_tags"))
    if tags:
        return _clean_tags(tags, asset_type=asset_type, asset_name=asset_name)
    name = _optional_text_value(value.get("name")) or ""
    parts = _split_composite_name(name)
    if len(parts) >= 2 and parts[0] in _ASSET_TAG_TYPES:
        return _clean_tags(parts[2:], asset_type=asset_type, asset_name=asset_name)
    library_tags = _string_list(value.get("tags"))
    if library_tags:
        return _clean_tags(library_tags, asset_type=asset_type, asset_name=asset_name)
    return []


def _clean_tags(tags: list[str], *, asset_type: str, asset_name: str) -> list[str]:
    type_tag = _ASSET_TYPE_TAGS.get(asset_type, "")
    result: list[str] = []
    for tag in tags:
        clean = tag.strip()
        if not clean or clean == type_tag or clean == asset_name:
            continue
        if clean not in result:
            result.append(clean)
    return result


def _split_composite_name(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.replace("＿", "_").split("_") if part.strip()]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _required_prompt_results(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) == 0:
        raise ValidationError(
            code="runninghub_prompt_results_required",
            message="prompt_results must be a non-empty array",
        )
    if not all(isinstance(item, Mapping) for item in value):
        raise ValidationError(
            code="runninghub_prompt_results_invalid",
            message="prompt_results items must be objects",
        )
    return value


def _required_image_refs(value: Any) -> list[Any]:
    if isinstance(value, list) and value:
        return value
    raise ValidationError(
        code="image_refs_required",
        message="RunningHub image-to-image requires at least one image reference",
    )


def _required_mapping_text(inputs: Mapping[str, Any], key: str, code: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            code=code,
            message=f"RunningHub {key} cannot be empty",
        )
    return value.strip()


def _mapping_text(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    return item.strip() if isinstance(item, str) and item.strip() else None


def _optional_text(inputs: Mapping[str, Any], key: str) -> str | None:
    return _optional_text_value(inputs.get(key))


def _optional_text_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_number_value(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int | float) else None


def _parse_json_object(text: str, *, code: str, message: str) -> dict[str, Any]:
    candidate = text.strip()
    match = _JSON_FENCE_PATTERN.search(candidate)
    if match is not None:
        candidate = match.group(1).strip()
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValidationError(
            code=code,
            message=message,
            details={"type": type(parsed).__name__},
        )
    return parsed


def _schema_instruction(schema: dict[str, Any]) -> str:
    return f"Target JSON Schema:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"


def _json_object_response_metadata() -> dict[str, dict[str, str]]:
    return {"response_format": dict(_JSON_OBJECT_RESPONSE_FORMAT)}


def _string_input(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _record_input(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _required_text(value: Any, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(code=code, message=message)
    return value.strip()
