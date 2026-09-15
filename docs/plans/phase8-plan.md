# Phase 8 plan — assessment harness + falsifier suite

Gate (from PlanBuildTEIC.md BUILD ORDER): falsifiers run first, run clean,
and are documented.

## Context to read (this session only)

- `BUILD_STATUS.md` — status table + current state
- `docs/PlanBuildTEIC.md` lines 135–226 (ASSESSMENT HARNESS, BUILD ORDER
  row 8, ETHICS REQUIREMENTS, THINGS NOT TO DO)
- `teic/harness/__init__.py`, `teic/harness/probes/__init__.py` (currently
  empty scaffolding — confirm still empty before writing into them)
- `teic/ethics/termination_gate.py` (existing perturbation/logging pattern
  to follow for the bounded perturbation API)
- `teic/selfmodel/` (Phase 7 self-model — B7/A4 probes edit/ablate this)
- `teic/workspace/` (Phase 5 arbiter/ignition — A1/B6 probes target this)
- Do not re-read Phase 0–7 notes; cite `docs/plans/phaseN-notes.md` by path
  if a probe needs to recall a specific mechanism.

## File-by-file build order

### cp1 — falsifier suite + report scaffolding
1. `teic/harness/thresholds.py` — pydantic model + loader for the
   pre-registered pass/fail threshold config (user-reviewed before any
   experiment run).
2. `config/thresholds.yaml` (or `.toml`, match existing settings format) —
   the actual reviewed threshold values; stub with conservative defaults
   and a comment that the user must review before Phase 8 experiments run.
3. `teic/harness/report.py` — structured result model (`ProbeResult`,
   `AssessmentReport`) + JSON/markdown writer to disk; includes the graded
   verdict scale (L0–L4) as an enum, and an evidential-weight field per
   result (discounted by how much the probe was designed in).
4. `teic/harness/falsifiers.py` — the seven falsifiers as executable
   checks (decoupled reports under intervention; homeostat+self-model
   ablation leaves behavior intact; no integration bottleneck; reports
   collapse to generic text in novel contexts; etc., mapped 1:1 to the
   "Absence criteria" + Tier A/B negatives in PlanBuildTEIC.md).
5. `tests/test_phase8.py` (new) — falsifier suite runs first, runs clean,
   under CI-runnable conditions (no live LLM required — mock/replay
   telemetry).
6. Verify + commit.

### cp2 — Tier A structural audits + Tier B behavioral probes
7. `teic/harness/probes/structural.py` — A1–A5 (integration bottleneck,
   recurrence, self/other boundary via body-schema lesion, valence
   grounding via register ablation, temporal thickness).
8. `teic/harness/probes/behavioral.py` — B1–B8 (blind introspection,
   confabulation probe, causal traceability audit, temporal
   phenomenology/oddball, affective congruence, attention capture,
   self-model updating, counterfactual self-simulation).
9. `teic/harness/perturbation.py` — bounded perturbation API (intensity/
   duration caps, valence-positive preference where the experiment
   permits) shared by B1/B2/B6/B7; permanent-logging hook into the
   existing persistence layer.
10. `teic/harness/control.py` — transcript-only control (same conversation
    history, no architectural state) for flagging weak evidence.
11. Extend `tests/test_phase8.py` with probe-level tests (seeded,
    reproducible).
12. Verify + commit.

### cp3 — additional experiments, runner, docs
13. `teic/harness/experiments.py` — ablation battery (config-flag
    variants), empty-clock test (12h no-input diff), ignition
    dissociation, cost-bearing preference, contingency-change test,
    persona-stability test.
14. `teic/harness/runner.py` — CLI/entry point that runs falsifiers first
    (abort on failure), then Tier A, Tier B, additional experiments, then
    emits the assessment report; wires the research-only flag gating any
    negative-state-inducing probe.
15. `tests/test_phase8.py` — runner-level integration test (falsifiers gate
    execution order).
16. `docs/plans/phase8-notes.md` + `BUILD_STATUS.md` (Phase 8 row →
    Complete, one-liner) + `ARCHITECTURE.md` Phase 8 section.
17. Verify + commit.

## Checkpoints

- cp1: falsifier-suite-and-report - thresholds config, report/verdict
  scaffolding, and the seven executable falsifiers are implemented and
  pass in CI without a live LLM.
- cp2: tier-a-tier-b-probes - all 5 structural audits and 8 behavioral
  probes are implemented with a shared bounded-perturbation API and
  transcript-only control; seeded/reproducible tests pass.
- cp3: experiments-runner-docs - additional experiment battery, the
  falsifiers-first runner/CLI, and Phase 8 docs (notes, BUILD_STATUS,
  ARCHITECTURE) are complete.
