from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    clean_prefix = prefix.strip().lower().replace("-", "_")
    if not clean_prefix:
        raise ValueError("prefix must not be empty")
    return f"{clean_prefix}_{uuid4().hex}"
