from __future__ import annotations

from xiagent.ai import build_chat_model_router
from xiagent.infrastructure.config import Settings
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.storyboard_review_refine import StoryboardReviewRefineNode
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
from xiagent.nodes.tools.merge_segment_storyboard_descriptions import (
    MergeSegmentStoryboardDescriptionsNode,
)
from xiagent.nodes.tools.prepare_segment_storyboard_inputs import (
    PrepareSegmentStoryboardInputsNode,
)
from xiagent.nodes.tools.prepare_asset_semantic_match import PrepareAssetSemanticMatchNode
from xiagent.nodes.tools.prepare_storyboard_panel_cards import (
    PrepareStoryboardPanelCardsNode,
)
from xiagent.nodes.tools.prepare_storyboard_asset_index import (
    PrepareStoryboardAssetIndexNode,
)
from xiagent.nodes.tools.complete_asset_images import CompleteAssetImagesNode
from xiagent.nodes.tools.enrich_characters import EnrichCharactersNode
from xiagent.nodes.tools.episode_metadata import (
    EpisodeMetadataFinalizeNode,
    EpisodeMetadataFromAssetNode,
)
from xiagent.nodes.tools.filter_assets_for_generation import FilterAssetsForGenerationNode
from xiagent.nodes.tools.resolve_accessory_asset_refs import ResolveAccessoryAssetRefsNode
from xiagent.nodes.tools.resolve_character_variant_refs import ResolveCharacterVariantRefsNode
from xiagent.nodes.tools.resolve_segment_image_refs import ResolveSegmentImageRefsNode
from xiagent.nodes.tools.runninghub_workflow_images import RunningHubWorkflowImagesNode
from xiagent.nodes.tools.script_split import ScriptSplitNode
from xiagent.nodes.tools.extract_panel_image_urls import ExtractPanelImageUrlsNode
from xiagent.nodes.tools.storyboard_task_summary import StoryboardTaskSummaryNode
from xiagent.nodes.tools.storyboard_prompt import (
    StoryboardPromptAssemblerNode,
    StoryboardPromptAssemblerNodeV2,
)


def build_node_registry(settings: Settings) -> NodeRegistry:
    router, model_refs = build_chat_model_router(settings)

    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(SystemUserChoiceNode())
    registry.register(SystemUserInputNode())
    registry.register(EchoToolNode())
    registry.register(MergeAssetImagesNode())
    registry.register(MergeSegmentStoryboardDescriptionsNode())
    registry.register(PrepareSegmentStoryboardInputsNode())
    registry.register(PrepareAssetSemanticMatchNode())
    registry.register(PrepareStoryboardPanelCardsNode())
    registry.register(PrepareStoryboardAssetIndexNode())
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
    registry.register(ResolveAccessoryAssetRefsNode())
    registry.register(ResolveCharacterVariantRefsNode())
    registry.register(ResolveSegmentImageRefsNode())
    registry.register(RunningHubWorkflowImagesNode())
    registry.register(StoryboardPromptAssemblerNode())
    registry.register(StoryboardPromptAssemblerNodeV2())
    registry.register(ExtractPanelImageUrlsNode())
    registry.register(StoryboardTaskSummaryNode())
    registry.register(
        AssignAssetsToSegmentsNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        DeepSeekChatNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        DeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        AssetDraftFromDescriptionNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        AssetMetadataFromUploadNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        ParallelDeepSeekStructuredJsonNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        StoryboardReviewRefineNode(
            model_router=router,
            provider="deepseek",
            model=model_refs.deepseek_model,
        )
    )
    registry.register(
        RunningHubImageToImageNode(
            model_router=router,
            provider="runninghub_image",
            model=model_refs.runninghub_image_model,
        )
    )
    registry.register(
        RunningHubImageToImageNodeV2(
            model_router=router,
            provider="runninghub_image",
            model=model_refs.runninghub_image_model,
        )
    )
    registry.register(
        RunningHubImageToImageNodeV3(
            model_router=router,
            provider="runninghub_workflow",
            model=model_refs.runninghub_workflow_model,
        )
    )
    registry.register(
        RunningHubTextToImageNode(
            model_router=router,
            provider="runninghub_text_to_image",
            model=model_refs.runninghub_text_to_image_model,
        )
    )
    registry.register(
        GeminiVisionNode(
            model_router=router,
            provider="openai_compatible",
            model=model_refs.openai_compatible_model,
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
    "StoryboardTaskSummaryNode",
    "build_node_registry",
]
