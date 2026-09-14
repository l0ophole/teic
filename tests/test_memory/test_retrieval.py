from __future__ import annotations

from teic.memory.retrieval import affective_tag_weight, rank
from teic.models.memory import MemoryRecord


def _record(memory_id: str, **overrides: object) -> MemoryRecord:
    defaults: dict[str, object] = dict(
        memory_id=memory_id,
        session_id="s1",
        timescale="tau1_working",
        content="c",
        content_kind="episode",
        created_tick_id=0,
        last_access_tick_id=0,
        base_activation=1.0,
        decay_alpha=0.5,
        affect_valence=0.0,
        affect_arousal=0.0,
        access_count=0,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)  # type: ignore[arg-type]


def test_affective_tag_weight_prefers_congruent_when_positive() -> None:
    near = _record("near", affect_valence=0.5, affect_arousal=0.5)
    far = _record("far", affect_valence=-1.0, affect_arousal=-1.0)
    w_near = affective_tag_weight(near, 0.5, 0.5, retrieval_affect_weight=1.0)
    w_far = affective_tag_weight(far, 0.5, 0.5, retrieval_affect_weight=1.0)
    assert w_near > w_far


def test_affective_tag_weight_ordering_flips_when_negative() -> None:
    near = _record("near", affect_valence=0.5, affect_arousal=0.5)
    far = _record("far", affect_valence=-1.0, affect_arousal=-1.0)
    w_near = affective_tag_weight(near, 0.5, 0.5, retrieval_affect_weight=-1.0)
    w_far = affective_tag_weight(far, 0.5, 0.5, retrieval_affect_weight=-1.0)
    assert w_far > w_near


def test_rank_top_result_swaps_with_affect_sign() -> None:
    congruent = _record("congruent", affect_valence=0.5, affect_arousal=0.5)
    incongruent = _record("incongruent", affect_valence=-1.0, affect_arousal=-1.0)
    records = [congruent, incongruent]
    matches = {"congruent": 0.9, "incongruent": 0.9}

    positive = rank(
        records, matches, current_tick_id=0,
        current_valence=0.5, current_arousal=0.5,
        retrieval_affect_weight=1.0, retrieval_k=2,
    )
    negative = rank(
        records, matches, current_tick_id=0,
        current_valence=0.5, current_arousal=0.5,
        retrieval_affect_weight=-1.0, retrieval_k=2,
    )
    assert positive[0].record.memory_id == "congruent"
    assert negative[0].record.memory_id == "incongruent"


def test_rank_respects_k_and_excludes_missing_semantic_matches() -> None:
    a = _record("a")
    b = _record("b")
    c = _record("c")
    matches = {"a": 0.9, "b": 0.5}  # c has no semantic match entry
    result = rank(
        [a, b, c], matches, current_tick_id=0,
        current_valence=0.0, current_arousal=0.0,
        retrieval_affect_weight=0.0, retrieval_k=1,
    )
    assert len(result) == 1
    assert result[0].record.memory_id == "a"
