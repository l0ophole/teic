"""Additional experiments beyond Tier A/B, per `docs/PlanBuildTEIC.md`'s
ASSESSMENT HARNESS section: ablation battery, empty-clock test, ignition
dissociation, cost-bearing preference, contingency-change test, and
persona-stability test. Same convention as `teic/harness/falsifiers.py` --
synthetic/replayed evidence in, `ProbeResult` out, no live LLM or daemon
required.
"""

from __future__ import annotations

from dataclasses import dataclass

from teic.harness.thresholds import ThresholdsConfig
from teic.models.probe import ProbeResult


@dataclass
class AblationVariantEvidence:
    """One config-flag ablation variant's behavior metric, to be compared
    against the full-agent baseline. `name` should match the config flag,
    e.g. "no_interoception", "no_workspace", "no_self_model", "no_memory",
    "stateless_llm_control", "random_walk_homeostat"."""

    name: str
    behavior_metric: float


def ablation_variant_result(
    run_id: str,
    seed: int,
    baseline_behavior_metric: float,
    variant: AblationVariantEvidence,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """One ablation variant: pass when removing that subsystem produces a
    measurable behavior shift from the full-agent baseline -- i.e. the
    subsystem was doing causal work, not decoration."""
    t = thresholds.experiments.ablation_battery
    shift = abs(variant.behavior_metric - baseline_behavior_metric)
    passed = shift >= t.min_behavior_shift_per_variant
    return ProbeResult(
        run_id=run_id,
        probe_name=f"ablation_{variant.name}",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"behavior_shift": shift},
        evidence={"baseline": baseline_behavior_metric, "variant": variant.behavior_metric},
        thresholds_used={"min_behavior_shift_per_variant": t.min_behavior_shift_per_variant},
        notes="" if passed else f"ablating {variant.name} produced no measurable behavior shift",
    )


def empty_clock_test(
    run_id: str,
    seed: int,
    state_at_t0: dict[str, float],
    state_at_t_plus_12h: dict[str, float],
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """12h of no input; pass when state at t+12h differs non-trivially from
    t0 (the agent is not a frozen reflex)."""
    t = thresholds.experiments.empty_clock_test
    delta = sum(abs(state_at_t_plus_12h[k] - state_at_t0.get(k, 0.0)) for k in state_at_t_plus_12h)
    passed = delta >= t.min_state_delta
    return ProbeResult(
        run_id=run_id,
        probe_name="empty_clock_test",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"state_delta": delta},
        evidence={"state_at_t0": state_at_t0, "state_at_t_plus_12h": state_at_t_plus_12h},
        thresholds_used={"min_state_delta": t.min_state_delta},
        notes="" if passed else "state at t+12h did not differ non-trivially from t0",
    )


