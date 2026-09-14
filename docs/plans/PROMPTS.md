# Prompt templates for building phases (copy-paste)

Keep prompts short — the token cost isn't the prompt itself, it's what
Claude reads in response. Never say "get up to speed" or "review the
project"; name the exact files to read.

## 1. Plan-writing session (fresh `/clear`, phase has no plan yet)

For Phases 6-9, one session to write the plan, then build in a fresh
session. If the phase is large, treat the plan itself as a checkpoint.

```
Read BUILD_STATUS.md (table + "Current state" only) and the Phase 6 sections
of docs/PlanBuildTEIC.md. Write docs/plans/phase6-plan.md: file-by-file build
order, named checkpoints (2-3 session ends), and a "context to read" list.
Do not start building.
```

## 2. Start building a phase (fresh `/clear`, plan exists)

```
Read docs/plans/phase6-plan.md and the "Current state" section of
BUILD_STATUS.md. Build Phase 6 per the plan, following CLAUDE.md's build
protocol. Stop at checkpoint cp1 and run the batched verify+commit.
```

## 3. Resume at a checkpoint (fresh `/clear`, mid-phase)

```
Continue Phase 6 at checkpoint cp2 per BUILD_STATUS.md and the checkpoint
section of docs/plans/phase6-plan.md. Do not re-read completed checkpoints'
files unless the plan requires it.
```

## 4. Correction (repo surveying or context ballooning)

```
You're off-protocol — re-read CLAUDE.md. Stop surveying, finish the current
edit, run the batched verify command, and stop at the next checkpoint.
```

## Reminders

- Name the checkpoint explicitly (cp1/cp2) — that's the contract for where
  the session ends. Every phase plan must define 2-3 named checkpoints.
- After each checkpoint: batched verify+commit runs, BUILD_STATUS.md gets
  updated (<= 5 lines), then user runs `/clear`.
- Substitute the right phase number / checkpoint name in each template.

## Or: let the orchestrator prompt for you

`scripts/orchestrate_build.py` automates all of the above: each checkpoint
segment runs as its own headless `claude -p` session (fresh context — no
/clear needed), verifies the checkpoint (new commit + pytest + mypy), and
pauses for you between segments.

```
cd /mnt/ide/teamssd/part1/projects/teic
python scripts/orchestrate_build.py --status        # current state
python scripts/orchestrate_build.py --phase 6       # semi-attended pilot
python scripts/orchestrate_build.py --phase 6 --dry-run
python scripts/orchestrate_build.py --phase 6 --auto  # unattended overnight
.venv/bin/python scripts/build_dashboard.py  # watch in a second terminal
```

On halt (exit 2), bring the printed transcript path to opencode for
diagnosis. On usage-limit halt (exit 3), re-run after the window resets —
or run with --auto, which sleeps until the rate-limit reset timestamp and
continues by itself.

