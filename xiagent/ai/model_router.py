from __future__ import annotations

from dataclasses import dataclass

from xiagent.infrastructure.config import Settings
from xiagent.models import ChatModelRouter
from xiagent.models.providers.deepseek import DeepSeekChatProvider
from xiagent.models.providers.openai_compatible import OpenAICompatibleChatProvider
from xiagent.models.providers.runninghub import (
    RunningHubImageProvider,
    RunningHubTextToImageProvider,
    RunningHubWorkflowProvider,
)
from xiagent.models.types import (
    DeepSeekModelConfig,
    OpenAICompatibleModelConfig,
    RunningHubImageModelConfig,
    RunningHubTextToImageModelConfig,
    RunningHubWorkflowModelConfig,
)


@dataclass(frozen=True, slots=True)
class AiModelRefs:
    deepseek_model: str
    runninghub_image_model: str
    runninghub_text_to_image_model: str
    runninghub_workflow_model: str | None
    openai_compatible_model: str


def build_chat_model_router(settings: Settings) -> tuple[ChatModelRouter, AiModelRefs]:
    deepseek_config = DeepSeekModelConfig(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    runninghub_image_config = RunningHubImageModelConfig(
        api_key=settings.runninghub_image_api_key,
        base_url=settings.runninghub_image_base_url,
        model=settings.runninghub_image_model,
        endpoint=settings.runninghub_image_endpoint,
        default_aspect_ratio=settings.runninghub_image_default_aspect_ratio,
        default_resolution=settings.runninghub_image_default_resolution,
        poll_interval_seconds=settings.runninghub_image_poll_interval_seconds,
        poll_timeout_seconds=settings.runninghub_image_poll_timeout_seconds,
    )
    runninghub_text_config = RunningHubTextToImageModelConfig(
        api_key=settings.runninghub_text_to_image_api_key,
        base_url=settings.runninghub_text_to_image_base_url,
        model=settings.runninghub_text_to_image_model,
        endpoint=settings.runninghub_text_to_image_endpoint,
        default_aspect_ratio=settings.runninghub_text_to_image_default_aspect_ratio,
        default_resolution=settings.runninghub_text_to_image_default_resolution,
        poll_interval_seconds=settings.runninghub_text_to_image_poll_interval_seconds,
        poll_timeout_seconds=settings.runninghub_text_to_image_poll_timeout_seconds,
    )
    runninghub_workflow_config = RunningHubWorkflowModelConfig(
        api_key=settings.runninghub_workflow_api_key,
        base_url=settings.runninghub_workflow_base_url,
        workflow_id=settings.runninghub_workflow_workflow_id,
        instance_type=settings.runninghub_workflow_instance_type,
        api_prefix=settings.runninghub_workflow_api_prefix,
        http_timeout_seconds=settings.runninghub_workflow_http_timeout_seconds,
        upload_timeout_seconds=settings.runninghub_workflow_upload_timeout_seconds,
        use_personal_queue=settings.runninghub_workflow_use_personal_queue,
        poll_interval_seconds=settings.runninghub_workflow_poll_interval_seconds,
        poll_timeout_seconds=settings.runninghub_workflow_poll_timeout_seconds,
    )
    openai_compatible_config = OpenAICompatibleModelConfig(
        api_key=settings.openai_compatible_api_key,
        base_url=settings.openai_compatible_base_url,
        model=settings.openai_compatible_model,
    )
    router = ChatModelRouter()
    router.register_provider(
        "deepseek",
        DeepSeekChatProvider(config=deepseek_config),
    )
    router.register_provider(
        "runninghub_image",
        RunningHubImageProvider(config=runninghub_image_config),
    )
    router.register_provider(
        "runninghub_text_to_image",
        RunningHubTextToImageProvider(config=runninghub_text_config),
    )
    router.register_provider(
        "runninghub_workflow",
        RunningHubWorkflowProvider(config=runninghub_workflow_config),
    )
    router.register_provider(
        "openai_compatible",
        OpenAICompatibleChatProvider(config=openai_compatible_config),
    )
    return router, AiModelRefs(
        deepseek_model=deepseek_config.model,
        runninghub_image_model=runninghub_image_config.model,
        runninghub_text_to_image_model=runninghub_text_config.model,
        runninghub_workflow_model=runninghub_workflow_config.workflow_id,
        openai_compatible_model=openai_compatible_config.model,
    )
