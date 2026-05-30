from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from xiagent.core.errors import NotFoundError


@dataclass(slots=True)
class ImageGenerationJob:
    generation_id: str
    user_id: str
    project_id: str
    status: str
    input: dict[str, Any]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generation_id": self.generation_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        return payload


class ImageGenerationStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ImageGenerationJob] = {}

    def create(
        self,
        *,
        user_id: str,
        project_id: str,
        input_payload: dict[str, Any],
    ) -> ImageGenerationJob:
        generation_id = f"image_generation_{uuid.uuid4().hex}"
        job = ImageGenerationJob(
            generation_id=generation_id,
            user_id=user_id,
            project_id=project_id,
            status="queued",
            input=input_payload,
        )
        self._jobs[generation_id] = job
        return job

    def get(self, *, user_id: str, generation_id: str) -> ImageGenerationJob:
        job = self._jobs.get(generation_id)
        if job is None or job.user_id != user_id:
            raise NotFoundError(
                code="image_generation_not_found",
                message="Image generation job was not found",
                details={"generation_id": generation_id},
            )
        return job

    def mark_running(self, generation_id: str) -> None:
        job = self._jobs[generation_id]
        job.status = "running"
        job.updated_at = time.time()

    def mark_succeeded(self, generation_id: str, result: dict[str, Any]) -> None:
        job = self._jobs[generation_id]
        job.status = "succeeded"
        job.result = result
        job.error = None
        job.updated_at = time.time()

    def mark_failed(self, generation_id: str, error: dict[str, Any]) -> None:
        job = self._jobs[generation_id]
        job.status = "failed"
        job.error = error
        job.updated_at = time.time()
