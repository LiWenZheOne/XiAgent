# Issues — Asset Storyboard Orchestration

## F3: QA Execution Results (2026-05-25)

### PASS/FAIL Verdict

| Test Group | Count | Pass | Fail |
|---|---|---|---|
| Orchestration tests (`test_asset_storyboard_orchestration.py`) | 16 | 16 | 0 |
| Workflow CLI tests (`test_workflow_testing_cli.py`) | 8 | 8 | 0 |
| All other tests (non-orchestration) | 248 | 247 | 1 |
| **TOTAL** | **272** | **271** | **1** |

**Overall pass rate: 99.63% (271/272)**

### Single Failure: `test_build_node_registry_registers_builtin_nodes` (test_node_registry.py:44)

**Cause:** The test hardcodes a static set of expected built-in node refs. The orchestration feature added 4 new nodes and bumped 2 version numbers, but the test was not updated:

- `ai.assign_assets_to_segments.v1` (new)
- `tool.assemble_storyboard_context.v1` (new)
- `tool.extract_panel_image_urls.v1` (new)
- `tool.storyboard_prompt_assembler.v1 → v2` (version bump)
- `ai.runninghub_image_to_image.v1 → v2` (version bump)

**Severity:** Low. Not a functionality regression — the test expectation set needs updating to reflect the new node registry. All 16 orchestration-specific tests pass cleanly, and no existing workflow behavior is broken.

### Edge Cases Tested

- Empty input, all-new characters, missing assets: covered by `test_prop_pipeline_execution` and `test_scene_pipeline_execution`
- No regression in existing workflow tests (storyboard, runninghub, catalog, runtime, validator)


## F4 Scope Fidelity Check — 2026-05-25 18:17

### VERDICT: REJECT

16 files outside plan scope found across commits 6863c44 + a3a8108.
Critical violations:
- asset_catalog.workflow.yaml + storyboard_generation.workflow.yaml modified despite prohibition
- 4 existing node files modified without .v2 versioning
- 2 unplanned new nodes (parallel_deepseek_structured_json, create_text_asset)
- 4 existing test files modified

Full report in F4 output.
