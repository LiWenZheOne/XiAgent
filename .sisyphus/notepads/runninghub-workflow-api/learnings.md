# Learnings - RunningHub Workflow API Integration

## Test 5: Integration + Regression Tests

### Key Patterns

1. **V3 provider integration test** uses `FakeWorkflowHttpClient` with sequential responses where first call returns `RUNNING` status and second returns `SUCCESS` with results — this mirrors the real submit→poll→result flow.

2. **FakeRouter pattern**: When testing nodes, create a `FakeRunningHubRouter` that returns pre-configured `ChatResponse` objects. This isolates node logic from provider implementation. But for testing the full provider chain, use a real `ChatModelRouter` with a real `RunningHubWorkflowProvider` and a mocked `_UrllibJsonClient`.

3. **conftest.py must stay in sync** with `Settings` dataclass. When new fields are added (like `runninghub_workflow_*`), the `test_settings` fixture must be updated or tests using it will fail at setup.

4. **Node registry tests** explicitly list expected refs in `test_build_node_registry_registers_builtin_nodes`. When adding a new node ref, this set must be updated.

5. **Workflow test `_registry_for_test`** functions need to be updated when workflows reference new node refs. The `test_workflow_storyboard_from_sketch.py` has its own `_registry_for_test` that needed V3 node registration and `FakeRouter` handling for `runninghub_workflow` provider.

### Gotchas

- The `storyboard_from_sketch.workflow.yaml` switched from `ai.runninghub_image_to_image.v1` (provider `runninghub_image`) to `ai.runninghub_image_to_image.v3` (provider `runninghub_workflow`). Tests that assert on provider counts needed updating from `providers.count("runninghub_image")` to `providers.count("runninghub_workflow")`.

### Files Modified
- `tests/conftest.py` — added 4 new `runninghub_workflow_*` fields
- `tests/test_node_registry.py` — added `ai.runninghub_image_to_image.v3` to expected refs
- `tests/test_runninghub_workflow.py` — added `test_v3_integration_full_submit_poll_flow`
- `tests/test_runninghub_workflows.py` — added `test_v1_node_still_works`, `test_existing_workflows_still_load`, `test_storyboard_from_sketch_uses_v3`
- `tests/test_workflow_storyboard_from_sketch.py` — added V3 node registration + `runninghub_workflow` provider handling in `FakeRouter`

### Test Results
- Final: **299 passed**, 0 failed
