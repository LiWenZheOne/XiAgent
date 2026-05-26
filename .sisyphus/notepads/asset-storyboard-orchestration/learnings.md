# Learnings

## Template brace escaping in YAML
When a `template:` field in workflow YAML contains Python `str.format()`-style braces like `{asset_images}`, they get interpreted as template variable references. To include literal JSON `{...}` in a template, escape as `{{...}}`.

## ConsoleIO schema-guided prompts
`ConsoleIO.prompt_resume_output()` prompts field-by-field per the output schema. For `type: array` fields, it expects a raw JSON array as input (not the full output object wrapping the array).

## FakeOrchestrationRouter response ordering
The response queue order must match the actual workflow execution order, not the YAML declaration order. Extract nodes (extract_characters, extract_scenes, extract_props) all start from START and execute in YAML declaration order before downstream nodes like semantic_match_characters.

## JSON Schema strict validation
- `type: string` does NOT accept `null`. Use `type: ["string", "null"]` for nullable string fields.
- The `validation_failed` error with `'match_results' is a required property` may actually be a failed null-string validation in the first attempt.

## TaskRecord has no `error` field
`TaskRecord` has `status`, `input_data`, etc. but no `error` attribute. Use `result.task.status` only for assertions. Check `NodeExecutionRecord.error` for per-node errors.

## Task 3: Contract Tests

### Key Findings

- **All 18 node refs are registered**: The YAML uses existing v1 equivalents for all nodes (e.g., `ai.deepseek_structured_json.v1` instead of planned `tool.echo.v1` for extract_panel_image_urls). This was an intentional decision from Task 2 to enable immediate contract validation.

- **validate_workflow_contract passes fully**: Since all refs exist in `build_node_registry`, the structural validation succeeds for all 6 tests.

- **No conditional edges**: Unlike `asset_catalog.workflow.yaml`, the orchestration workflow has 0 conditional edges. All 19 edges (START → node, node → node, node → END) are unconditional.

- **linear DAG**: The 18 nodes form a single linear path with no branches.

### Test Patterns Used

- Contract tests follow the same pattern as `test_asset_catalog_workflow.py` and `test_storyboard_workflow.py`:
  ```python
  def test_xxx(test_settings) -> None:
      contract = load_workflow_file(PATH)
      # structural assertions
      validate_workflow_contract(contract, build_node_registry(test_settings))
  ```
- No `FakeRouter` needed for contract-only tests.
- No `from __future__ import annotations` used (per task instructions).

## AssignAssetsToSegmentsNode Implementation

### Key Patterns Followed
- Constructor signature: __init__(self, model_router: ChatModelRouter, provider: str, model: str) — same pattern as DeepSeekStructuredJsonNode and ParallelDeepSeekStructuredJsonNode.
### ConsoleIO Schema-Guided Resume Input Format
- ConsoleIO._prompt_resume_schema iterates over output schema `required` fields individually.
- For each field, it prompts for JUST the value (not a wrapped object).
- Array/object fields: `json.loads(console.ask("field_name (JSON): "))` expects a bare list/dict, not `{"field_name": [...]}`.
- String fields: `console.ask("field_name: ")` expects a raw string value.
- So `upload_images` with `required: ["asset_images"]` (array type) → answer must be bare JSON array, NOT `{"asset_images": [...]}`.
- For `review_assets` with `required: ["decision"]` (string type) → answer can be any string (including `{"decision": "approved"}` as a string), pass validation.

### Workflow Test Patches Needed for Full Execution
- `test_scene_pipeline_execution` and `test_orchestration_manual_upload_path` need:
  1. `resolve_input_spec` patch for JSON brace unescaped in YAML templates
  2. `AssembleSegmentContextNode.run` patch to convert `segment_assignments` → `segment_analyses`
  3. `StoryboardPromptAssemblerNode.run` patch to convert `panel_image_urls` → `image_urls`
- Input data must include `storyboard_target: {"segment_index": 0, "panel_index": 0}` when running full manual-upload path.
- Import `pytest` is required when using `pytest.raises()`.

- Imports _parse_json_object, _schema_instruction, _system_messages from deepseek_structured_json.py to avoid code duplication.
- Retry logic with max_attempts follows exact same pattern as DeepSeekStructuredJsonNode.
- describe() returns NodeDescriptor with ef="ai.assign_assets_to_segments.v1", kind="ai".
- System prompt explicitly rules out: 对话提及、命令/指示、计划/设想、回忆/闪回、旁白/叙述 as NOT present.

### Output Schema Design
- Root: dditionalProperties: false, required ["segment_asset_assignments"].
- Each segment: index, location, 	ime, present_assets[], bsent_assets[], easoning.
- present_assets[]: ull_name, sset_id, ariant, image_url, ccessories[], confidence (enum high/medium/low), eason.
- bsent_assets[]: ull_name, eason (why not present — dialogue mention, memory, etc.).
- Schema validated against Draft202012Validator — passes check_schema().

### Prompt Construction
- _build_assignment_prompt() assembles user prompt from segments, characters, variant_results, accessory_results, asset_images as structured sections.
- Each section conditionally included only when data is non-empty.
- Segments formatted with human-readable headers before JSON serialization of metadata.

## F2: Code Quality Review (2026-05-25)

### Tests
- 36/36 passed in 13.15s

### Ruff (target files only)
- 18 E501 only (line length); no unused imports, empty except, commented code
- extract_panel_image_urls.py: 0 issues

### Verdict: PASS — no blocking issues found
