from __future__ import annotations

from xiagent.ai.capabilities import (
    AssetMetadataCapability,
    CapabilityResult,
    ImageGenerationCapability,
    PromptDraftCapability,
    asset_draft_output_schema,
    asset_upload_metadata_output_schema,
)
from xiagent.ai.model_router import AiModelRefs, build_chat_model_router

__all__ = [
    "AiModelRefs",
    "AssetMetadataCapability",
    "CapabilityResult",
    "ImageGenerationCapability",
    "PromptDraftCapability",
    "asset_draft_output_schema",
    "asset_upload_metadata_output_schema",
    "build_chat_model_router",
]
