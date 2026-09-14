from __future__ import annotations

from teic.interoception.mood import MoodTracker


def test_mood_starts_neutral() -> None:
    tracker = MoodTracker()
    assert tracker.update(0.0) == 0.0


def test_mood_moves_toward_sustained_valence() -> None:
    tracker = MoodTracker()
    mood = 0.0
    for _ in range(50):
        mood = tracker.update(1.0)
    assert mood > 0.0


def test_mood_lags_far_behind_a_single_tick_ewma_of_the_same_input() -> None:
    """Mood must be a genuinely SLOWER integrator than a single EWMA update
    at affect_dynamics.ALPHA -- not just another EWMA with the same label."""
    from teic.interoception.affect_dynamics import ALPHA

    mood_tracker = MoodTracker()
    fast_state = 0.0
    n = 10
    for _ in range(n):
        mood_tracker.update(1.0)
        fast_state = fast_state + ALPHA * (1.0 - fast_state)

    mood_after_n = mood_tracker.update(1.0)
    assert mood_after_n < fast_state
