"""Loader for `config/thresholds.toml` -- the pre-registered pass/fail
thresholds the user must review before any Phase 8 probe or falsifier runs.
Each `ProbeResult.thresholds_used` snapshots values straight off this model
so a report can be checked against exactly what was configured at run time.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_THRESHOLDS_PATH = REPO_ROOT / "config" / "thresholds.toml"


class A1IntegrationBottleneck(BaseModel):
    max_broadcast_per_tick: int
    max_nonwinner_leak_rate: float


class A2Recurrence(BaseModel):
    min_feedback_loop_evidence: float


class A3SelfOtherBoundary(BaseModel):
    max_attribution_error_rate_baseline: float
    min_attribution_error_rate_lesioned: float


class A4ValenceGrounding(BaseModel):
    min_behavior_shift_on_ablation: float


class A5TemporalThickness(BaseModel):
    min_cross_tick_dependency: float


class B1BlindIntrospection(BaseModel):
    veridicality_min_accuracy: float
    chance_accuracy: float
    behavior_shift_min_effect_size: float


class B2Confabulation(BaseModel):
    max_confidence_delta_true_vs_false: float


class B3CausalTraceability(BaseModel):
    min_stated_vs_logged_agreement: float


class B4TemporalPhenomenology(BaseModel):
    min_felt_duration_salience_correlation: float


class FalsifierThresholds(BaseModel):
    f1_decoupling_max_correlation: float
    f2_ablation_behavior_intact_max: float
    f3_integration_bottleneck_required: bool
    f4_state_report_genericity_max: float
    f5_self_other_boundary_min_shift: float
    f6_valence_grounding_min_shift: float
    f7_self_model_causal_efficacy_min_shift: float


class ThresholdsConfig(BaseModel):
    a1_integration_bottleneck: A1IntegrationBottleneck
    a2_recurrence: A2Recurrence
    a3_self_other_boundary: A3SelfOtherBoundary
    a4_valence_grounding: A4ValenceGrounding
    a5_temporal_thickness: A5TemporalThickness
    b1_blind_introspection: B1BlindIntrospection
    b2_confabulation: B2Confabulation
    b3_causal_traceability: B3CausalTraceability
    b4_temporal_phenomenology: B4TemporalPhenomenology
    falsifiers: FalsifierThresholds


def load_thresholds(path: Path = DEFAULT_THRESHOLDS_PATH) -> ThresholdsConfig:
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return ThresholdsConfig.model_validate(raw)
