from __future__ import annotations

from xiagent.infrastructure.config import Settings
from xiagent.models import ChatModelRouter
from xiagent.models.providers.deepseek import DeepSeekChatProvider
from xiagent.models.providers.runninghub import (
    RunningHubImageProvider,
    RunningHubTextToImageProvider,
)
from xiagent.models.types import (
    DeepSeekModelConfig,
    RunningHubImageModelConfig,
    RunningHubTextToImageModelConfig,
)
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.ai.deepseek_structured_json import DeepSeekStructuredJsonNode
from xiagent.nodes.ai.parallel_deepseek_structured_json import (
    ParallelDeepSeekStructuredJsonNode,
)
from xiagent.nodes.ai.runninghub_image import (
    RunningHubImageToImageNode,
    RunningHubTextToImageNode,
)
from xiagent.nodes.base import AssetRef, BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.assemble_segment_context import AssembleSegmentContextNode
from xiagent.nodes.tools.asset_lookup import AssetLookupNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.nodes.tools.script_split import ScriptSplitNode
from xiagent.nodes.tools.storyboard_prompt import StoryboardPromptAssemblerNode


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
        poll_interval_seconds=settings.runninghub_image_poll_interval_seconds,
        poll_timeout_seconds=settings.runninghub_image_poll_timeout_seconds,
    )
    runninghub_text_config = RunningHubTextToImageModelConfig(
        api_key=settings.runninghub_text_to_image_api_key,
        base_url=settings.runninghub_text_to_image_base_url,
        model=settings.runninghub_text_to_image_model,
        endpoint=settings.runninghub_text_to_image_endpoint,
        poll_interval_seconds=settings.runninghub_text_to_image_poll_interval_seconds,
        poll_timeout_seconds=settings.runninghub_text_to_image_poll_timeout_seconds,
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

    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    registry.register(ScriptSplitNode())
    registry.register(AssembleSegmentContextNode())
    registry.register(AssetLookupNode())
    registry.register(StoryboardPromptAssemblerNode())
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
        RunningHubTextToImageNode(
            model_router=router,
            provider="runninghub_text_to_image",
            model=runninghub_text_config.model,
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
    "build_node_registry",
]
