from __future__ import annotations

import json

from xiagent.runtime.models import TaskEventRecord


def format_sse_event(event: TaskEventRecord) -> str:
    data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"id: {event.event_id}\nevent: {event.event_type}\ndata: {data}\n\n"
