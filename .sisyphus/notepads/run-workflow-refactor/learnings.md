## Task 4: V3 Node Updates

### Changes made
- `_input_schema`: removed `maxItems: 3` from `image_urls`, added `node_mapping` object with `images`, `text`, `select` sub-properties
- `run()`: changed `image_urls` to `list()` copy, merged `line_art_url` via `insert(0, ...)` instead of separate `all_image_urls` list
- `run()`: `node_mapping` now read from `inputs.get("node_mapping")` with fallback default including `select` sub-mapping
- Default images: `["81", "141", "139", "140", "176", "182"]`
- Default select: `{"nodeIds": ["190", "191"], "fieldName": "select"}`

### Test results
- 12/12 `test_runninghub_nodes.py` passed
- 7/7 `test_runninghub_workflows.py` V3 + regression tests passed
- LSP diagnostics: clean
