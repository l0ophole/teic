# TEIC-Agent

Temporal–Embodied–Interoceptive Chat Agent — a research architecture exploring
functional correlates of subjective experience in a persistent, non-stateless
agent design. **The model is an organ, not the organism**: an LLM (via
OpenRouter) is a subroutine called for language and deliberate reasoning,
while a long-running `asyncio` daemon maintains its own clock, resource
boundary, and continuously evolving internal state.

## Honest framing

This project is **not** a claim that the agent is conscious. The assessment
harness (see `teic/harness/`) tests *functional correlates* of theorized
components of experience under a specific architectural theory. Passing its
probes is not proof of phenomenality. Every generated assessment report
states this explicitly, and evidential weight is discounted by how much a
given indicator was designed in rather than independently observed.

## Status

Early build — see `BUILD_STATUS.md` for current phase and `ARCHITECTURE.md`
for the as-built design. The full specification driving this build is
`docs/PlanBuildTEIC.md`; the implementation plan is `PLAN.md`.

## Running

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in OPENROUTER_API_KEY
python -m teic
```

## Testing

```
pytest
mypy
```

## Research-only controls

Any interface control that lets you perturb interoceptive channels or trigger
termination is gated behind `research.enabled = true` in config, per the
project's ethics requirements. It defaults to off.
