---
name: xiagent-ui-development
description: Use when creating, modifying, refactoring, or validating XiAgent frontend UI under ui/V1, ui/V2, or future ui version directories, including task workbench, project, asset, workflow, node input/output, visual rules, API wiring, and UI rule documentation updates.
---

# XiAgent UI Development

## Overview

XiAgent UI work is versioned under `ui/<version>/...` and must deliver a real end-user workflow, not a mock demo or developer JSON viewer. The UI consumes stable REST APIs and workflow/node contracts; users choose templates, submit inputs, inspect task state, handle waiting interactions, and manage assets/projects.

## Start Here

1. Identify the target UI version. If the user does not name one, inspect `ui/*` and current git diff; ask only when multiple versions are plausible and local evidence is insufficient.
2. Read `AGENTS.md`, relevant `docs/design/`, `docs/project-architecture/`, and `docs/development/` files before changing behavior.
3. Read the target version rule file if present: `ui/<version>/docs/ui-development-rules.md`.
4. Map every screen field to a real API/service/state source before editing. UI must not directly read SQLite, local asset file paths, backend internals, node classes, or provider adapter details.
5. When a UI rule changes, update documentation in the same turn: reusable XiAgent UI rules go in this skill; version-specific style, layout, and exceptions go in `ui/<version>/docs/ui-development-rules.md`.

## Directory Rules

- Put UI code only under a concrete version directory such as `ui/V1` or `ui/V2`; `ui/` itself is only the container.
- Do not move non-UI backend code into `ui/`.
- Do not copy a UI version into another version without reconciling its project-specific rule file.
- Shared UI code belongs in an explicit `ui/shared/...` only when the user approves cross-version coupling.
- Every maintained UI version should have `ui/<version>/docs/ui-development-rules.md` covering stack, routes, API wiring, visual tokens, layout rules, node/control rendering rules, commands, and known caveats.

## Product Contract

- XiAgent is not a low-code or drag-and-drop workflow editor. Users select developer-maintained workflow YAML/JSON templates; they do not edit DAGs.
- `project_id` is required for task, asset, and project-scoped workflow operations. The built-in `project_id=global` project is the default shared project for active users; tasks remain isolated by `user_id + project_id`.
- Available workflows for a project are `scope=global` plus workflows whose `project_id` matches the selected project.
- Global workflow templates keep `project_id` empty in the workflow contract; do not rewrite them to `project_id=global`.
- Workflow/node/task JSON is transport and persistence data. Do not display raw JSON, schema keys, `input_schema`, `output_snapshot`, `public_url`, or internal refs to end users unless a developer/debug view is explicitly requested.
- Task creation pages must not collect workflow business parameters. They show launch information and create the task; required user input is submitted later through a node that declares `from_user: true`.
- Render node user input schemas as labels, forms, pickers, toggles, image selectors, cards, status badges, and media previews only through the node UI control path. Node input/output should be presented as user-facing cards, not as raw object dumps.

## Node UI Controls

- Node UI must come from a version-local registered control library when behavior is reusable or configurable. Prefer a registry such as `ui/<version>/src/node-ui/...` or an existing equivalent over hardcoded workflow-specific rendering in page code.
- Workflow/node config may reference UI control IDs, variants, modes, sections, actions, and bindings. Resolve those references through the registered UI control library.
- Control inputs and outputs must follow the node descriptor/schema and workflow contract. Do not invent UI-only payload shapes that the runtime cannot validate.
- If a needed node control does not exist, add it to the registry, document it in `ui/<version>/docs/ui-development-rules.md`, and add tests for the rendered input/output state.
- Keep program transport JSON inside API calls and adapters. The visible UI should speak in domain terms such as task, project, workflow, asset, input, output, waiting, failed, succeeded.

## Implementation Rules

- Use the target UI version's existing stack, state style, API client, CSS tokens, and test patterns.
- Keep work-focused operational UIs dense but readable: predictable navigation, restrained cards, clear tables/lists, status badges, and compact controls.
- Avoid landing pages for app work; the first authenticated screen should be the usable workspace.
- Use project selection consistently across task list, task detail, workflow loading, assets, and project pages.
- Preserve loading, empty, error, disabled, success, waiting, and failed states for all API-backed flows.
- Avoid static business data in production paths. Mock data belongs only in tests or explicit story/dev harnesses.
- Do not leave local-only URLs, demo credentials, console noise, debug routes, TODO/FIXME, or hardcoded user/project/task data in production UI code.

## Verification

Run the target version's available commands, usually:

```powershell
npm run test
npm run build
npm run test:e2e
```

Also run backend/API tests when UI behavior depends on backend contracts. Finish with a real browser flow using the running backend and UI: login or register, select/confirm project, exercise the changed page, perform the core action, refresh or navigate as needed, and verify persisted results. Check that no user-facing raw JSON appears.

For acceptance review, use `xiagent-ui-review` after implementation.

## Rule Updates

- Put reusable UI development rules in this skill.
- Put version-specific design language, color, layout, and control registry details in `ui/<version>/docs/ui-development-rules.md`.
- Put backend/API/workflow contract changes in the relevant `docs/design/` or `docs/project-architecture/` document.
- If implementation discovers a new rule, update the right document before final verification.

## Common Mistakes

- Adding a fake frontend-only global project instead of using `/api/projects`.
- Reintroducing a task-creation-page business input form instead of using the start input node and node UI controls.
- Showing raw workflow JSON or schema because it is convenient to render.
- Hiding test workflows that should be selectable for UI testing.
- Loading all workflows without selected project context.
- Treating screenshots as proof without checking API source and persisted state.
- Updating V2 visual language while leaving `ui/V2/docs/ui-development-rules.md` stale.
