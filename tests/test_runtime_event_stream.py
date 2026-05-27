from __future__ import annotations

from xiagent.runtime.event_stream import format_sse_event
from xiagent.runtime.models import TaskEventRecord


def test_format_sse_event_uses_event_id_type_and_json_payload() -> None:
    event = TaskEventRecord(
        event_id="event_123",
        task_id="task_123",
        event_type="node_started",
        payload={"node_id": "plan", "count": 1},
        created_at="2026-05-27T00:00:00+00:00",
    )

    assert format_sse_event(event) == (
        "id: event_123\n"
        "event: node_started\n"
        'data: {"count":1,"node_id":"plan"}\n\n'
    )
