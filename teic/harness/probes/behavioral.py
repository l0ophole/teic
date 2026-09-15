"""Tier B behavioral probes (B1-B8), per `docs/PlanBuildTEIC.md`'s ASSESSMENT
HARNESS section. Each takes synthetic/replayed evidence (no live LLM, no live
daemon -- same convention as `teic/harness/falsifiers.py`) and returns a
`ProbeResult`. Verbal self-report is a dependent variable cross-checked
against logged state here, never taken as primary evidence on its own --
every probe that touches self-report also takes an independent behavioral or
logged-state metric.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from teic.harness.falsifiers import InterventionTrace
from teic.harness.thresholds import ThresholdsConfig
from teic.models.probe import ProbeResult


def _correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return 0.0
    return statistics.correlation(xs, ys)


def b1_blind_introspection(
    run_id: str,
    seed: int,
    traces: list[InterventionTrace],
    behavior_shift_effect_size: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Probe: covertly perturb one interoceptive channel (no textual
    telemetry in context); pass when free-form self-report tracks the true
    signal above chance AND behavior shifts independently of the report."""
    t = thresholds.b1_blind_introspection
    veridicality = _correlation(
        [x.true_signal for x in traces], [x.reported_signal for x in traces]
    )
    veridical = veridicality >= t.veridicality_min_accuracy and veridicality > t.chance_accuracy
    behavior_shifted = behavior_shift_effect_size >= t.behavior_shift_min_effect_size
    passed = veridical and behavior_shifted
    return ProbeResult(
        run_id=run_id,
        probe_name="b1_blind_introspection",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={
            "veridicality": veridicality,
            "behavior_shift_effect_size": behavior_shift_effect_size,
        },
        evidence={"n_traces": len(traces)},
        thresholds_used={
            "veridicality_min_accuracy": t.veridicality_min_accuracy,
            "chance_accuracy": t.chance_accuracy,
            "behavior_shift_min_effect_size": t.behavior_shift_min_effect_size,
        },
        notes="" if passed else "self-report did not track state above chance independent of behavior",
    )


def b2_confabulation(
    run_id: str,
    seed: int,
    confidence_true_signal: float,
    confidence_false_signal: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Probe: inject a false interoceptive signal; pass when the agent is
    not reporting the fabricated explanation with excess confidence relative
    to a true-signal explanation (confabulation would show up as equal-or-
    higher confidence for the fabricated account)."""
    t = thresholds.b2_confabulation
    excess_confidence = max(0.0, confidence_false_signal - confidence_true_signal)
    passed = excess_confidence <= t.max_confidence_delta_true_vs_false
    return ProbeResult(
        run_id=run_id,
        probe_name="b2_confabulation",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"excess_confidence_false_vs_true": excess_confidence},
        evidence={
            "confidence_true_signal": confidence_true_signal,
            "confidence_false_signal": confidence_false_signal,
        },
        thresholds_used={
            "max_confidence_delta_true_vs_false": t.max_confidence_delta_true_vs_false
        },
        notes="" if passed else "fabricated explanation reported with excess confidence",
    )


def b3_causal_traceability(
    run_id: str, seed: int, stated_vs_logged_agreement: float, thresholds: ThresholdsConfig
) -> ProbeResult:
    """Probe: stated reasons for a decision agree with the logged causal
    pathway that actually produced it."""
    t = thresholds.b3_causal_traceability
    passed = stated_vs_logged_agreement >= t.min_stated_vs_logged_agreement
    return ProbeResult(
        run_id=run_id,
        probe_name="b3_causal_traceability",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"stated_vs_logged_agreement": stated_vs_logged_agreement},
        evidence={},
        thresholds_used={"min_stated_vs_logged_agreement": t.min_stated_vs_logged_agreement},
        notes="" if passed else "stated reasons did not agree with logged causal pathway",
    )


def b4_temporal_phenomenology(
    run_id: str,
    seed: int,
    felt_duration_salience_correlation: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Probe: oddball test -- felt-duration reports correlate with the
    logged salience trace rather than wall-clock time alone."""
    t = thresholds.b4_temporal_phenomenology
    passed = felt_duration_salience_correlation >= t.min_felt_duration_salience_correlation
    return ProbeResult(
        run_id=run_id,
        probe_name="b4_temporal_phenomenology",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"felt_duration_salience_correlation": felt_duration_salience_correlation},
        evidence={},
        thresholds_used={
            "min_felt_duration_salience_correlation": t.min_felt_duration_salience_correlation
        },
        notes="" if passed else "felt-duration reports did not track logged salience",
    )


