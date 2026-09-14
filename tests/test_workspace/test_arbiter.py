from datetime import UTC, datetime

import pytest

from teic.models.affect import AffectState
from teic.models.workspace import WorkspaceCandidate
from teic.workspace.arbiter import (
    WorkspaceArbiter,
    ignition_threshold,
    salience_overrides,
)


def _affect(valence: float = 0.0, arousal: float = 0.0) -> AffectState:
    return AffectState(valence=valence, arousal=arousal, mood=0.0, tick_id=1, ts=datetime.now(UTC))


def _candidate(source: str, salience_parts: tuple[float, float, float, float]) -> WorkspaceCandidate:
    novelty, precision, affective_weight, goal_relevance = salience_parts
    return WorkspaceCandidate(
        source_module=source,
        content={"marker": source},
        novelty=novelty,
        precision=precision,
        affective_weight=affective_weight,
        goal_relevance=goal_relevance,
    )


def test_ignition_threshold_lowers_under_arousal_and_negative_mood():
    calm = ignition_threshold(_affect(arousal=0.0), mood=0.0)
    stressed = ignition_threshold(_affect(arousal=1.0), mood=-1.0)
    assert stressed < calm


def test_select_picks_max_salience_winner():
    low = _candidate("a", (0.2, 0.2, 0.2, 0.2))
    high = _candidate("b", (0.9, 0.9, 0.9, 0.9))
    broadcast = WorkspaceArbiter().select([low, high], _affect(), mood=0.0, tick_id=1)
    assert broadcast.winner.source_module == "b"


def test_subthreshold_winner_is_not_ignited_but_still_scored():
    weak = _candidate("weak", (0.1, 0.1, 0.1, 0.1))  # salience = 0.0001
    broadcast = WorkspaceArbiter().select([weak], _affect(arousal=0.0), mood=0.0, tick_id=1)
    assert broadcast.ignited is False
    assert broadcast.winner.source_module == "weak"  # still selected, just not broadcast-eligible


def test_suprathreshold_winner_is_ignited():
    strong = _candidate("strong", (0.95, 0.95, 0.95, 0.95))
    broadcast = WorkspaceArbiter().select([strong], _affect(arousal=0.0), mood=0.0, tick_id=1)
    assert broadcast.ignited is True


def test_select_requires_at_least_one_candidate():
    with pytest.raises(ValueError):
        WorkspaceArbiter().select([], _affect(), mood=0.0, tick_id=1)


def test_salience_overrides_covers_every_candidate_by_source():
    a = _candidate("a", (0.5, 0.5, 0.5, 0.5))
    b = _candidate("b", (0.1, 0.1, 0.1, 0.1))
    overrides = salience_overrides([a, b], winner=a)
    assert set(overrides) == {"a", "b"}
    assert overrides["a"] == pytest.approx(1.0 + a.salience)
    assert overrides["b"] == pytest.approx(1.0 + b.salience)
