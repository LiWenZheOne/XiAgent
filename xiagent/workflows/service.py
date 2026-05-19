from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from xiagent.core.errors import ConflictError, NotFoundError
from xiagent.nodes.registry import NodeRegistry
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.validator import validate_workflow_contract


class WorkflowCatalog:
    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self._contracts: dict[str, dict[str, Any]] = {}
        self._identities: set[str] = set()

    def load_directory(self, directory: Path) -> None:
        for path in sorted(directory.glob("**/*.workflow.yaml")):
            contract = load_workflow_file(path)
            validate_workflow_contract(contract, self._registry)
            workflow = contract["workflow"]
            workflow_id = workflow["id"]
            identity = _workflow_identity(workflow)
            if workflow_id in self._contracts or identity in self._identities:
                raise ConflictError(
                    code="workflow_template_exists",
                    message="工作流模板已存在",
                    details={"workflow_id": workflow_id, "identity": identity},
                )
            self._contracts[workflow_id] = deepcopy(contract)
            self._identities.add(identity)

    def get(self, workflow_id: str) -> dict[str, Any]:
        try:
            contract = self._contracts[workflow_id]
        except KeyError as exc:
            raise NotFoundError(
                code="workflow_template_not_found",
                message="工作流模板不存在",
                details={"workflow_id": workflow_id},
            ) from exc
        return deepcopy(contract)

    def list(self) -> list[dict[str, Any]]:
        return [deepcopy(contract) for contract in self._contracts.values()]


InMemoryWorkflowService = WorkflowCatalog


def _workflow_identity(workflow: dict[str, Any]) -> str:
    return ":".join(
        [
            str(workflow["id"]),
            str(workflow["version"]),
            str(workflow["scope"]),
            str(workflow.get("project_id")),
        ]
    )
