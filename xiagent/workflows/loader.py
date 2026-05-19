from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_workflow_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"workflow file must contain object: {path}")
    return data
