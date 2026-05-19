from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.testing.builder import WorkflowTestBuilder
from xiagent.workflows.testing.console import ConsoleIO, parse_input_data, print_error
from xiagent.workflows.testing.runner import WorkflowTestRunner
from xiagent.workflows.validator import validate_workflow_contract


class WorkflowTestingArgumentParser(argparse.ArgumentParser):
    def parse_args(
        self,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        parsed_args = super().parse_args(args, namespace)
        has_workflow_path = parsed_args.workflow_path is not None
        has_workflow_id = parsed_args.workflow_id is not None
        if has_workflow_path == has_workflow_id:
            self.error("exactly one of workflow_path or --workflow-id is required")
        return parsed_args


def build_parser() -> WorkflowTestingArgumentParser:
    parser = WorkflowTestingArgumentParser(
        description="Run a XiAgent workflow contract in a local testing session.",
    )
    parser.add_argument("workflow_path", nargs="?", type=Path)
    parser.add_argument("--workflow-id")
    parser.add_argument("--input")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(".data/workflow-test.sqlite3"),
    )
    parser.add_argument(
        "--asset-storage-dir",
        type=Path,
        default=Path(".data/workflow-test-assets"),
    )
    parser.add_argument("--workflow-dir", type=Path, default=Path("workflows"))
    parser.add_argument("--project-id")
    parser.add_argument("--project-name", default="Workflow Test Project")
    parser.add_argument("--username", default="workflow-test-admin")
    parser.add_argument("--password", default="secret-123")
    parser.add_argument("--show-json", action="store_true")
    parser.add_argument("--open-images", action="store_true")
    parser.add_argument("--preview", choices=["html"])
    parser.add_argument("--open-preview", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


async def run_from_args(args: argparse.Namespace) -> int:
    console = ConsoleIO()
    try:
        builder = (
            WorkflowTestBuilder()
            .with_database_path(args.database_path)
            .with_asset_storage_dir(args.asset_storage_dir)
            .with_workflow_dir(args.workflow_dir)
            .with_default_admin(username=args.username, password=args.password)
            .with_default_project(name=args.project_name)
        )
        if args.project_id is not None:
            builder.with_project_id(args.project_id)

        session = await builder.build()
        if args.workflow_path is not None:
            contract = load_workflow_file(args.workflow_path)
            validate_workflow_contract(contract, session.node_registry)
        else:
            contract = session.workflows.get(args.workflow_id)

        input_data = parse_input_data(
            inline_json=args.input,
            input_file=args.input_file,
            interactive=args.interactive,
            input_schema=contract["workflow"]["input_schema"],
            console=console,
        )
        runner = WorkflowTestRunner(session=session, console=console)
        result = await runner.run_contract(
            contract,
            input_data=input_data,
            open_images=args.open_images,
            preview=_preview_argument(args.preview),
            open_preview=args.open_preview,
        )

        if args.show_json:
            _print_json_result(result, console)

        return 0 if result.task.status == "succeeded" else 1
    except Exception as exc:
        print_error(exc, debug=args.debug, console=console)
        return 1


def main() -> None:
    raise SystemExit(asyncio.run(run_from_args(build_parser().parse_args())))


def _preview_argument(preview: str | None) -> bool | None:
    if preview == "html":
        return True
    return None


def _print_json_result(result: Any, console: ConsoleIO) -> None:
    payload = {
        "task": asdict(result.task),
        "events": [asdict(event) for event in result.events],
        "node_executions": [asdict(execution) for execution in result.node_executions],
        "artifacts": [asdict(artifact) for artifact in result.artifacts],
    }
    console.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
