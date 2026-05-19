from __future__ import annotations

import json
from pathlib import Path

from xiagent.workflows.testing.console import ConsoleIO, parse_input_data


def test_parse_input_data_prefers_inline_json(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text('{"topic":"from-file"}', encoding="utf-8")

    parsed = parse_input_data(
        inline_json='{"topic":"from-inline"}',
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-inline"}


def test_parse_input_data_reads_json_file(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"topic": "from-file"}), encoding="utf-8")

    parsed = parse_input_data(
        inline_json=None,
        input_file=input_file,
        interactive=False,
        input_schema={"type": "object"},
        console=ConsoleIO(),
    )

    assert parsed == {"topic": "from-file"}


def test_parse_input_data_prompts_required_schema_fields() -> None:
    prompts: list[str] = []
    answers = iter(["hello", "7", "yes", '{"nested": true}'])
    console = ConsoleIO(input_func=lambda prompt: prompts.append(prompt) or next(answers))

    parsed = parse_input_data(
        inline_json=None,
        input_file=None,
        interactive=False,
        input_schema={
            "type": "object",
            "required": ["topic", "count", "enabled", "options"],
            "properties": {
                "topic": {"type": "string"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "options": {"type": "object"},
            },
        },
        console=console,
    )

    assert parsed == {
        "topic": "hello",
        "count": 7,
        "enabled": True,
        "options": {"nested": True},
    }
    assert prompts == ["topic: ", "count: ", "enabled: ", "options (JSON): "]