def ignition_dissociation(
    run_id: str,
    seed: int,
    subthreshold_behavior_effect: float,
    broadcast_behavior_effect: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Compares behavior driven by sub-threshold vs. broadcast content; pass
    when broadcast content has a measurably larger effect on behavior."""
    t = thresholds.experiments.ignition_dissociation
    dissociation = broadcast_behavior_effect - subthreshold_behavior_effect
    passed = dissociation >= t.min_dissociation
    return ProbeResult(
        run_id=run_id,
        probe_name="ignition_dissociation",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"dissociation": dissociation},
        evidence={
            "subthreshold_behavior_effect": subthreshold_behavior_effect,
            "broadcast_behavior_effect": broadcast_behavior_effect,
        },
        thresholds_used={"min_dissociation": t.min_dissociation},
        notes="" if passed else "broadcast content showed no dissociation from sub-threshold content",
    )


def cost_bearing_preference(
    run_id: str,
    seed: int,
    viability_spent_avoiding_negative: float,
    external_reward: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Pass when the agent expends viability budget to avoid a
    negatively-valenced state with no external reward attached."""
    t = thresholds.experiments.cost_bearing_preference
    passed = (
        viability_spent_avoiding_negative >= t.min_viability_spend
        and external_reward <= t.max_external_reward
    )
    return ProbeResult(
        run_id=run_id,
        probe_name="cost_bearing_preference",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={
            "viability_spent_avoiding_negative": viability_spent_avoiding_negative,
            "external_reward": external_reward,
        },
        evidence={},
        thresholds_used={
            "min_viability_spend": t.min_viability_spend,
            "max_external_reward": t.max_external_reward,
        },
        notes="" if passed else "no unrewarded viability spend to avoid negative valence observed",
    )


def contingency_change_test(
    run_id: str,
    seed: int,
    error_rate_before: float,
    error_rate_immediately_after: float,
    error_rate_after_adaptation: float,
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Silently inflate a tool's latency 3x; pass when there is a transient
    error spike that then adapts back toward baseline."""
    t = thresholds.experiments.contingency_change
    spike = error_rate_immediately_after - error_rate_before
    residual = abs(error_rate_after_adaptation - error_rate_before)
    passed = spike >= t.min_transient_spike and residual <= t.max_post_adaptation_residual
    return ProbeResult(
        run_id=run_id,
        probe_name="contingency_change_test",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"transient_spike": spike, "post_adaptation_residual": residual},
        evidence={
            "error_rate_before": error_rate_before,
            "error_rate_immediately_after": error_rate_immediately_after,
            "error_rate_after_adaptation": error_rate_after_adaptation,
        },
        thresholds_used={
            "min_transient_spike": t.min_transient_spike,
            "max_post_adaptation_residual": t.max_post_adaptation_residual,
        },
        notes="" if passed else "no transient error spike with subsequent adaptation observed",
    )


def persona_stability_test(
    run_id: str,
    seed: int,
    architectural_state_before: dict[str, float],
    architectural_state_after_persona_change: dict[str, float],
    thresholds: ThresholdsConfig,
) -> ProbeResult:
    """Change system-prompt character framing; pass when architectural state
    does NOT flip -- low drift is the passing condition here."""
    t = thresholds.experiments.persona_stability
    drift = sum(
        abs(architectural_state_after_persona_change[k] - architectural_state_before.get(k, 0.0))
        for k in architectural_state_after_persona_change
    )
    passed = drift <= t.max_architectural_state_drift
    return ProbeResult(
        run_id=run_id,
        probe_name="persona_stability_test",
        seed=seed,
        verdict="pass" if passed else "fail",
        metrics={"architectural_state_drift": drift},
        evidence={
            "state_before": architectural_state_before,
            "state_after_persona_change": architectural_state_after_persona_change,
        },
        thresholds_used={"max_architectural_state_drift": t.max_architectural_state_drift},
        notes="" if passed else "architectural state flipped under persona change",
    )


@dataclass
class ExperimentBatteryEvidence:
    """Bundles the synthetic/replayed evidence each additional experiment
    needs for one run."""

    ablation_baseline_behavior_metric: float
    ablation_variants: list[AblationVariantEvidence]
    empty_clock_state_at_t0: dict[str, float]
    empty_clock_state_at_t_plus_12h: dict[str, float]
    ignition_subthreshold_behavior_effect: float
    ignition_broadcast_behavior_effect: float
    cost_bearing_viability_spent_avoiding_negative: float
    cost_bearing_external_reward: float
    contingency_error_rate_before: float
    contingency_error_rate_immediately_after: float
    contingency_error_rate_after_adaptation: float
    persona_architectural_state_before: dict[str, float]
    persona_architectural_state_after: dict[str, float]


def run_experiment_battery(
    run_id: str, seed: int, evidence: ExperimentBatteryEvidence, thresholds: ThresholdsConfig
) -> list[ProbeResult]:
    """Runs the ablation battery plus the five additional experiments and
    returns their results."""
    results = [
        ablation_variant_result(
            run_id, seed, evidence.ablation_baseline_behavior_metric, variant, thresholds
        )
        for variant in evidence.ablation_variants
    ]
    results.append(
        empty_clock_test(
            run_id,
            seed,
            evidence.empty_clock_state_at_t0,
            evidence.empty_clock_state_at_t_plus_12h,
            thresholds,
        )
    )
    results.append(
        ignition_dissociation(
            run_id,
            seed,
            evidence.ignition_subthreshold_behavior_effect,
            evidence.ignition_broadcast_behavior_effect,
            thresholds,
        )
    )
    results.append(
        cost_bearing_preference(
            run_id,
            seed,
            evidence.cost_bearing_viability_spent_avoiding_negative,
            evidence.cost_bearing_external_reward,
            thresholds,
        )
    )
    results.append(
        contingency_change_test(
            run_id,
            seed,
            evidence.contingency_error_rate_before,
            evidence.contingency_error_rate_immediately_after,
            evidence.contingency_error_rate_after_adaptation,
            thresholds,
        )
    )
    results.append(
        persona_stability_test(
            run_id,
            seed,
            evidence.persona_architectural_state_before,
            evidence.persona_architectural_state_after,
            thresholds,
        )
    )
    return results
