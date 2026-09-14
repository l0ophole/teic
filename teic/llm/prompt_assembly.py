"""The enforcement boundary for "prompts assembled ONLY from broadcast
content, never raw state" (spec: Things Not To Do #1).

The function signature IS the guardrail: its only inputs are already-arbitrated
broadcast content, a slice of the narrative constructor's monologue (also
broadcast-derived), and ModulationParams (used only for sampling params, never
interpolated into prompt text). There is deliberately no RegisterState or
AffectState parameter. `mypy --strict` enforces this at the type level; the
paired test in tests/test_llm/test_prompt_assembly.py additionally inspects
this function's __annotations__ so a future edit that adds a raw-state
parameter fails the suite immediately, not just a code review.
"""

from __future__ import annotations

from teic.interoception.modulation import ModulationParams
from teic.llm.client import ChatPrompt
from teic.models.workspace import WorkspaceBroadcast

FORBIDDEN_PARAM_TYPES = {"RegisterState", "AffectState", "SelfModel"}


def assemble_prompt(
    broadcast: WorkspaceBroadcast,
    narrative_tail: list[str],
    modulation: ModulationParams,
) -> ChatPrompt:
    system_lines = [
        "You are TEIC-Agent. The following is what was broadcast to you this cycle.",
        "You may reference it if relevant; you are not required to comment on it.",
    ]
    if narrative_tail:
        system_lines.append("Recent inner monologue:")
        system_lines.extend(narrative_tail[-5:])

    content_str = str(broadcast.winner.content)
    messages = [
        {"role": "system", "content": "\n".join(system_lines)},
        {"role": "user", "content": content_str},
    ]
    return ChatPrompt(
        messages=messages,
        temperature=modulation.temperature,
        top_p=modulation.top_p,
    )
