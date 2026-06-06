from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from xiagent.ai import AssetMetadataCapability, ImageGenerationCapability, PromptDraftCapability
from xiagent.core.errors import NotFoundError, ValidationError, XiAgentError
from xiagent.core.services import AssetService, UserService
from xiagent.nodes.ai.image_references import resolve_image_ref_with_asset_service

_UNTRUSTED_REFERENCE_KEYS = {
    "storage_uri",
    "public_url",
    "preview_url",
    "content_url",
    "thumbnail_url",
    "url",
    "image_url",
    "default_variant_storage_uri",
}


@dataclass(slots=True)
class AssetGenerationJob:
    generation_id: str
    user_id: str
    project_id: str
    operation: str
    status: str
    input: dict[str, Any]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generation_id": self.generation_id,
            "operation": self.operation,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        return payload


class AssetGenerationService:
    def __init__(
        self,
        *,
        user_service: UserService,
        asset_service: AssetService,
        prompt_draft_capability: PromptDraftCapability,
        asset_metadata_capability: AssetMetadataCapability,
        image_generation_capability: ImageGenerationCapability,
    ) -> None:
        self._user_service = user_service
        self._asset_service = asset_service
        self.prompt_draft_capability = prompt_draft_capability
        self.asset_metadata_capability = asset_metadata_capability
        self.image_generation_capability = image_generation_capability
        self._jobs: dict[str, AssetGenerationJob] = {}

    async def draft_asset_from_description(
        self,
        *,
        user_id: str,
        project_id: str | None,
        asset_type: str,
        description: str,
        script: str,
        background: str,
        current_assets: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_project_id = _normalize_project_id(project_id)
        await self._ensure_project_access(
            user_id=user_id,
            project_id=normalized_project_id,
            action="asset:preview",
        )
        result = await self.prompt_draft_capability.draft_asset_from_description(
            asset_type=asset_type,
            description=description,
            script=script,
            background=background,
            current_assets=_sanitize_business_input(current_assets),
            max_attempts=2,
        )
        return result.output

    async def complete_upload_metadata(
        self,
        *,
        asset_name: str,
        asset_type: str,
        world_background: str,
    ) -> dict[str, Any]:
        result = await self.asset_metadata_capability.complete_upload_metadata(
            asset_name=asset_name,
            asset_type=asset_type,
            world_background=world_background,
            max_attempts=2,
        )
        return result.output

    async def create_asset_image_generation(
        self,
        *,
        user_id: str,
        project_id: str | None,
        input_payload: dict[str, Any],
    ) -> AssetGenerationJob:
        normalized_project_id = _normalize_project_id(project_id)
        await self._ensure_project_access(
            user_id=user_id,
            project_id=normalized_project_id,
            action="asset:generate",
        )
        generation_id = f"asset_generation_{uuid.uuid4().hex}"
        job = AssetGenerationJob(
            generation_id=generation_id,
            user_id=user_id,
            project_id=normalized_project_id,
            operation="asset_image_generation",
            status="queued",
            input=input_payload,
        )
        self._jobs[generation_id] = job
        return job

    def get_generation(self, *, user_id: str, generation_id: str) -> AssetGenerationJob:
        job = self._jobs.get(generation_id)
        if job is None or job.user_id != user_id:
            raise NotFoundError(
                code="asset_generation_not_found",
                message="Asset generation job was not found",
                details={"generation_id": generation_id},
            )
        return job

    async def run_asset_image_generation(self, *, generation_id: str) -> None:
        job = self._jobs[generation_id]
        self._mark_running(job)
        try:
            result = await self.image_generation_capability.generate_asset_images(
                prompt_results=[job.input["prompt_result"]],
                prompt_prefix=job.input.get("prompt_prefix") or "",
                prompt_suffix=job.input.get("prompt_suffix") or "",
                aspect_ratio=job.input.get("aspect_ratio", "1:1"),
                resolution=job.input.get("resolution", "2k"),
                image_ref_resolver=self._image_ref_resolver(
                    user_id=job.user_id,
                    project_id=job.project_id,
                ),
            )
            images = result.output.get("asset_images")
            if not isinstance(images, list) or not images:
                raise ValidationError(
                    code="asset_image_generation_empty",
                    message="资产图像生成没有返回图像。",
                )
            image = images[0]
            if not isinstance(image, dict):
                raise ValidationError(
                    code="asset_image_generation_invalid",
                    message="资产图像生成返回了无效结果。",
                )
            self._mark_succeeded(job, image)
        except XiAgentError as exc:
            self._mark_failed(
                job,
                {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive background task guard
            self._mark_failed(
                job,
                {
                    "code": "asset_image_generation_failed",
                    "message": str(exc) or "资产图像生成失败。",
                    "details": {},
                },
            )

    def _image_ref_resolver(self, *, user_id: str, project_id: str):
        async def resolver(image_ref: Any) -> str:
            return await resolve_image_ref_with_asset_service(
                user_id=user_id,
                project_id=project_id,
                asset_service=self._asset_service,
                image_ref=image_ref,
            )

        return resolver

    async def _ensure_project_access(self, *, user_id: str, project_id: str, action: str) -> None:
        if project_id != "global":
            await self._user_service.ensure_project_access(
                user_id=user_id,
                project_id=project_id,
                action=action,
            )

    @staticmethod
    def _mark_running(job: AssetGenerationJob) -> None:
        job.status = "running"
        job.updated_at = time.time()

    @staticmethod
    def _mark_succeeded(job: AssetGenerationJob, result: dict[str, Any]) -> None:
        job.status = "succeeded"
        job.result = result
        job.error = None
        job.updated_at = time.time()

    @staticmethod
    def _mark_failed(job: AssetGenerationJob, error: dict[str, Any]) -> None:
        job.status = "failed"
        job.error = error
        job.updated_at = time.time()


def _normalize_project_id(project_id: str | None) -> str:
    return project_id if isinstance(project_id, str) and project_id.strip() else "global"


def _sanitize_business_input(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_business_input(item)
            for key, item in value.items()
            if key not in _UNTRUSTED_REFERENCE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_business_input(item) for item in value]
    return value
