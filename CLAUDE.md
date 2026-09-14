# TEIC build protocol (token budget rules)

## During plan-execution phases, read ONLY
- `docs/plans/phaseN-plan.md` (current phase only)
- `BUILD_STATUS.md`: the status table + current phase section
- Files the phase plan explicitly names; use offset/limit for large ones

Do NOT: survey the repo, re-read `ARCHITECTURE.md` or `PLAN.md` unless the
phase plan says to, or re-read completed-phase sections.

## Session checkpoints
Each phase is built in 2–3 sessions split at named checkpoints defined in
its plan file. At a checkpoint:
1. Run the batched verify+commit command (below) in ONE Bash call
2. Update `BUILD_STATUS.md` (current state + next checkpoint, <= 5 lines)
3. User runs `/clear`; resume with "Continue Phase N at checkpoint <name>"

If a session's context passes ~120K before reaching a checkpoint, stop at
the next natural stopping point, treat it as an extra checkpoint.

## Verification is batched — one Bash call per checkpoint
```
.venv/bin/pytest -q && .venv/bin/mypy && git add -A && git commit -m "phase N: <checkpoint>"
```
Never run pytest/mypy/git as separate turns. Use `.venv/bin/` binaries
directly (do not `source .venv/bin/activate` — it is not on the
permission allowlist). On failure, fix and re-run the same batch; do not
narrate between steps.

## Delegate to subagents (Task tool) — do NOT do in main context
- Repo/package surveys or "how does X work" deep-dives
- Test-failure triage across multiple files
- Multi-file code reviews
Keep the main context for: reading the plan, editing files, running the
batched verify command.

## Notes discipline
- Completed phases: one line in `BUILD_STATUS.md`; detail lives in
  `docs/plans/phaseN-notes.md`
- Never inline file contents in summaries; reference paths + line numbers
