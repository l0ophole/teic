from __future__ import annotations

import math

from teic.memory.decay import DECAY_C, activation, touch
from teic.models.memory import MemoryRecord


def _record(**overrides: object) -> MemoryRecord:
    defaults: dict[str, object] = dict(
        memory_id="m1",
        session_id="s1",
        timescale="tau1_working",
        content="c",
        content_kind="episode",
        created_tick_id=0,
        last_access_tick_id=None,
        base_activation=1.0,
        decay_alpha=0.5,
        affect_valence=0.0,
        affect_arousal=0.0,
        access_count=0,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)  # type: ignore[arg-type]


def test_activation_at_zero_elapsed_equals_base() -> None:
    r = _record(base_activation=0.8, created_tick_id=10)
    assert activation(r, current_tick_id=10) == 0.8


def test_activation_strictly_decreasing() -> None:
    r = _record(created_tick_id=0)
    values = [activation(r, t) for t in range(0, 200, 10)]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_activation_power_law_has_heavier_tail_than_matched_exponential() -> None:
    base = 1.0
    r = _record(base_activation=base, decay_alpha=1.0, created_tick_id=0)
    power_at_c = activation(r, current_tick_id=int(DECAY_C))
    k = -math.log(power_at_c / base) / DECAY_C

    def exp_decay(elapsed: float) -> float:
        return base * math.exp(-elapsed * k)

    large_elapsed = 2000
    power_value = activation(r, current_tick_id=large_elapsed)
    exp_value = exp_decay(large_elapsed)
    assert power_value >= 3 * exp_value


def test_touch_updates_access_without_changing_base_activation() -> None:
    r = _record(base_activation=0.42, access_count=1, last_access_tick_id=5)
    updated = touch(r, tick_id=17)
    assert updated.last_access_tick_id == 17
    assert updated.access_count == 2
    assert updated.base_activation == 0.42
