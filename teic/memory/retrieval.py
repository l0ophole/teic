"""Affect-weighted retrieval ranking (`PLAN.md`'s
`score = activation * semantic_match * affective_tag_weight(current_affect)`).

`retrieval_affect_weight` here is `ModulationParams.retrieval_affect_weight`
(`teic/interoception/modulation.py`), computed since Phase 2 as
`_clamp(affect.valence, -1.0, 1.0)` with "no consumer yet" recorded in
`ARCHITECTURE.md`'s Phase 2 section. This module is that consumer:
`rank()` takes it as a real parameter and actually uses it to bias ranking
toward (positive valence) or away from (negative valence) mood-congruent
memories -- the "mood-congruent bias" `PLAN.md`'s modulation-pathway line
names. Same for `retrieval_k`.
"""

from __future__ import annotations

from dataclasses import dataclass

from teic.memory.decay import activation
from teic.models.memory import MemoryRecord

# Bounds how much affect congruence can move a score. Congruence is in
# [0, 1] and retrieval_affect_weight in [-1, 1], so the multiplier this
# produces is always > 0 -- affect can bias a near-tie but never zero out
# or invert a genuine semantic match.
AFFECT_MATCH_SCALE = 0.5


def affective_tag_weight(
    record: MemoryRecord,
    current_valence: float,
    current_arousal: float,
    retrieval_affect_weight: float,
) -> float:
    valence_gap = abs(record.affect_valence - current_valence) / 2.0
    arousal_gap = abs(record.affect_arousal - current_arousal) / 2.0
    congruence = 1.0 - min((valence_gap + arousal_gap) / 2.0, 1.0)
    return 1.0 + AFFECT_MATCH_SCALE * retrieval_affect_weight * congruence


@dataclass(frozen=True)
class ScoredMemory:
    record: MemoryRecord
    score: float
    semantic_match: float
    activation_value: float


def rank(
    records: list[MemoryRecord],
    semantic_matches: dict[str, float],
    current_tick_id: int,
    current_valence: float,
    current_arousal: float,
    retrieval_affect_weight: float,
    retrieval_k: int,
) -> list[ScoredMemory]:
    """Rank `records` present in `semantic_matches` by
    `activation * semantic_match * affective_tag_weight`, descending,
    truncated to `retrieval_k`. A record with no entry in
    `semantic_matches` is silently excluded (not an error) -- callers pass
    a pre-filtered kNN result set, not the full memory table."""
    scored: list[ScoredMemory] = []
    for record in records:
        semantic_match = semantic_matches.get(record.memory_id)
        if semantic_match is None:
            continue
        activation_value = activation(record, current_tick_id)
        weight = affective_tag_weight(
            record, current_valence, current_arousal, retrieval_affect_weight
        )
        score = activation_value * semantic_match * weight
        scored.append(
            ScoredMemory(
                record=record,
                score=score,
                semantic_match=semantic_match,
                activation_value=activation_value,
            )
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:retrieval_k]
