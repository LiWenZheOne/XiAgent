from __future__ import annotations

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
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.gemini_vision import GeminiVisionNode
from xiagent.nodes.ai.assign_assets_to_segments import AssignAssetsToSegmentsNode
from xiagent.nodes.ai.asset_draft_from_description import AssetDraftFromDescriptionNode
from xiagent.nodes.ai.asset_metadata_from_upload import AssetMetadataFromUploadNode
from xiagent.nodes.ai.runninghub_image import (
    RunningHubImageToImageNode,
    RunningHubImageToImageNodeV2,
    RunningHubImageToImageNodeV3,
    RunningHubTextToImageNode,
)
from xiagent.nodes.base import AssetRef, BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_choice import SystemUserChoiceNode
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.nodes.tools.assemble_segment_context import AssembleSegmentContextNode
from xiagent.nodes.tools.assemble_storyboard_context import AssembleStoryboardContextNode
from xiagent.nodes.tools.asset_lookup import AssetLookupNode
from xiagent.nodes.tools.create_text_asset import CreateTextAssetNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.nodes.tools.merge_asset_images import MergeAssetImagesNode
from xiagent.nodes.tools.complete_asset_images import CompleteAssetImagesNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.nodes.tools.episode_metadata import (
    EpisodeMetadataFinalizeNode,
    EpisodeMetadataFromAssetNode,
)
from xiagent.nodes.tools.filter_assets_for_generation import FilterAssetsForGenerationNode
from xiagent.nodes.tools.resolve_character_variant_refs import ResolveCharacterVariantRefsNode
from xiagent.nodes.tools.runninghub_workflow_images import RunningHubWorkflowImagesNode
from xiagent.nodes.tools.script_split import ScriptSplitNode
from xiagent.nodes.tools.extract_panel_image_urls import ExtractPanelImageUrlsNode
from xiagent.nodes.tools.storyboard_prompt import (
    StoryboardPromptAssemblerNode,
    StoryboardPromptAssemblerNodeV2,
)


def build_node_registry(settings: Settings) -> NodeRegistry:
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
    rh_workflow_config = RunningHubWorkflowModelConfig(
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
        RunningHubWorkflowProvider(config=rh_workflow_config),
    )
    router.register_provider(
        "openai_compatible",
        OpenAICompatibleChatProvider(config=openai_compatible_config),
    )

    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(SystemUserChoiceNode())
    registry.register(SystemUserInputNode())
    registry.register(EchoToolNode())
    registry.register(MergeAssetImagesNode())
    registry.register(CompleteAssetImagesNode())
    registry.register(ScriptSplitNode())
    registry.register(AssembleSegmentContextNode())
    registry.register(AssembleStoryboardContextNode())
    registry.register(AssetLookupNode())
    registry.register(CreateTextAssetNode())
    registry.register(EpisodeMetadataFinalizeNode())
    registry.register(EpisodeMetadataFromAssetNode())
    registry.register(EnrichCharactersNode())
    registry.register(FilterAssetsForGenerationNode())
    registry.register(ResolveCharacterVariantRefsNode())
    registry.register(RunningHubWorkflowImagesNode())
    registry.register(StoryboardPromptAssemblerNode())
    registry.register(StoryboardPromptAssemblerNodeV2())
    registry.register(ExtractPanelImageUrlsNode())
    registry.register(
        AssignAssetsToSegmentsNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
        )
    )
    registry.register(
        DeepSeekChatNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
        )
    )
    registry.register(
        DeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
        )
    )
    registry.register(
        AssetDraftFromDescriptionNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
        )
    )
    registry.register(
        AssetMetadataFromUploadNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
        )
    )
    registry.register(
        ParallelDeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
        )
    )
    registry.register(
        RunningHubImageToImageNode(
            model_router=router,
            provider="runninghub_image",
            model=runninghub_image_config.model,
        )
    )
    registry.register(
        RunningHubImageToImageNodeV2(
            model_router=router,
            provider="runninghub_image",
            model=runninghub_image_config.model,
        )
    )
    registry.register(
        RunningHubImageToImageNodeV3(
            model_router=router,
            provider="runninghub_workflow",
            model=rh_workflow_config.workflow_id,
        )
    )
    registry.register(
        RunningHubTextToImageNode(
            model_router=router,
            provider="runninghub_text_to_image",
            model=runninghub_text_config.model,
        )
    )
    registry.register(
        GeminiVisionNode(
            model_router=router,
            provider="openai_compatible",
            model=openai_compatible_config.model,
        )
    )
    return registry


__all__ = [
    "AssetRef",
    "BaseNode",
    "NodeContext",
    "NodeDescriptor",
    "NodeRegistry",
    "NodeResult",
    "SystemUserChoiceNode",
    "SystemUserInputNode",
    "AssetDraftFromDescriptionNode",
    "AssetMetadataFromUploadNode",
    "EpisodeMetadataFinalizeNode",
    "EpisodeMetadataFromAssetNode",
    "build_node_registry",
]