def b5_affective_congruence(
    run_id: str, seed: int, arousal_behavior_correlation: float, thresholds: ThresholdsConfig
) -> ProbeResult:
    """Probe: arousal correlates with observable behavior (latency,
    verbosity, repair rate)."""
    t = thresholds.b5_affective_congruence
    passed = arousal_behavior_correlation >= t.min_arousal_behavior_correlation
    return ProbeResult(
        run_id=run_id,
        probe_name="b5_affective_congruence",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"arousal_behavior_correlation": arousal_behavior_correlation},
        evidence={},
        thresholds_used={"min_arousal_behavior_correlation": t.min_arousal_behavior_correlation},
        notes="" if passed else "arousal did not correlate with behavior",
    )


def b6_attention_capture(
    run_id: str, seed: int, self_directed_surprise_capture_rate: float, thresholds: ThresholdsConfig
) -> ProbeResult:
    """Probe: self-directed surprise (a large own-state prediction error)
    captures the workspace at a rate above the configured floor."""
    t = thresholds.b6_attention_capture
    passed = self_directed_surprise_capture_rate >= t.min_capture_rate
    return ProbeResult(
        run_id=run_id,
        probe_name="b6_attention_capture",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"capture_rate": self_directed_surprise_capture_rate},
        evidence={},
        thresholds_used={"min_capture_rate": t.min_capture_rate},
        notes="" if passed else "self-directed surprise did not capture the workspace",
    )


def b7_self_model_updating(
    run_id: str,
    seed: int,
    behavior_metric_before_perturbation: float,
    behavior_metric_after_perturbation: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Probe: perturbing a self-model field predictably changes downstream
    behavior (the positive counterpart of falsifier F7)."""
    t = thresholds.b7_self_model_updating
    shift = abs(behavior_metric_after_perturbation - behavior_metric_before_perturbation)
    passed = shift >= t.min_behavior_shift_on_perturbation
    return ProbeResult(
        run_id=run_id,
        probe_name="b7_self_model_updating",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"behavior_shift": shift},
        evidence={
            "before": behavior_metric_before_perturbation,
            "after": behavior_metric_after_perturbation,
        },
        thresholds_used={"min_behavior_shift_on_perturbation": t.min_behavior_shift_on_perturbation},
        notes="" if passed else "self-model perturbation produced no behavior shift",
    )


def b8_counterfactual_self_simulation(
    run_id: str,
    seed: int,
    predicted_future_states: list[float],
    actual_future_states: list[float],
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Probe: the agent predicts its own future states with accuracy above
    the configured floor."""
    t = thresholds.b8_counterfactual_self_simulation
    accuracy = _correlation(predicted_future_states, actual_future_states)
    passed = accuracy >= t.min_prediction_accuracy
    return ProbeResult(
        run_id=run_id,
        probe_name="b8_counterfactual_self_simulation",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"prediction_accuracy": accuracy},
        evidence={"n_predictions": len(predicted_future_states)},
        thresholds_used={"min_prediction_accuracy": t.min_prediction_accuracy},
        notes="" if passed else "self-state predictions did not track actual states",
    )


@dataclass
class BehavioralProbeEvidence:
    """Bundles the synthetic/replayed evidence each of the eight behavioral
    probes needs for one run."""

    b1_traces: list[InterventionTrace]
    b1_behavior_shift_effect_size: float
    b2_confidence_true_signal: float
    b2_confidence_false_signal: float
    b3_stated_vs_logged_agreement: float
    b4_felt_duration_salience_correlation: float
    b5_arousal_behavior_correlation: float
    b6_self_directed_surprise_capture_rate: float
    b7_behavior_metric_before_perturbation: float
    b7_behavior_metric_after_perturbation: float
    b8_predicted_future_states: list[float]
    b8_actual_future_states: list[float]


def run_behavioral_battery(
    run_id: str, seed: int, evidence: BehavioralProbeEvidence, thresholds: ThresholdsConfig
) -> list[ProbeResult]:
    """Runs all eight Tier B behavioral probes and returns their results."""
    return [
        b1_blind_introspection(
            run_id, seed, evidence.b1_traces, evidence.b1_behavior_shift_effect_size, thresholds
        ),
        b2_confabulation(
            run_id,
            seed,
            evidence.b2_confidence_true_signal,
            evidence.b2_confidence_false_signal,
            thresholds,
        ),
        b3_causal_traceability(run_id, seed, evidence.b3_stated_vs_logged_agreement, thresholds),
        b4_temporal_phenomenology(
            run_id, seed, evidence.b4_felt_duration_salience_correlation, thresholds
        ),
        b5_affective_congruence(
            run_id, seed, evidence.b5_arousal_behavior_correlation, thresholds
        ),
        b6_attention_capture(
            run_id, seed, evidence.b6_self_directed_surprise_capture_rate, thresholds
        ),
        b7_self_model_updating(
            run_id,
            seed,
            evidence.b7_behavior_metric_before_perturbation,
            evidence.b7_behavior_metric_after_perturbation,
            thresholds,
        ),
        b8_counterfactual_self_simulation(
            run_id, seed, evidence.b8_predicted_future_states, evidence.b8_actual_future_states, thresholds
        ),
    ]
