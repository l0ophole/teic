"""Self/other/ambiguous provenance tagging for the winning candidate.

Phase 5 scope ruling: the only live candidate sources are agent-internal
("interoception", "memory" -- see phase5-plan.md's scope ruling 1), so
every real call this phase returns "self". "user_message" (the real
Phase 9 user-turn candidate source; see `teic/daemon.py`) is dispatched
to "other". No live source produces "ambiguous" yet -- that's an honest
gap, not a placeholder; it waits for a source that can itself be
uncertain about its own provenance (e.g. a mis-attributed effector
outcome), not built yet.
"""

from __future__ import annotations

from typing import Literal

from teic.models.workspace import WorkspaceCandidate

MinenessTag = Literal["self", "other", "ambiguous"]

_OTHER_SOURCES = {"user_message"}


def mineness_tag(candidate: WorkspaceCandidate) -> MinenessTag:
    if candidate.source_module in _OTHER_SOURCES:
        return "other"
    return "self"
