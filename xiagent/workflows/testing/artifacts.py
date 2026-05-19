from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import webbrowser
from dataclasses import asdict, dataclass, is_dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_DATA_URL_PATTERN = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ImageArtifact:
    node_id: str
    node_ref: str
    snapshot_kind: str
    field_path: str
    path: Path
    mime_type: str
    source_type: str


def collect_image_artifacts(
    node_executions: Iterable[Any],
    *,
    output_dir: Path,
) -> list[ImageArtifact]:
    artifacts: list[ImageArtifact] = []
    image_dir = output_dir / "images"

    for execution in node_executions:
        for snapshot_kind, snapshot in (
            ("input", execution.input_snapshot),
            ("output", execution.output_snapshot),
        ):
            artifacts.extend(
                _collect_from_value(
                    value=snapshot,
                    execution=execution,
                    snapshot_kind=snapshot_kind,
                    field_path=snapshot_kind,
                    image_dir=image_dir,
                    data_url_counter=len(artifacts),
                )
            )

    return artifacts


def generate_html_preview(
    *,
    task: Any,
    node_executions: Iterable[Any],
    events: Iterable[Any],
    artifacts: Iterable[ImageArtifact],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_list = list(artifacts)
    payload = {
        "task": _to_jsonable(task),
        "events": [_to_jsonable(event) for event in events],
        "node_executions": [_to_jsonable(execution) for execution in node_executions],
        "artifacts": [_to_jsonable(artifact) for artifact in artifact_list],
    }

    images_html = "\n".join(_render_artifact_image(artifact) for artifact in artifact_list)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Workflow Test Preview - {escape(str(getattr(task, "workflow_id", "")))}</title>
  <style>
    body {{
      color: #1f2933;
      font-family: Arial, sans-serif;
      line-height: 1.5;
      margin: 24px;
    }}
    img {{
      border: 1px solid #d5d9de;
      display: block;
      margin-top: 8px;
      max-width: min(100%, 960px);
    }}
    pre {{
      background: #f5f7fa;
      border: 1px solid #d5d9de;
      overflow: auto;
      padding: 12px;
    }}
  </style>
</head>
<body>
  <h1>{escape(str(getattr(task, "workflow_id", "")))}</h1>
  <section>
    <h2>Images</h2>
    {images_html}
  </section>
  <section>
    <h2>Task JSON</h2>
    <pre>{escape(json.dumps(payload["task"], ensure_ascii=False, indent=2))}</pre>
  </section>
  <section>
    <h2>Events JSON</h2>
    <pre>{escape(json.dumps(payload["events"], ensure_ascii=False, indent=2))}</pre>
  </section>
  <section>
    <h2>Node Executions JSON</h2>
    <pre>{escape(json.dumps(payload["node_executions"], ensure_ascii=False, indent=2))}</pre>
  </section>
  <section>
    <h2>Artifacts JSON</h2>
    <pre>{escape(json.dumps(payload["artifacts"], ensure_ascii=False, indent=2))}</pre>
  </section>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def open_artifact_paths(
    paths: Iterable[Path],
    *,
    opener: Callable[[Path], Any] | None = None,
) -> None:
    open_path = opener or _default_open_path
    for path in paths:
        open_path(Path(path))


def open_html_preview(path: Path) -> None:
    webbrowser.open(Path(path).resolve().as_uri())


def _collect_from_value(
    *,
    value: Any,
    execution: Any,
    snapshot_kind: str,
    field_path: str,
    image_dir: Path,
    data_url_counter: int,
) -> list[ImageArtifact]:
    if isinstance(value, dict):
        explicit = _artifact_from_image_object(
            value=value,
            execution=execution,
            snapshot_kind=snapshot_kind,
            field_path=field_path,
        )
        if explicit is not None:
            return [explicit]

        artifacts: list[ImageArtifact] = []
        for key, item in value.items():
            artifacts.extend(
                _collect_from_value(
                    value=item,
                    execution=execution,
                    snapshot_kind=snapshot_kind,
                    field_path=f"{field_path}.{key}",
                    image_dir=image_dir,
                    data_url_counter=data_url_counter + len(artifacts),
                )
            )
        return artifacts

    if isinstance(value, list):
        artifacts = []
        for index, item in enumerate(value):
            artifacts.extend(
                _collect_from_value(
                    value=item,
                    execution=execution,
                    snapshot_kind=snapshot_kind,
                    field_path=f"{field_path}[{index}]",
                    image_dir=image_dir,
                    data_url_counter=data_url_counter + len(artifacts),
                )
            )
        return artifacts

    if isinstance(value, str):
        path_artifact = _artifact_from_path_string(
            value=value,
            execution=execution,
            snapshot_kind=snapshot_kind,
            field_path=field_path,
        )
        if path_artifact is not None:
            return [path_artifact]

        data_url_artifact = _artifact_from_data_url(
            value=value,
            execution=execution,
            snapshot_kind=snapshot_kind,
            field_path=field_path,
            image_dir=image_dir,
            counter=data_url_counter,
        )
        if data_url_artifact is not None:
            return [data_url_artifact]

    return []


def _artifact_from_image_object(
    *,
    value: dict[str, Any],
    execution: Any,
    snapshot_kind: str,
    field_path: str,
) -> ImageArtifact | None:
    if value.get("type") != "image" or not isinstance(value.get("path"), str):
        return None

    path = Path(value["path"])
    mime_type = str(value.get("mime_type") or _mime_type_for_path(path))
    return ImageArtifact(
        node_id=execution.node_id,
        node_ref=execution.node_ref,
        snapshot_kind=snapshot_kind,
        field_path=field_path,
        path=path,
        mime_type=mime_type,
        source_type="object",
    )


def _artifact_from_path_string(
    *,
    value: str,
    execution: Any,
    snapshot_kind: str,
    field_path: str,
) -> ImageArtifact | None:
    path = Path(value)
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        return None

    return ImageArtifact(
        node_id=execution.node_id,
        node_ref=execution.node_ref,
        snapshot_kind=snapshot_kind,
        field_path=field_path,
        path=path,
        mime_type=_mime_type_for_path(path),
        source_type="path",
    )


def _artifact_from_data_url(
    *,
    value: str,
    execution: Any,
    snapshot_kind: str,
    field_path: str,
    image_dir: Path,
    counter: int,
) -> ImageArtifact | None:
    match = _DATA_URL_PATTERN.match(value)
    if match is None:
        return None

    mime_type = match.group(1)
    suffix = "." + mime_type.split("/", 1)[1].split("+", 1)[0]
    filename = f"{execution.node_execution_id}-{snapshot_kind}-{counter}{suffix}"
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / filename
    path.write_bytes(base64.b64decode(match.group(2), validate=True))
    return ImageArtifact(
        node_id=execution.node_id,
        node_ref=execution.node_ref,
        snapshot_kind=snapshot_kind,
        field_path=field_path,
        path=path,
        mime_type=mime_type,
        source_type="data_url",
    )


def _mime_type_for_path(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _render_artifact_image(artifact: ImageArtifact) -> str:
    src = artifact.path.resolve().as_uri() if artifact.path.is_absolute() else escape(str(artifact.path))
    label = f"{artifact.node_id} {artifact.field_path} {artifact.path.name}"
    return (
        "<figure>"
        f"<figcaption>{escape(label)}</figcaption>"
        f'<img src="{escape(src, quote=True)}" alt="{escape(label, quote=True)}">'
        "</figure>"
    )


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


def _default_open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return

    webbrowser.open(path.resolve().as_uri())
