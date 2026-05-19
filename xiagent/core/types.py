from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
    COMBINED = "combined"


class StoredScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class NodeExecutionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NodeResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    WAITING = "waiting"
    FAILED = "failed"


class AssetType(StrEnum):
    FILE = "file"
    TEXT = "text"
