# Learnings

## 2026-05-27: Renamed GeminiModelConfig → OpenAICompatibleModelConfig

- Renamed class GeminiModelConfig → OpenAICompatibleModelConfig in xiagent/models/types.py
- Updated ase_url default from "https://generativelanguage.googleapis.com/v1beta/openai/" → "https://api.vectorengine.cn"
- Updated container field in ModelConfig: gemini: GeminiModelConfig → openai_compatible: OpenAICompatibleModelConfig
- All 3 original fields retained unchanged: pi_key, ase_url, model
- model default kept as "gemini-3-flash-preview"
- Verification: no GeminiModelConfig refs remain, import/instantiation works correctly

## 2026-05-27: Renamed config loading in xiagent/models/config.py

- **Import (line 10):** `GeminiModelConfig` → `OpenAICompatibleModelConfig`
- **Section (line 68):** `gemini = _section(raw, "gemini")` → `openai_compatible = _section(raw, "openai_compatible")`
- **Local vars (lines 208-210):** `gemini_api_key/gemini_base_url/gemini_model` → `openai_compatible_api_key/openai_compatible_base_url/openai_compatible_model`
- **Env vars (lines 212-214):** `GEMINI_API_KEY/GEMINI_BASE_URL/GEMINI_MODEL` → `OPENAI_COMPATIBLE_API_KEY/OPENAI_COMPATIBLE_BASE_URL/OPENAI_COMPATIBLE_MODEL`
- **ModelConfig kwargs (lines 254-258):** `gemini=GeminiModelConfig(...)` → `openai_compatible=OpenAICompatibleModelConfig(...)`
- **Preserved:** default model string `"gemini-3-flash-preview"` and RunningHub model name (not config identifiers)
- **LSP diagnostics:** clean, no errors

## 2026-05-27: Renamed Settings fields in config.py

- Renamed 3 Settings fields in `xiagent/infrastructure/config.py`:
  - `gemini_api_key` → `openai_compatible_api_key`
  - `gemini_base_url` → `openai_compatible_base_url`
  - `gemini_model` → `openai_compatible_model`
- Updated 3 mappings in `load_settings()`:
  - `model_config.gemini.*` → `model_config.openai_compatible.*`
- Verification: import + hasattr assertion passed
- **Downstream breakages (not yet fixed):**
  - `xiagent/nodes/__init__.py` lines 86-88: references old `settings.gemini_api_key/base_url/model`
  - `tests/conftest.py` lines 31-33: keyword args with old `gemini_*` names

## 2026-05-27: Config file updates for openai_compatible section

- **`xiagent/models/local_config.toml`** — appended new `[openai_compatible]` section at end of file:
  - `api_key = ""`, `base_url = "https://api.vectorengine.cn"`, `model = "gemini-3-flash-preview"`
- **`xiagent/models/local_config.example.toml`** — renamed `[gemini]` → `[openai_compatible]` (header only). Base URL was already `https://api.vectorengine.cn`.
- **`.env.example`** — appended 3 new env vars after `RUNNINGHUB_*` block:
  - `OPENAI_COMPATIBLE_API_KEY=`, `OPENAI_COMPATIBLE_BASE_URL=https://api.vectorengine.cn`, `OPENAI_COMPATIBLE_MODEL=gemini-3-flash-preview`
- Verification: Python tomllib parsed all 3 files successfully and validated the new section content.

## 2026-05-27: Renamed provider file gemini.py → openai_compatible.py

- Renamed `xiagent/models/providers/gemini.py` → `xiagent/models/providers/openai_compatible.py`
- Renamed `GeminiChatProvider` → `OpenAICompatibleChatProvider`
- Renamed `GeminiModelConfig` → `OpenAICompatibleModelConfig` (import + type annotation)
- Updated all error codes/msgs/metadata from `gemini_*` → `openai_compatible_*`
- Chat logic preserved unchanged
- Old file `gemini.py` deleted
- Verification: `from xiagent.models.providers.openai_compatible import OpenAICompatibleChatProvider` — OK

## 2026-05-27: Renamed tests/conftest.py fixture fields

- **Lines 31-33 in `test_settings()` fixture:**
  - `gemini_api_key=None` → `openai_compatible_api_key=None`
  - `gemini_base_url=...` → `openai_compatible_base_url="https://api.vectorengine.cn"`
  - `gemini_model=...` → `openai_compatible_model="gemini-3-flash-preview"`
- No other fields in the fixture were modified.
- `Settings` class already had the renamed fields, so the fixture now matches the model.

