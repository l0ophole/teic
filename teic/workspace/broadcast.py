"""The ignition gate for turning a WorkspaceBroadcast into an LLM prompt.

assemble_prompt() (teic/llm/prompt_assembly.py) is a pure formatter -- it
has no ignited check of its own, by design (its job is only the no-raw-state
type boundary). This module is the actual "never broadcasts/reports below
threshold" enforcement point: render_prompt_if_ignited() returns None for
any non-ignited broadcast, full stop, before assemble_prompt ever sees it.
daemon.py does not call this yet (Phase 5 scope ruling 2 -- no real
OpenRouter send exists until Phase 6's viability accounting can gate spend),
but this is the seam Phase 6 wires its real send through, so the enforcement
point is real and tested now, not deferred alongside the send itself.
"""

from __future__ import annotations

from teic.interoception.modulation import ModulationParams
from teic.llm.client import ChatPrompt
from teic.llm.prompt_assembly import assemble_prompt
from teic.models.workspace import WorkspaceBroadcast


def render_prompt_if_ignited(
    broadcast: WorkspaceBroadcast,
    narrative_tail: list[str],
    modulation: ModulationParams,
) -> ChatPrompt | None:
    if not broadcast.ignited:
        return None
    return assemble_prompt(broadcast, narrative_tail, modulation)
