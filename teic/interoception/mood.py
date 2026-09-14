"""Mood -- the slow integrator over the affect trajectory (Phase 2).

`AffectState`'s docstring already states the intent: "mood is a slow
integrator over the affect trajectory." `MOOD_ALPHA` is deliberately much
smaller than `affect_dynamics.ALPHA` so mood genuinely lags valence rather
than tracking it tick-for-tick with a different label -- that distinction is
exercised directly in `tests/test_interoception/test_mood.py`.
"""

from __future__ import annotations

MOOD_ALPHA = 0.05


class MoodTracker:
    """Per-session single-state EWMA over valence. Starts at 0.0 (neutral),
    not a hand-picked initial mood."""

    def __init__(self, alpha: float = MOOD_ALPHA) -> None:
        self._alpha = alpha
        self._mood: float = 0.0

    def update(self, valence: float) -> float:
        self._mood = self._mood + self._alpha * (valence - self._mood)
        return self._mood
