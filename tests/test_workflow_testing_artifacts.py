from __future__ import annotations

import base64
from pathlib import Path

from xiagent.runtime.models import NodeExecutionRecord, TaskEventRecord, TaskRecord
from xiagent.workflows.testing.artifacts import (
    ImageArtifact,
    collect_image_artifacts,
    generate_html_preview,
    open_artifact_paths,
)


def _execution(output_snapshot: dict) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_execution_id="node_execution_1",
        task_id="task_1",
        node_id="render",
        node_ref="tool.render.v1",
        attempt=1,
        input_snapshot={},
        output_snapshot=output_snapshot,
        status="succeeded",
        error=None,
        metadata={},
        started_at="2026-05-20T00:00:00+00:00",
        finished_at="2026-05-20T00:00:01+00:00",
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:01+00:00",
    )


def _task() -> TaskRecord:
    return TaskRecord(
        task_id="task_1",
        workflow_template_id="workflow_template_1",
        workflow_id="image-demo",
        workflow_version="1.0.0",
        user_id="user_1",
        project_id="project_1",
        input_data={},
        status="succeeded",
        current_view={"status": "succeeded"},
        created_at="2026-05-20T00:00:00+00:00",
        started_at="2026-05-20T00:00:00+00:00",
        finished_at="2026-05-20T00:00:01+00:00",
        updated_at="2026-05-20T00:00:01+00:00",
    )


def test_collect_image_artifacts_detects_path_object_and_data_url(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    data_url = "data:image/png;base64," + base64.b64encode(b"data-url-png").decode("ascii")
    output_dir = tmp_path / "run"
    executions = [
        _execution(
            {
                "direct": str(image_path),
                "object": {
                    "type": "image",
                    "path": str(image_path),
                    "mime_type": "image/png",
                },
                "inline": data_url,
            }
        )
    ]

    artifacts = collect_image_artifacts(executions, output_dir=output_dir)

    assert [(item.field_path, item.mime_type) for item in artifacts] == [
        ("output.direct", "image/png"),
        ("output.object", "image/png"),
        ("output.inline", "image/png"),
    ]
    assert artifacts[0].path == image_path
    assert artifacts[1].path == image_path
    assert artifacts[2].path.read_bytes() == b"data-url-png"
    assert artifacts[2].path.parent == output_dir / "images"


def test_collect_image_artifacts_skips_invalid_data_url(tmp_path: Path) -> None:
    artifacts = collect_image_artifacts(
        [_execution({"bad": "data:image/png;base64,not-valid@@"})],
        output_dir=tmp_path / "run",
    )

    assert artifacts == []


def test_collect_image_artifacts_skips_missing_paths_and_urls(tmp_path: Path) -> None:
    artifacts = collect_image_artifacts(
        [
            _execution(
                {
                    "missing": str(tmp_path / "missing.png"),
                    "url": "https://example.com/a.png",
                }
            )
        ],
        output_dir=tmp_path / "run",
    )

    assert artifacts == []


def test_generate_html_preview_contains_node_json_and_image(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    execution = _execution({"image": str(image_path), "text": "ok"})
    artifact = ImageArtifact(
        node_id="render",
        node_ref="tool.render.v1",
        snapshot_kind="output",
        field_path="output.image",
        path=image_path,
        mime_type="image/png",
        source_type="path",
    )
    preview_path = tmp_path / "preview.html"

    event = TaskEventRecord(
        event_id="event_1",
        task_id="task_1",
        event_type="task_succeeded",
        payload={},
        created_at="2026-05-20T00:00:01+00:00",
    )

    generated = generate_html_preview(
        _task(),
        [execution],
        [event],
        [artifact],
        preview_path,
    )

    html = generated.read_text(encoding="utf-8")
    assert generated == preview_path
    assert "image-demo" in html
    assert "render" in html
    assert "task_succeeded" in html
    assert "sample.png" in html
    assert "<img" in html


def test_generate_html_preview_uses_absolute_file_uri_once(tmp_path: Path) -> None:
    image_path = tmp_path / "sample & one.png"
    image_path.write_bytes(b"png")
    artifact = ImageArtifact(
        node_id="render",
        node_ref="tool.render.v1",
        snapshot_kind="output",
        field_path="output.image",
        path=image_path,
        mime_type="image/png",
        source_type="path",
    )
    preview_path = tmp_path / "preview.html"

    generated = generate_html_preview(_task(), [], [], [artifact], preview_path)

    html = generated.read_text(encoding="utf-8")
    assert "file:///" in html
    assert "sample%20%26%20one.png" in html
    assert "&amp;amp;" not in html


def test_open_artifact_paths_uses_injected_opener(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    opened: list[Path] = []

    open_artifact_paths([image_path], opener=opened.append)

    assert opened == [image_path]
