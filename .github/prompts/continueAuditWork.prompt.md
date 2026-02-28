```prompt
---
name: continueAuditWork
description: Continue from the deep repo audit session — review completed work, address remaining items
argument-hint: Optional focus (e.g., "SHOW CORTEX AGENTS fix", "review PR", "next improvements")
---

## Context — Previous Session Summary

A comprehensive repo audit was completed on branch `feat/semantic-sync-full-validation`.
PR #2 is open: https://github.com/WaynezWorld/insulintel-semantic-models/pull/2

### Completed Work (all validated ✅)

| # | Fix | Files |
|---|-----|-------|
| 1 | **Centralized constants** — `SCHEMA_FQN`, `AGENT_FQN`, view lists extracted to single source | `scripts/semantic_diff/constants.py` (NEW), `app/deployer.py`, `scripts/build_deploy.py`, `scripts/semantic_diff/export_sf.py` |
| 2 | **CI workflow** — added path triggers for `app/**`, `pyproject.toml`; switched to `pip install -e .` | `.github/workflows/ci.yml` |
| 3 | **Deleted redundant `requirements.txt`** — `pyproject.toml` is sole source of truth | `requirements.txt` (DELETED) |
| 4 | **Removed hardcoded DB defaults** — `init_connection()` no longer injects `DB_INSULINTEL`/`SCH_SEMANTIC` | `app/streamlit_app.py` |
| 5 | **Fixed git staging** — `_do_git_commit()` now stages `semantic_views/` alongside `instructions/` | `app/streamlit_app.py` |
| 6 | **Added `app/__init__.py`** — makes `app/` a proper Python package | `app/__init__.py` (NEW) |
| 7 | **Added 21 unit tests** for `assemble.py` instruction assembly logic | `tests/test_assemble.py` (NEW), `pyproject.toml` |
| 8 | **Fixed Streamlit secrets resolution** — deleted `app/.streamlit/` which was overriding real secrets | `app/.streamlit/` (DELETED) |

### Validation Results
- `python scripts/validate_repo.py` — ✅ all checks pass
- `python scripts/build_deploy.py` — ✅ artefacts generated
- `pytest tests/ -v` — ✅ 21/21 tests pass
- Streamlit app connects to Snowflake — ✅

### Known Remaining Issues

1. **`SHOW CORTEX AGENTS` syntax error** (visible in Diff tab → Agent target → "Fetch from Snowflake"):
   - Error: `001003 (42000): SQL compilation error: syntax error line 1 at position 12 unexpected 'AGENTS'`
   - Location: `app/deployer.py` → `get_live_agent_instructions()` (~line 208)
   - Current SQL: `SHOW CORTEX AGENTS LIKE 'INSULINTEL' IN SCHEMA {SCHEMA_FQN}`
   - Likely fix: Update syntax for current Snowflake version (may need `SHOW CORTEX SEARCH SERVICES` or a different catalog query)

2. **Additional test coverage** — only `assemble.py` has tests; `deployer.py`, `snapshot_manager.py`, `diff_engine.py`, etc. are untested

3. **README could be expanded** — current README is minimal; could document the instruction assembly pipeline, Streamlit app usage, and deployment workflow

### Key Architecture Notes
- **Instruction pipeline**: Modular YAML files in `instructions/` → assembled via `assembly.yaml` manifest → injected into semantic view YAMLs and agent SQL in `deploy/`
- **Snowflake auth**: PROGRAMMATIC_ACCESS_TOKEN (PAT), account `LIYWRBM-JZC37138`
- **Constants module**: `scripts/semantic_diff/constants.py` — import from here, not hardcode
- **Streamlit secrets**: Must be at project-level `.streamlit/secrets.toml` (NOT inside `app/`)

## Instructions

1. Read this context to understand what has been done
2. Check the current state of the branch and PR
3. Address the user's specific request or, if none given, propose next steps from the remaining issues above
4. Validate changes the same way: `validate_repo.py`, `build_deploy.py`, `pytest tests/ -v`

```
