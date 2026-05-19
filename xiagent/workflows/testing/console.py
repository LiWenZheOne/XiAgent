from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Callable

from xiagent.core.errors import XiAgentError
from xiagent.core.schemas import validate_json_value

_JSON_DUMP_OPTIONS = {"ensure_ascii": False, "indent": 2, "default": str}


class ConsoleIO:
    def __init__(
        self,
        input_func: Callable[[str], str] | None = None,
        output_func: Callable[[str], None] | None = None,
    ) -> None:
        self._input_func = input_func or input
        self._output_func = output_func or print

    def write(self, message: str = "") -> None:
        self._output_func(message)

    def ask(self, prompt: str) -> str:
        return self._input_func(prompt)

    def ask_json(self, prompt: str) -> dict[str, Any]:
        value = json.loads(self.ask(prompt))
        if not isinstance(value, dict):
            raise ValueError("JSON input must be an object")
        return value

    def show_event(self, index: int, event: Any) -> None:
        self.write(f"[事件 {index}]")
        self.write(_to_pretty_json(_to_jsonable(event)))

    def show_node_execution(self, execution: Any) -> None:
        node_id = _read_attr(execution, "node_id")
        status = _read_attr(execution, "status")
        if node_id is not None and status is not None:
            self.write(f"[节点] {node_id} ({status})")
        else:
            self.write("[节点]")
        self.write(_to_pretty_json(_to_jsonable(execution)))

    def prompt_resume_output(self, execution: Any, output_schema: dict[str, Any]) -> dict[str, Any]:
        self.write("[等待节点]")
        self.show_node_execution(execution)
        metadata = _read_attr(execution, "metadata") or {}
        requested_inputs = metadata.get("requested_inputs") if isinstance(metadata, dict) else None
        if requested_inputs is not None:
            self.write("[请求输入]")
            self.write(_to_pretty_json(requested_inputs))
        self.write("[输出 Schema]")
        self.write(_to_pretty_json(output_schema))
        return self.ask_json("resume output JSON: ")


def parse_input_data(
    inline_json: str | None,
    input_file: Path | None,
    interactive: bool,
    input_schema: dict[str, Any],
    console: ConsoleIO,
) -> dict[str, Any]:
    _ = interactive
    if inline_json is not None:
        value = json.loads(inline_json)
    elif input_file is not None:
        value = json.loads(input_file.read_text(encoding="utf-8-sig"))
    else:
        value = _prompt_schema(input_schema, console)

    if not isinstance(value, dict):
        raise ValueError("Workflow input must be a JSON object")
    validate_json_value(input_schema, value)
    return value


def print_error(exc: Exception, debug: bool, console: ConsoleIO) -> None:
    if isinstance(exc, XiAgentError):
        console.write(f"[错误] {exc.code}")
        console.write(exc.message)
        if exc.details:
            console.write(_to_pretty_json(exc.details))
    else:
        console.write(f"[错误] {type(exc).__name__}: {exc}")

    if debug:
        console.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


def _prompt_schema(input_schema: dict[str, Any], console: ConsoleIO) -> dict[str, Any]:
    required = input_schema.get("required")
    properties = input_schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return console.ask_json("workflow input JSON: ")

    value: dict[str, Any] = {}
    for field_name in required:
        if not isinstance(field_name, str):
            return console.ask_json("workflow input JSON: ")
        field_schema = properties.get(field_name)
        if not isinstance(field_schema, dict):
            return console.ask_json("workflow input JSON: ")
        value[field_name] = _prompt_field(field_name, field_schema, console)
    return value


def _prompt_field(field_name: str, field_schema: dict[str, Any], console: ConsoleIO) -> Any:
    field_type = field_schema.get("type")
    if field_type == "string":
        return console.ask(f"{field_name}: ")
    if field_type == "integer":
        return int(console.ask(f"{field_name}: "))
    if field_type == "number":
        return float(console.ask(f"{field_name}: "))
    if field_type == "boolean":
        return _parse_boolean(console.ask(f"{field_name}: "))
    if field_type in {"object", "array"}:
        value = json.loads(console.ask(f"{field_name} (JSON): "))
        if field_type == "object" and not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a JSON object")
        if field_type == "array" and not isinstance(value, list):
            raise ValueError(f"{field_name} must be a JSON array")
        return value
    return json.loads(console.ask(f"{field_name} (JSON): "))


def _parse_boolean(raw_value: str) -> bool:
    value = raw_value.strip().lower()
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {raw_value}")


def _to_pretty_json(value: Any) -> str:
    return json.dumps(value, **_JSON_DUMP_OPTIONS)


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dict__"):
        return vars(value)
    if hasattr(value, "__dataclass_fields__"):
        return {field: getattr(value, field) for field in value.__dataclass_fields__}
    return value


def _read_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
