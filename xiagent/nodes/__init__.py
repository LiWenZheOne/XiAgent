from __future__ import annotations

from xiagent.infrastructure.config import Settings
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.base import AssetRef, BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode


def build_node_registry(settings: Settings) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    registry.register(
        DeepSeekChatNode(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
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
