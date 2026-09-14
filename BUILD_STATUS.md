# Build Status

| Phase | Status |
|---|---|
| 0 — Daemon skeleton | **Complete** |
| 1 — Telemetry → interoceptive vector | Not started |
| 2 — Non-linguistic modulation (real gate) | Not started |
| 3 — Forward models, prediction error | Not started |
| 4 — Memory timescales, decay, consolidation | Not started |
| 5 — Workspace arbiter, ignition | Not started |
| 6 — Viability, allostasis | Not started |
| 7 — Self-model, metacognition | Not started |
| 8 — Assessment harness + falsifiers | Not started |
| 9 — UI (terminal + web) | Not started |

## Phase 0 — complete

- [x] git repo initialized
- [x] `pyproject.toml`, package skeleton, migrations, settings
- [x] Verify OpenRouter model slugs against `/models` (done — see ARCHITECTURE.md)
- [x] `pip install -e ".[dev]"` completes cleanly
- [x] `pytest` passes (3 tests: phase-0 gate x2, prompt_assembly regression guard)
- [x] `mypy` passes on `teic/models`, `teic/interoception`, `teic/workspace`, `teic/llm`
- [x] Manual smoke test: `python -m teic` — clean start, ticks persisted, clean SIGTERM shutdown
- [x] Fixed a real bug found during manual verification: `run_migrations` used
      `executescript`, which implicitly commits before running, so a
      process killed mid-migration left partially-applied DDL with no
      `schema_migrations` record and could not recover on restart. Fixed by
      opening the connection with `isolation_level=None` and applying each
      migration's statements individually inside one explicit
      `BEGIN`/`COMMIT` (rolled back on any exception).
- [x] First commit

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
python -m teic   # Ctrl+C after a few seconds; check data/teic.db has tick rows
```
