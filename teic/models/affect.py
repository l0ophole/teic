from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# Named attractors are DISPLAY-ONLY labels computed post hoc from the continuous
# (valence, arousal) trajectory. They are never stored as ground truth and never
# fed back causally into any other computation -- this is the concrete mechanism
# that enforces "do not hard-code emotions as labels" (spec: Things Not To Do).
_ATTRACTOR_ANCHORS: tuple[tuple[str, float, float], ...] = (
    ("frustration", -0.6, 0.7),
    ("relief", 0.6, -0.4),
    ("curiosity", 0.4, 0.5),
    ("boredom", -0.2, -0.7),
    ("distress", -0.7, 0.8),
    ("contentment", 0.5, -0.6),
    ("neutral", 0.0, 0.0),
)


class AffectState(BaseModel):
    """Continuous valence x arousal state, derived from register deltas.

    valence ~= d/dt(predicted viability) - precision-weighted expectation
    arousal ~= ||prediction_error|| + resource mobilization
    mood is a slow integrator over the affect trajectory.
    """

    valence: float
    arousal: float
    mood: float
    tick_id: int
    ts: datetime

    def nearest_attractor_label(self) -> str:
        """Post hoc display label only. Never assign to a field; always compute."""
        best_label = "neutral"
        best_dist = float("inf")
        for label, v_anchor, a_anchor in _ATTRACTOR_ANCHORS:
            dist = (self.valence - v_anchor) ** 2 + (self.arousal - a_anchor) ** 2
            if dist < best_dist:
                best_dist = dist
                best_label = label
        return best_label
