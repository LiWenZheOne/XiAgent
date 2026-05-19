from __future__ import annotations

from xiagent.infrastructure.config import Settings
from xiagent.models import ChatModelRouter
from xiagent.models.providers.deepseek import DeepSeekChatProvider
from xiagent.models.types import DeepSeekModelConfig
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.base import AssetRef, BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode


def build_node_registry(settings: Settings) -> NodeRegistry:
    deepseek_config = DeepSeekModelConfig(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    router = ChatModelRouter()
    router.register_provider(
        "deepseek",
        DeepSeekChatProvider(config=deepseek_config),
    )

    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    registry.register(
        DeepSeekChatNode(
            model_router=router,
            provider="deepseek",
            model=deepseek_config.model,
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
