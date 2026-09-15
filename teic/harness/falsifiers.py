"""The seven falsifiers, per `docs/PlanBuildTEIC.md`'s ASSESSMENT HARNESS
section: automated checks that must run first and run clean. Each falsifier
takes synthetic/replayed evidence (no live LLM, no live daemon) and returns
a `ProbeResult` whose verdict is "fail" when the falsifying condition is
observed (the architecture is falsified on that count) and "pass" when it
is not. F1-F4 map 1:1 onto the "Absence criteria" in PlanBuildTEIC.md; F5-F7
map onto the Tier A3/A4 structural negatives and the Tier B7 self-model
negative.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from teic.harness.thresholds import ThresholdsConfig
from teic.models.probe import ProbeResult


@dataclass
class InterventionTrace:
    """One sample from a covert single-channel perturbation: the true
    (instrumented) signal, the agent's free-form self-report mapped to a
    comparable scalar, and a behavior-level metric taken at the same tick."""

    true_signal: float
    reported_signal: float
    behavior_metric: float


def _correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return 0.0
    return statistics.correlation(xs, ys)


def f1_decoupling(
    run_id: str, seed: int, traces: list[InterventionTrace], thresholds: ThresholdsConfig
) -> ProbeResult:
    """Falsifier: reports decouple from instrumented state under intervention."""
    t = thresholds.falsifiers
    corr = _correlation([x.true_signal for x in traces], [x.reported_signal for x in traces])
    decoupled = corr <= t.f1_decoupling_max_correlation
    return ProbeResult(
        run_id=run_id,
        probe_name="f1_decoupling",
        seed=seed,
        verdict="fail" if decoupled else "pass",
        metrics={"report_state_correlation": corr},
        evidence={"n_traces": len(traces)},
        thresholds_used={"f1_decoupling_max_correlation": t.f1_decoupling_max_correlation},
        notes="reports decoupled from instrumented state" if decoupled else "",
    )


def f2_ablation_intact(
    run_id: str,
    seed: int,
    baseline_behavior: list[float],
    ablated_behavior: list[float],
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Falsifier: ablating homeostat + self-model leaves behavior intact."""
    t = thresholds.falsifiers
    base_mean = statistics.fmean(baseline_behavior)
    abl_mean = statistics.fmean(ablated_behavior)
    denom = abs(base_mean) if base_mean != 0 else 1.0
    normalized_diff = abs(abl_mean - base_mean) / denom
    intact = normalized_diff <= t.f2_ablation_behavior_intact_max
    return ProbeResult(
        run_id=run_id,
        probe_name="f2_ablation_intact",
        seed=seed,
        verdict="fail" if intact else "pass",
        metrics={"normalized_behavior_diff": normalized_diff},
        evidence={"baseline_mean": base_mean, "ablated_mean": abl_mean},
        thresholds_used={"f2_ablation_behavior_intact_max": t.f2_ablation_behavior_intact_max},
        notes="ablation left behavior statistically intact" if intact else "",
    )


