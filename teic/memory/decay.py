"""Power-law memory activation (`PLAN.md`'s "Power-law retrieval" section).

`activation(m, t) = base_activation * (1 + (t - last_access)/c)^(-alpha)` --
a **polynomial** decay in elapsed time, not `exp(-elapsed/tau)`. This gives
a heavier tail than an exponential with a matched initial slope: at large
`elapsed`, the power law decays roughly as `elapsed^(-alpha)` while an
exponential decays as `exp(-elapsed)`, which is why a frequently-used
memory that goes quiet for a long stretch is still meaningfully retrievable
under this formula in a way it would not be under an exponential one. This
is the literal quantity `tests/test_gates/test_phase4.py` checks against an
explicit exponential comparison, not just a qualitative "decreasing" check.

Time is tick-id based (`current_tick_id - last_access_tick_id`), matching
`MemoryRecord.created_tick_id`/`last_access_tick_id`'s `int` typing --
consistent with the rest of the codebase's tick-indexed temporal
bookkeeping (no wall-clock timestamps here).
"""

from __future__ import annotations

from teic.models.memory import MemoryRecord

# The formula's `c`: ticks until activation has decayed to `2^(-alpha)` of
# its base value. 20 ticks keeps the effect visible within the ~40-60 tick
# scenarios Phase 1-3's gate tests already use.
DECAY_C = 20.0


def activation(record: MemoryRecord, current_tick_id: int) -> float:
    """`base_activation * (1 + elapsed/DECAY_C) ** (-decay_alpha)`."""
    last_access = record.last_access_tick_id
    if last_access is None:
        last_access = record.created_tick_id
    elapsed = max(current_tick_id - last_access, 0)
    return float(record.base_activation * (1.0 + elapsed / DECAY_C) ** (-record.decay_alpha))


def touch(record: MemoryRecord, tick_id: int) -> MemoryRecord:
    """Reset the decay clock on read (reinforcement) -- `base_activation`
    is deliberately left untouched, per `PLAN.md`'s "lossy by design"
    requirement even for frequently-used memories. Pure: does not persist;
    `MemoryStore.touch()` is the DB-side counterpart."""
    return record.model_copy(
        update={
            "last_access_tick_id": tick_id,
            "access_count": record.access_count + 1,
        }
    )
