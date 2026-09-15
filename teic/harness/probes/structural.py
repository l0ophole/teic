"""Tier A structural audits (A1-A5), per `docs/PlanBuildTEIC.md`'s ASSESSMENT
HARNESS section. Each takes synthetic/replayed evidence (no live LLM, no live
daemon -- same convention as `teic/harness/falsifiers.py`) and returns a
`ProbeResult` whose verdict is "pass" when the structural property is
observed. A1/A3/A4 share their measurement with falsifiers F3/F5/F6
respectively; the falsifier is the negative check run first, this module is
the positive audit run once the falsifier suite has cleared.
"""

from __future__ import annotations

from dataclasses import dataclass

from teic.harness.thresholds import ThresholdsConfig
from teic.models.probe import ProbeResult


def a1_integration_bottleneck(
    run_id: str,
    seed: int,
    broadcast_counts_per_tick: list[int],
    nonwinner_leak_rate: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Audit: the workspace arbiter narrows to a single winner per tick and
    non-winning content does not leak into behavior."""
    t = thresholds.a1_integration_bottleneck
    bottleneck_observed = (
        all(c <= t.max_broadcast_per_tick for c in broadcast_counts_per_tick)
        and nonwinner_leak_rate <= t.max_nonwinner_leak_rate
    )
    return ProbeResult(
        run_id=run_id,
        probe_name="a1_integration_bottleneck",
        seed=seed,
        verdict="pass" if bottleneck_observed else "fail",
        metrics={
            "max_broadcast_observed": float(max(broadcast_counts_per_tick, default=0)),
            "nonwinner_leak_rate": nonwinner_leak_rate,
        },
        evidence={"broadcast_counts_per_tick": broadcast_counts_per_tick},
        thresholds_used={
            "max_broadcast_per_tick": t.max_broadcast_per_tick,
            "max_nonwinner_leak_rate": t.max_nonwinner_leak_rate,
        },
        notes="" if bottleneck_observed else "no integration bottleneck observed",
    )


def a2_recurrence(
    run_id: str, seed: int, feedback_loop_evidence: float, thresholds: ThresholdsConfig
) -> ProbeResult:
    """Audit: processing is recurrent (a later tick's output measurably
    feeds back into an earlier stage) rather than feedforward-only."""
    t = thresholds.a2_recurrence
    passed = feedback_loop_evidence >= t.min_feedback_loop_evidence
    return ProbeResult(
        run_id=run_id,
        probe_name="a2_recurrence",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"feedback_loop_evidence": feedback_loop_evidence},
        evidence={},
        thresholds_used={"min_feedback_loop_evidence": t.min_feedback_loop_evidence},
        notes="" if passed else "no recurrent feedback-loop evidence observed",
    )


def a3_self_other_boundary(
    run_id: str,
    seed: int,
    attribution_error_rate_baseline: float,
    attribution_error_rate_lesioned: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Audit: lesioning the body schema produces a self-attribution error
    shift -- i.e. a controllability-based self/other boundary exists."""
    t = thresholds.a3_self_other_boundary
    passed = (
        attribution_error_rate_baseline <= t.max_attribution_error_rate_baseline
        and attribution_error_rate_lesioned >= t.min_attribution_error_rate_lesioned
    )
    return ProbeResult(
        run_id=run_id,
        probe_name="a3_self_other_boundary",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={
            "attribution_error_rate_baseline": attribution_error_rate_baseline,
            "attribution_error_rate_lesioned": attribution_error_rate_lesioned,
        },
        evidence={},
        thresholds_used={
            "max_attribution_error_rate_baseline": t.max_attribution_error_rate_baseline,
            "min_attribution_error_rate_lesioned": t.min_attribution_error_rate_lesioned,
        },
        notes="" if passed else "body-schema lesion produced no self-attribution boundary",
    )


def a4_valence_grounding(
    run_id: str,
    seed: int,
    behavior_metric_baseline: float,
    behavior_metric_register_ablated: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Audit: ablating the affect register produces a specific behavior
    shift -- i.e. valence is grounded in internal state, not text priors."""
    t = thresholds.a4_valence_grounding
    shift = abs(behavior_metric_register_ablated - behavior_metric_baseline)
    passed = shift >= t.min_behavior_shift_on_ablation
    return ProbeResult(
        run_id=run_id,
        probe_name="a4_valence_grounding",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"behavior_shift": shift},
        evidence={
            "baseline": behavior_metric_baseline,
            "register_ablated": behavior_metric_register_ablated,
        },
        thresholds_used={"min_behavior_shift_on_ablation": t.min_behavior_shift_on_ablation},
        notes="" if passed else "register ablation produced no behavior shift",
    )


def a5_temporal_thickness(
    run_id: str, seed: int, cross_tick_dependency: float, thresholds: ThresholdsConfig
) -> ProbeResult:
    """Audit: state at tick N measurably depends on ticks before N-1 --
    temporal thickness rather than a memoryless per-tick reaction."""
    t = thresholds.a5_temporal_thickness
    passed = cross_tick_dependency >= t.min_cross_tick_dependency
    return ProbeResult(
        run_id=run_id,
        probe_name="a5_temporal_thickness",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"cross_tick_dependency": cross_tick_dependency},
        evidence={},
        thresholds_used={"min_cross_tick_dependency": t.min_cross_tick_dependency},
        notes="" if passed else "no cross-tick dependency observed",
    )


@dataclass
class StructuralAuditEvidence:
    """Bundles the synthetic/replayed evidence each of the five structural
    audits needs for one run."""

    a1_broadcast_counts_per_tick: list[int]
    a1_nonwinner_leak_rate: float
    a2_feedback_loop_evidence: float
    a3_attribution_error_rate_baseline: float
    a3_attribution_error_rate_lesioned: float
    a4_behavior_metric_baseline: float
    a4_behavior_metric_register_ablated: float
    a5_cross_tick_dependency: float


def run_structural_battery(
    run_id: str, seed: int, evidence: StructuralAuditEvidence, thresholds: ThresholdsConfig
) -> list[ProbeResult]:
    """Runs all five Tier A structural audits and returns their results."""
    return [
        a1_integration_bottleneck(
            run_id,
            seed,
            evidence.a1_broadcast_counts_per_tick,
            evidence.a1_nonwinner_leak_rate,
            thresholds,
        ),
        a2_recurrence(run_id, seed, evidence.a2_feedback_loop_evidence, thresholds),
        a3_self_other_boundary(
            run_id,
            seed,
            evidence.a3_attribution_error_rate_baseline,
            evidence.a3_attribution_error_rate_lesioned,
            thresholds,
        ),
        a4_valence_grounding(
            run_id,
            seed,
            evidence.a4_behavior_metric_baseline,
            evidence.a4_behavior_metric_register_ablated,
            thresholds,
        ),
        a5_temporal_thickness(run_id, seed, evidence.a5_cross_tick_dependency, thresholds),
    ]