## 2026-05-27: Updated xiagent/nodes/__init__.py — 5 Gemini → openai_compatible references
- **Line 6:** `from xiagent.models.providers.gemini import GeminiChatProvider` → `from xiagent.models.providers.openai_compatible import OpenAICompatibleChatProvider`
- **Line 14:** `GeminiModelConfig` → `OpenAICompatibleModelConfig` (in types import block)
- **Lines 85-89:** `gemini_config = GeminiModelConfig(api_key=settings.gemini_api_key, base_url=settings.gemini_base_url, model=settings.gemini_model)` → `openai_compatible_config = OpenAICompatibleModelConfig(api_key=settings.openai_compatible_api_key, base_url=settings.openai_compatible_base_url, model=settings.openai_compatible_model)`
- **Lines 107-110:** `router.register_provider("gemini", GeminiChatProvider(config=gemini_config))` → `router.register_provider("openai_compatible", OpenAICompatibleChatProvider(config=openai_compatible_config))`
- **Lines 182-188:** `GeminiVisionNode(..., provider="gemini", model=gemini_config.model)` → `GeminiVisionNode(..., provider="openai_compatible", model=openai_compatible_config.model)`
- Verification: Import check passed, LSP clean (only pre-existing str|None warning on unrelated line)

## 2026-05-27: Updated 5 test files — Gemini → openai_compatible references

### tests/test_gemini_provider.py
- **Import (line 10-11):** `from xiagent.models.providers.gemini import GeminiChatProvider` + `GeminiModelConfig` → `from xiagent.models.providers.openai_compatible import OpenAICompatibleChatProvider` + `OpenAICompatibleModelConfig`
- **Provider string (line 17):** `"gemini"` → `"openai_compatible"`
- **All class refs:** 4× `GeminiModelConfig(...)` → `OpenAICompatibleModelConfig(...)`, 4× `GeminiChatProvider(...)` → `OpenAICompatibleChatProvider(...)`
- **Error codes:** `"gemini_api_key_missing"` → `"openai_compatible_api_key_missing"`, `"gemini_request_failed"` → `"openai_compatible_request_failed"`
- **Preserved:** `gemini-3-flash-preview` (model name), test function names

### tests/test_gemini_vision_node.py
- **Provider string (line 16):** `"gemini"` → `"openai_compatible"`
- **Metadata (lines 29, 320):** `{"provider": "gemini"}` → `{"provider": "openai_compatible"}`
- **Assertion (line 95):** `call_arg.provider == "gemini"` → `"openai_compatible"`
- **Error codes (lines 139, 156, 171):** `"gemini_request_failed"` → `"openai_compatible_request_failed"` (these originate from the renamed provider)
- **Preserved:** `GeminiVisionNode` (class), `gemini_vision_*` error codes (node-specific), `gemini-3-flash-preview` (model name), test function names

### tests/test_workflow_storyboard_from_sketch.py
- **Provider check (line 83):** `request.provider == "gemini"` → `"openai_compatible"`
- **Method name (lines 84, 181):** `_gemini_response` → `_openai_compatible_response`
- **Comment (line 179):** `# ---- gemini ----` → `# ---- openai_compatible ----`
- **Node registration (line 274):** `provider="gemini"` → `provider="openai_compatible"`
- **Count assertion (line 410):** `providers.count("gemini")` → `providers.count("openai_compatible")`
- **Comment (line 407):** `gemini 1 次` → `openai_compatible 1 次`
- **Preserved:** `GeminiVisionNode` (class), `"ai.gemini_vision.v1"` (node ref), `gemini_vision_analysis` (node ID)

### tests/test_model_config.py / tests/test_node_registry.py
- No changes needed — all `gemini` strings are model names ("nano-banana2-gemini31flash/...") or node refs ("ai.gemini_vision.v1")

### Verification
- `grep GeminiModelConfig|GeminiChatProvider tests/` → **0 matches** ✅
- `grep gemini tests/*.py` → Only `GeminiVisionNode`, `gemini_vision_*` error codes, model names (`gemini-3-flash-preview`, `nano-banana2-gemini31flash`), and node refs remain ✅
- LSP diagnostics: clean on all modified files ✅

## 2026-05-27: F2 Code Quality Review — APPROVED

All 6 checks passed:

1. **Ruff pre-existing issues**: 58 E501/F401/I001 lines across project (pre-existing, not from this change)
2. **New ruff issues in xiagent/**: Only 4 I001 (import ordering) cosmetic issues, 0 new substantive errors
3. **GeminiModelConfig/GeminiChatProvider grep**: 0 matches — old classes fully purged
4. **providers.gemini imports grep**: 0 matches — no old module imports remain
5. **openai_compatible.py AI slop**: Clean — no TODOs, FIXME, HACK, commented-out code, or pass statements. Error messages clear and actionable.
6. **nodes/__init__.py**: GeminiVisionNode import is used (line 183), no dead gemini imports
