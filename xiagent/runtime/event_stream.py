from __future__ import annotations

import json

from xiagent.runtime.models import TaskEventRecord


def format_sse_event(event: TaskEventRecord) -> str:
    return format_sse_event_payload(
        event_id=event.event_id,
        event_type=event.event_type,
        payload=event.payload,
    )


def format_sse_event_payload(
    *,
    event_id: str,
    event_type: str,
    payload: dict,
) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"