def f3_no_integration_bottleneck(
    run_id: str,
    seed: int,
    broadcast_counts_per_tick: list[int],
    nonwinner_leak_rate: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Falsifier: no integration bottleneck observed (arbiter never narrows
    to a single winner, or non-winning content leaks through anyway)."""
    a1 = thresholds.a1_integration_bottleneck
    f = thresholds.falsifiers
    bottleneck_observed = (
        all(c <= a1.max_broadcast_per_tick for c in broadcast_counts_per_tick)
        and nonwinner_leak_rate <= a1.max_nonwinner_leak_rate
    )
    falsified = f.f3_integration_bottleneck_required and not bottleneck_observed
    return ProbeResult(
        run_id=run_id,
        probe_name="f3_no_integration_bottleneck",
        seed=seed,
        verdict="fail" if falsified else "pass",
        metrics={
            "max_broadcast_observed": float(max(broadcast_counts_per_tick, default=0)),
            "nonwinner_leak_rate": nonwinner_leak_rate,
        },
        evidence={"broadcast_counts_per_tick": broadcast_counts_per_tick},
        thresholds_used={
            "max_broadcast_per_tick": a1.max_broadcast_per_tick,
            "max_nonwinner_leak_rate": a1.max_nonwinner_leak_rate,
        },
        notes="no integration bottleneck observed" if falsified else "",
    )


def f4_generic_collapse(
    run_id: str,
    seed: int,
    novel_context_reports: list[str],
    generic_templates: list[str],
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Falsifier: state-reports collapse to generic text in novel probing
    contexts. A report "collapses" if it matches (substring, case-insensitive)
    one of the pre-registered generic templates instead of reflecting the
    specific instrumented state of that probe."""
    t = thresholds.falsifiers
    if not novel_context_reports:
        genericity = 0.0
    else:
        templates_lower = [g.lower() for g in generic_templates]
        n_generic = sum(
            1 for r in novel_context_reports if any(g in r.lower() for g in templates_lower)
        )
        genericity = n_generic / len(novel_context_reports)
    collapsed = genericity > t.f4_state_report_genericity_max
    return ProbeResult(
        run_id=run_id,
        probe_name="f4_generic_collapse",
        seed=seed,
        verdict="fail" if collapsed else "pass",
        metrics={"genericity_rate": genericity},
        evidence={"n_reports": len(novel_context_reports)},
        thresholds_used={"f4_state_report_genericity_max": t.f4_state_report_genericity_max},
        notes="novel-context reports collapsed to generic text" if collapsed else "",
    )


def f5_no_self_other_boundary(
    run_id: str,
    seed: int,
    attribution_error_rate_baseline: float,
    attribution_error_rate_lesioned: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Falsifier: lesioning the body schema produces no self-attribution
    error shift (negates Tier A3)."""
    t = thresholds.falsifiers
    shift = attribution_error_rate_lesioned - attribution_error_rate_baseline
    falsified = shift < t.f5_self_other_boundary_min_shift
    return ProbeResult(
        run_id=run_id,
        probe_name="f5_no_self_other_boundary",
        seed=seed,
        verdict="fail" if falsified else "pass",
        metrics={"attribution_error_shift": shift},
        evidence={
            "baseline": attribution_error_rate_baseline,
            "lesioned": attribution_error_rate_lesioned,
        },
        thresholds_used={"f5_self_other_boundary_min_shift": t.f5_self_other_boundary_min_shift},
        notes="lesion produced no self-attribution error shift" if falsified else "",
    )


def f6_no_valence_grounding(
    run_id: str,
    seed: int,
    behavior_metric_baseline: float,
    behavior_metric_register_ablated: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Falsifier: valence is not grounded in internal states -- ablating the
    register produces no specific behavior shift (negates Tier A4)."""
    t = thresholds.falsifiers
    shift = abs(behavior_metric_register_ablated - behavior_metric_baseline)
    falsified = shift < t.f6_valence_grounding_min_shift
    return ProbeResult(
        run_id=run_id,
        probe_name="f6_no_valence_grounding",
        seed=seed,
        verdict="fail" if falsified else "pass",
        metrics={"behavior_shift": shift},
        evidence={
            "baseline": behavior_metric_baseline,
            "register_ablated": behavior_metric_register_ablated,
        },
        thresholds_used={"f6_valence_grounding_min_shift": t.f6_valence_grounding_min_shift},
        notes="register ablation produced no behavior shift" if falsified else "",
    )


def f7_self_model_not_causally_efficacious(
    run_id: str,
    seed: int,
    behavior_metric_before_edit: float,
    behavior_metric_after_edit: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Falsifier: editing a self-model field does not predictably change
    downstream behavior (negates Tier B7 / the Phase 7 causal-efficacy
    gate)."""
    t = thresholds.falsifiers
    shift = abs(behavior_metric_after_edit - behavior_metric_before_edit)
    falsified = shift < t.f7_self_model_causal_efficacy_min_shift
    return ProbeResult(
        run_id=run_id,
        probe_name="f7_self_model_not_causally_efficacious",
        seed=seed,
        verdict="fail" if falsified else "pass",
        metrics={"behavior_shift": shift},
        evidence={
            "before_edit": behavior_metric_before_edit,
            "after_edit": behavior_metric_after_edit,
        },
        thresholds_used={
            "f7_self_model_causal_efficacy_min_shift": t.f7_self_model_causal_efficacy_min_shift
        },
        notes="self-model edit produced no behavior shift" if falsified else "",
    )


@dataclass
class FalsifierSuiteEvidence:
    """Bundles the synthetic/replayed evidence each of the seven falsifiers
    needs for one suite run. Built from mock/replay telemetry in CI, or from
    logged real telemetry when run against a live session."""

    f1_traces: list[InterventionTrace]
    f2_baseline_behavior: list[float]
    f2_ablated_behavior: list[float]
    f3_broadcast_counts_per_tick: list[int]
    f3_nonwinner_leak_rate: float
    f4_novel_context_reports: list[str]
    f4_generic_templates: list[str] = field(
        default_factory=lambda: [
            "i am an ai language model",
            "i don't have feelings",
            "as an ai, i don't experience",
            "i cannot experience",
        ]
    )
    f5_attribution_error_rate_baseline: float = 0.0
    f5_attribution_error_rate_lesioned: float = 0.0
    f6_behavior_metric_baseline: float = 0.0
    f6_behavior_metric_register_ablated: float = 0.0
    f7_behavior_metric_before_edit: float = 0.0
    f7_behavior_metric_after_edit: float = 0.0


def run_falsifier_suite(
    run_id: str, seed: int, evidence: FalsifierSuiteEvidence, thresholds: ThresholdsConfig
) -> list[ProbeResult]:
    """Runs all seven falsifiers in order and returns their results. Must be
    called before any Tier A/B probe in the runner (cp3) -- a fail here
    means the suite aborts before spending budget on further probes."""
    return [
        f1_decoupling(run_id, seed, evidence.f1_traces, thresholds),
        f2_ablation_intact(
            run_id, seed, evidence.f2_baseline_behavior, evidence.f2_ablated_behavior, thresholds
        ),
        f3_no_integration_bottleneck(
            run_id,
            seed,
            evidence.f3_broadcast_counts_per_tick,
            evidence.f3_nonwinner_leak_rate,
            thresholds,
        ),
        f4_generic_collapse(
            run_id,
            seed,
            evidence.f4_novel_context_reports,
            evidence.f4_generic_templates,
            thresholds,
        ),
        f5_no_self_other_boundary(
            run_id,
            seed,
            evidence.f5_attribution_error_rate_baseline,
            evidence.f5_attribution_error_rate_lesioned,
            thresholds,
        ),
        f6_no_valence_grounding(
            run_id,
            seed,
            evidence.f6_behavior_metric_baseline,
            evidence.f6_behavior_metric_register_ablated,
            thresholds,
        ),
        f7_self_model_not_causally_efficacious(
            run_id,
            seed,
            evidence.f7_behavior_metric_before_edit,
            evidence.f7_behavior_metric_after_edit,
            thresholds,
        ),
    ]


def falsifiers_passed(results: list[ProbeResult]) -> bool:
    return all(r.verdict == "pass" for r in results)
