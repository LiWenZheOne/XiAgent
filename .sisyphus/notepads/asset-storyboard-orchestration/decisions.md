# Asset Image Result Schema Design Decisions

## Decision: Schema Location and Structure

- **Date**: 2026-05-25
- **Task**: Task 1 — Wave 1: 统一资产结果 schema 定义

### Context

Asset module and image generation nodes (RunningHub) need a shared schema for image result data. Previously, each module defined its own shape. This unified schema ensures consistency across the system.

### Decision

1. **Place schemas in `xiagent/core/schemas.py`** — as module-level constants, following JSON Schema dict format used by `validate_json_value`.

2. **Two schemas**: `ASSET_IMAGE_RESULT_SCHEMA` (single item) + `ASSET_IMAGE_RESULT_LIST_SCHEMA` (array wrapper), so callers can validate individual items or collections.

3. **Required fields** (`full_name`, `image_url`, `source`): All three are mandatory for an asset image result to be usable. `full_name` has `minLength: 1` to prevent empty strings (a common failure mode). `source` uses `enum` to restrict values to `ai_generated` and `manual_upload`.

4. **Optional fields** (`variant`, `asset_id`, `runninghub_task_id`): useful metadata but not always present at different stages of the pipeline.

5. **`additionalProperties: False`**: Prevents accidental typos and ensures schema consumers don't add undocumented fields.

### Rationale

- Following existing patterns in `deepseek_structured_json.py` where schemas use lowercase JSON Schema keyword casing and `additionalProperties: False`.
- The `validate_json_value` function (using `Draft202012Validator`) already exists and validates both schema correctness and data compliance.
- Keeping schemas in `core` avoids circular imports — they can be referenced by nodes, runtime, and tests alike.

### Alternatives Considered

- Defining schemas only in asset or node modules — rejected because the cross-module nature requires a shared location.
- Using Pydantic models — rejected; codebase convention prefers plain dict JSON Schema to stay framework-agnostic.

## Decision: Asset Storyboard Generation Workflow YAML Structure

- **Date**: 2026-05-25
- **Task**: Task 2 — Wave 1: 创建 asset_storyboard_generation.workflow.yaml 草案

### Context

The orchestrated workflow combines asset extraction (from asset_catalog) with storyboard generation (from storyboard_generation) into a single 18-node pipeline. Only the manual upload path is implemented.

### Decision

1. **Node ref mapping**: Planned refs (`ai.assign_assets_to_segments.v1`, `tool.assemble_storyboard_context.v1`, `tool.extract_panel_image_urls.v1`, `tool.storyboard_prompt_assembler.v2`, `ai.runninghub_image_to_image.v2`) are not yet registered. Used existing v1 equivalents for contract validation to pass: `ai.deepseek_structured_json.v1` for AI-callable nodes, `tool.assemble_segment_context.v1` for context assembly, `tool.storyboard_prompt_assembler.v1` for prompt assembly, `ai.runninghub_image_to_image.v1` for image generation. When planned nodes are implemented, the refs should be updated to their intended versions.

2. **Asset extraction nodes (1-7)**: Copied verbatim from asset_catalog.workflow.yaml with no prompt changes — the `background` and `script` inputs resolve identically via `$workflow.input.*`.

3. **upload_images output schema**: Uses `ASSET_IMAGE_RESULT_LIST_SCHEMA` pattern with `asset_images` array (items with `full_name`, `image_url`, `source: "manual_upload"`), different from asset_catalog's flat `image_urls: string[]` output. This enables downstream nodes (assign_assets_to_segments, extract_panel_image_urls) to trace back which image belongs to which character.

4. **storyboard_target input**: Optional object with `segment_index` (default: 0) and `panel_index` (default: 0). Used by `extract_panel_image_urls` to select which panel to generate. Enables iterative generation of one panel at a time.

5. **No conditional edges**: Unlike asset_catalog which branches on `generate_assets`, this workflow has a single linear path (manual upload only). Conditional branching for auto-generate will be added in a future task.

6. **describe_panels system prompt**: Copied from storyboard_generation.workflow.yaml verbatim (same professional storyboard designer instructions). Input context changed from `assemble_context` to `assemble_storyboard_context` which includes asset assignments.

### Rationale

- Keeping asset extraction nodes identical ensures behavior consistency between standalone asset_catalog and orchestrated workflows.
- Using v1 registered refs enables immediate contract validation without waiting for new node implementations.
- The `asset_images` structured output from upload_images is critical for the manual upload path to work — downstream nodes need to know which image URL corresponds to which character.
- 18 nodes in a single linear chain keeps the draft simple and testable. Future iterations can add parallel branches or loops.
