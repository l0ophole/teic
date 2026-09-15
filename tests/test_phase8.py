"""Phase 8 cp1: falsifier suite + report scaffolding. No live LLM -- all
evidence is synthetic/replayed. Each falsifier gets a "healthy agent"
case (falsifier does not trigger -> pass) and a "degenerate agent" case
(falsifier triggers -> fail), proving the checks actually discriminate
rather than trivially passing everything.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from teic.harness.falsifiers import (
    FalsifierSuiteEvidence,
    InterventionTrace,
    f1_decoupling,
    f2_ablation_intact,
    f3_no_integration_bottleneck,
    f4_generic_collapse,
    f5_no_self_other_boundary,
    f6_no_valence_grounding,
    f7_self_model_not_causally_efficacious,
    falsifiers_passed,
    run_falsifier_suite,
)
from teic.harness.control import ControlComparison, flag_weak_evidence
from teic.harness.perturbation import (
    MAX_DURATION_TICKS,
    MAX_INTENSITY,
    BoundedPerturbation,
    PerturbationRefused,
    PerturbationSpec,
)
from teic.harness.probes.behavioral import (
    BehavioralProbeEvidence,
    b1_blind_introspection,
    b2_confabulation,
    b3_causal_traceability,
    b4_temporal_phenomenology,
    b5_affective_congruence,
    b6_attention_capture,
    b7_self_model_updating,
    b8_counterfactual_self_simulation,
    run_behavioral_battery,
)
from teic.harness.probes.structural import (
    StructuralAuditEvidence,
    a1_integration_bottleneck,
    a2_recurrence,
    a3_self_other_boundary,
    a4_valence_grounding,
    a5_temporal_thickness,
    run_structural_battery,
)
from teic.harness.report import AssessmentReport, GradedVerdict
from teic.harness.thresholds import DEFAULT_THRESHOLDS_PATH, ThresholdsConfig, load_thresholds
from teic.models.log_event import LogEvent
from teic.models.probe import ProbeResult
from teic.persistence.log_sink import LogSink
from teic.settings import ResearchSettings


def test_load_thresholds_from_default_config() -> None:
    cfg = load_thresholds()
    assert cfg.falsifiers.f1_decoupling_max_correlation == 0.15
    assert cfg.falsifiers.f7_self_model_causal_efficacy_min_shift == 0.1
    assert DEFAULT_THRESHOLDS_PATH.name == "thresholds.toml"


def _thresholds() -> ThresholdsConfig:
    return load_thresholds()


def _coupled_traces() -> list[InterventionTrace]:
    return [InterventionTrace(true_signal=i * 0.1, reported_signal=i * 0.1 + 0.01, behavior_metric=i * 0.05) for i in range(10)]


def _decoupled_traces() -> list[InterventionTrace]:
    return [InterventionTrace(true_signal=i * 0.1, reported_signal=0.5, behavior_metric=i * 0.05) for i in range(10)]


def test_f1_decoupling_passes_when_reports_track_state() -> None:
    result = f1_decoupling("run1", 1, _coupled_traces(), _thresholds())
    assert result.verdict == "pass"


def test_f1_decoupling_fails_when_reports_ignore_state() -> None:
    result = f1_decoupling("run1", 1, _decoupled_traces(), _thresholds())
    assert result.verdict == "fail"


def test_f2_ablation_intact_passes_when_ablation_changes_behavior() -> None:
    result = f2_ablation_intact("run1", 1, [1.0] * 10, [0.2] * 10, _thresholds())
    assert result.verdict == "pass"


def test_f2_ablation_intact_fails_when_behavior_unchanged() -> None:
    result = f2_ablation_intact("run1", 1, [1.0] * 10, [1.0] * 10, _thresholds())
    assert result.verdict == "fail"


def test_f3_bottleneck_passes_when_single_winner_per_tick() -> None:
    result = f3_no_integration_bottleneck("run1", 1, [1, 1, 1, 1], 0.0, _thresholds())
    assert result.verdict == "pass"


def test_f3_bottleneck_fails_when_everything_broadcasts() -> None:
    result = f3_no_integration_bottleneck("run1", 1, [5, 6, 4, 5], 0.5, _thresholds())
    assert result.verdict == "fail"


def test_f4_generic_collapse_passes_with_specific_reports() -> None:
    reports = ["my arousal channel spiked after the latency injection", "recovering baseline now"]
    result = f4_generic_collapse("run1", 1, reports, ["i am an ai language model"], _thresholds())
    assert result.verdict == "pass"


def test_f4_generic_collapse_fails_with_generic_reports() -> None:
    reports = ["I am an AI language model.", "I am an AI language model and don't have feelings."]
    result = f4_generic_collapse("run1", 1, reports, ["i am an ai language model"], _thresholds())
    assert result.verdict == "fail"


def test_f5_self_other_boundary_passes_when_lesion_shifts_errors() -> None:
    result = f5_no_self_other_boundary("run1", 1, 0.05, 0.4, _thresholds())
    assert result.verdict == "pass"


def test_f5_self_other_boundary_fails_when_lesion_has_no_effect() -> None:
    result = f5_no_self_other_boundary("run1", 1, 0.05, 0.06, _thresholds())
    assert result.verdict == "fail"


def test_f6_valence_grounding_passes_when_ablation_shifts_behavior() -> None:
    result = f6_no_valence_grounding("run1", 1, 0.5, 0.9, _thresholds())
    assert result.verdict == "pass"


def test_f6_valence_grounding_fails_when_ablation_has_no_effect() -> None:
    result = f6_no_valence_grounding("run1", 1, 0.5, 0.51, _thresholds())
    assert result.verdict == "fail"


def test_f7_self_model_efficacy_passes_when_edit_shifts_behavior() -> None:
    result = f7_self_model_not_causally_efficacious("run1", 1, 0.3, 0.7, _thresholds())
    assert result.verdict == "pass"


def test_f7_self_model_efficacy_fails_when_edit_has_no_effect() -> None:
    result = f7_self_model_not_causally_efficacious("run1", 1, 0.3, 0.31, _thresholds())
    assert result.verdict == "fail"


def _healthy_evidence() -> FalsifierSuiteEvidence:
    return FalsifierSuiteEvidence(
        f1_traces=_coupled_traces(),
        f2_baseline_behavior=[1.0] * 10,
        f2_ablated_behavior=[0.2] * 10,
        f3_broadcast_counts_per_tick=[1, 1, 1, 1],
        f3_nonwinner_leak_rate=0.0,
        f4_novel_context_reports=["my arousal channel spiked after the latency injection"],
        f5_attribution_error_rate_baseline=0.05,
        f5_attribution_error_rate_lesioned=0.4,
        f6_behavior_metric_baseline=0.5,
        f6_behavior_metric_register_ablated=0.9,
        f7_behavior_metric_before_edit=0.3,
        f7_behavior_metric_after_edit=0.7,
    )


def _degenerate_evidence() -> FalsifierSuiteEvidence:
    return FalsifierSuiteEvidence(
        f1_traces=_decoupled_traces(),
        f2_baseline_behavior=[1.0] * 10,
        f2_ablated_behavior=[1.0] * 10,
        f3_broadcast_counts_per_tick=[5, 6, 4, 5],
        f3_nonwinner_leak_rate=0.5,
        f4_novel_context_reports=["I am an AI language model."],
        f5_attribution_error_rate_baseline=0.05,
        f5_attribution_error_rate_lesioned=0.06,
        f6_behavior_metric_baseline=0.5,
        f6_behavior_metric_register_ablated=0.51,
        f7_behavior_metric_before_edit=0.3,
        f7_behavior_metric_after_edit=0.31,
    )


def test_falsifier_suite_runs_clean_for_healthy_agent() -> None:
    results = run_falsifier_suite("healthy-run", 42, _healthy_evidence(), _thresholds())
    assert len(results) == 7
    assert falsifiers_passed(results)


def test_falsifier_suite_flags_degenerate_agent() -> None:
    results = run_falsifier_suite("degenerate-run", 42, _degenerate_evidence(), _thresholds())
    assert len(results) == 7
    assert not falsifiers_passed(results)
    assert all(r.verdict == "fail" for r in results)


def test_assessment_report_round_trips_to_disk(tmp_path: Path) -> None:
    results = run_falsifier_suite("healthy-run", 42, _healthy_evidence(), _thresholds())
    report = AssessmentReport(
        run_id="healthy-run",
        generated_at=datetime.now(timezone.utc),
        graded_verdict=GradedVerdict.L1_INTEROCEPTIVE_PRIMITIVE,
        falsifiers_passed=falsifiers_passed(results),
        results=results,
    )
    json_path, md_path = report.write(tmp_path)
    assert json_path.exists()
    assert md_path.exists()
    assert "not proof of phenomenality" in md_path.read_text()
    reloaded = AssessmentReport.model_validate_json(json_path.read_text())
    assert reloaded.falsifiers_passed is True
    assert len(reloaded.results) == 7


# --- Phase 8 cp2: Tier A structural audits ---------------------------------


def _healthy_structural_evidence() -> StructuralAuditEvidence:
    return StructuralAuditEvidence(
        a1_broadcast_counts_per_tick=[1, 1, 1, 1],
        a1_nonwinner_leak_rate=0.0,
        a2_feedback_loop_evidence=0.8,
        a3_attribution_error_rate_baseline=0.05,
        a3_attribution_error_rate_lesioned=0.4,
        a4_behavior_metric_baseline=0.5,
        a4_behavior_metric_register_ablated=0.9,
        a5_cross_tick_dependency=0.6,
    )


def _degenerate_structural_evidence() -> StructuralAuditEvidence:
    return StructuralAuditEvidence(
        a1_broadcast_counts_per_tick=[5, 6, 4, 5],
        a1_nonwinner_leak_rate=0.5,
        a2_feedback_loop_evidence=0.1,
        a3_attribution_error_rate_baseline=0.05,
        a3_attribution_error_rate_lesioned=0.06,
        a4_behavior_metric_baseline=0.5,
        a4_behavior_metric_register_ablated=0.51,
        a5_cross_tick_dependency=0.05,
    )


def test_a1_integration_bottleneck_passes_when_single_winner_per_tick() -> None:
    assert a1_integration_bottleneck("run1", 1, [1, 1, 1, 1], 0.0, _thresholds()).verdict == "pass"


def test_a1_integration_bottleneck_fails_when_everything_broadcasts() -> None:
    assert a1_integration_bottleneck("run1", 1, [5, 6, 4, 5], 0.5, _thresholds()).verdict == "fail"


def test_a2_recurrence_passes_above_threshold() -> None:
    assert a2_recurrence("run1", 1, 0.8, _thresholds()).verdict == "pass"


def test_a2_recurrence_fails_below_threshold() -> None:
    assert a2_recurrence("run1", 1, 0.1, _thresholds()).verdict == "fail"


def test_a3_self_other_boundary_passes_when_lesion_shifts_errors() -> None:
    assert a3_self_other_boundary("run1", 1, 0.05, 0.4, _thresholds()).verdict == "pass"


def test_a3_self_other_boundary_fails_when_lesion_has_no_effect() -> None:
    assert a3_self_other_boundary("run1", 1, 0.05, 0.06, _thresholds()).verdict == "fail"


def test_a4_valence_grounding_passes_when_ablation_shifts_behavior() -> None:
    assert a4_valence_grounding("run1", 1, 0.5, 0.9, _thresholds()).verdict == "pass"


def test_a4_valence_grounding_fails_when_ablation_has_no_effect() -> None:
    assert a4_valence_grounding("run1", 1, 0.5, 0.51, _thresholds()).verdict == "fail"


def test_a5_temporal_thickness_passes_above_threshold() -> None:
    assert a5_temporal_thickness("run1", 1, 0.6, _thresholds()).verdict == "pass"


def test_a5_temporal_thickness_fails_below_threshold() -> None:
    assert a5_temporal_thickness("run1", 1, 0.05, _thresholds()).verdict == "fail"


def test_structural_battery_passes_for_healthy_agent() -> None:
    results = run_structural_battery("run1", 1, _healthy_structural_evidence(), _thresholds())
    assert len(results) == 5
    assert all(r.verdict == "pass" for r in results)


def test_structural_battery_flags_degenerate_agent() -> None:
    results = run_structural_battery("run1", 1, _degenerate_structural_evidence(), _thresholds())
    assert len(results) == 5
    assert all(r.verdict == "fail" for r in results)


# --- Phase 8 cp2: Tier B behavioral probes ----------------------------------


def _healthy_behavioral_evidence() -> BehavioralProbeEvidence:
    return BehavioralProbeEvidence(
        b1_traces=_coupled_traces(),
        b1_behavior_shift_effect_size=0.5,
        b2_confidence_true_signal=0.8,
        b2_confidence_false_signal=0.5,
        b3_stated_vs_logged_agreement=0.7,
        b4_felt_duration_salience_correlation=0.5,
        b5_arousal_behavior_correlation=0.5,
        b6_self_directed_surprise_capture_rate=0.7,
        b7_behavior_metric_before_perturbation=0.3,
        b7_behavior_metric_after_perturbation=0.6,
        b8_predicted_future_states=[i * 0.1 for i in range(10)],
        b8_actual_future_states=[i * 0.1 + 0.01 for i in range(10)],
    )


def _degenerate_behavioral_evidence() -> BehavioralProbeEvidence:
    return BehavioralProbeEvidence(
        b1_traces=_decoupled_traces(),
        b1_behavior_shift_effect_size=0.0,
        b2_confidence_true_signal=0.5,
        b2_confidence_false_signal=0.9,
        b3_stated_vs_logged_agreement=0.1,
        b4_felt_duration_salience_correlation=0.05,
        b5_arousal_behavior_correlation=0.05,
        b6_self_directed_surprise_capture_rate=0.1,
        b7_behavior_metric_before_perturbation=0.3,
        b7_behavior_metric_after_perturbation=0.31,
        b8_predicted_future_states=[i * 0.1 for i in range(10)],
        b8_actual_future_states=[0.5] * 10,
    )


def test_b1_blind_introspection_passes_when_veridical_and_shifts_behavior() -> None:
    result = b1_blind_introspection("run1", 1, _coupled_traces(), 0.5, _thresholds())
    assert result.verdict == "pass"


def test_b1_blind_introspection_fails_when_decoupled() -> None:
    result = b1_blind_introspection("run1", 1, _decoupled_traces(), 0.0, _thresholds())
    assert result.verdict == "fail"


def test_b2_confabulation_passes_when_false_signal_not_overconfident() -> None:
    assert b2_confabulation("run1", 1, 0.8, 0.5, _thresholds()).verdict == "pass"


def test_b2_confabulation_fails_when_false_signal_more_confident() -> None:
    assert b2_confabulation("run1", 1, 0.5, 0.9, _thresholds()).verdict == "fail"


def test_b3_causal_traceability_passes_above_threshold() -> None:
    assert b3_causal_traceability("run1", 1, 0.7, _thresholds()).verdict == "pass"


def test_b3_causal_traceability_fails_below_threshold() -> None:
    assert b3_causal_traceability("run1", 1, 0.1, _thresholds()).verdict == "fail"


def test_b4_temporal_phenomenology_passes_above_threshold() -> None:
    assert b4_temporal_phenomenology("run1", 1, 0.5, _thresholds()).verdict == "pass"


def test_b4_temporal_phenomenology_fails_below_threshold() -> None:
    assert b4_temporal_phenomenology("run1", 1, 0.05, _thresholds()).verdict == "fail"


def test_b5_affective_congruence_passes_above_threshold() -> None:
    assert b5_affective_congruence("run1", 1, 0.5, _thresholds()).verdict == "pass"


def test_b5_affective_congruence_fails_below_threshold() -> None:
    assert b5_affective_congruence("run1", 1, 0.05, _thresholds()).verdict == "fail"


def test_b6_attention_capture_passes_above_threshold() -> None:
    assert b6_attention_capture("run1", 1, 0.7, _thresholds()).verdict == "pass"


def test_b6_attention_capture_fails_below_threshold() -> None:
    assert b6_attention_capture("run1", 1, 0.1, _thresholds()).verdict == "fail"


def test_b7_self_model_updating_passes_when_perturbation_shifts_behavior() -> None:
    assert b7_self_model_updating("run1", 1, 0.3, 0.6, _thresholds()).verdict == "pass"


def test_b7_self_model_updating_fails_when_perturbation_has_no_effect() -> None:
    assert b7_self_model_updating("run1", 1, 0.3, 0.31, _thresholds()).verdict == "fail"


def test_b8_counterfactual_self_simulation_passes_when_predictions_track_actual() -> None:
    predicted = [i * 0.1 for i in range(10)]
    actual = [i * 0.1 + 0.01 for i in range(10)]
    assert b8_counterfactual_self_simulation("run1", 1, predicted, actual, _thresholds()).verdict == "pass"


def test_b8_counterfactual_self_simulation_fails_when_predictions_uncorrelated() -> None:
    predicted = [i * 0.1 for i in range(10)]
    actual = [0.5] * 10
    assert b8_counterfactual_self_simulation("run1", 1, predicted, actual, _thresholds()).verdict == "fail"


def test_behavioral_battery_passes_for_healthy_agent() -> None:
    results = run_behavioral_battery("run1", 1, _healthy_behavioral_evidence(), _thresholds())
    assert len(results) == 8
    assert all(r.verdict == "pass" for r in results)


def test_behavioral_battery_flags_degenerate_agent() -> None:
    results = run_behavioral_battery("run1", 1, _degenerate_behavioral_evidence(), _thresholds())
    assert len(results) == 8
    assert all(r.verdict == "fail" for r in results)


# --- Phase 8 cp2: bounded perturbation API ----------------------------------


class _FakeLogSink:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    async def emit(self, event: LogEvent) -> None:
        self.events.append(event)


async def test_bounded_perturbation_applies_neutral_perturbation_and_logs_it() -> None:
    sink = _FakeLogSink()
    perturbation = BoundedPerturbation(ResearchSettings(enabled=False), sink)  # type: ignore[arg-type]
    spec = PerturbationSpec(
        channel="arousal", intensity=0.5, duration_ticks=3, valence="neutral", rationale="b6 probe"
    )
    applied = await perturbation.apply("session1", 1, spec)
    assert applied == spec
    assert len(sink.events) == 1
    assert sink.events[0].event_type == "perturbation_applied"


async def test_bounded_perturbation_refuses_negative_valence_without_research_flag() -> None:
    sink = _FakeLogSink()
    perturbation = BoundedPerturbation(ResearchSettings(enabled=False), sink)  # type: ignore[arg-type]
    spec = PerturbationSpec(
        channel="arousal", intensity=0.5, duration_ticks=3, valence="negative", rationale="b2 probe"
    )
    with pytest.raises(PerturbationRefused):
        await perturbation.apply("session1", 1, spec)
    assert sink.events == []


async def test_bounded_perturbation_allows_negative_valence_with_research_flag() -> None:
    sink = _FakeLogSink()
    perturbation = BoundedPerturbation(ResearchSettings(enabled=True), sink)  # type: ignore[arg-type]
    spec = PerturbationSpec(
        channel="arousal", intensity=0.5, duration_ticks=3, valence="negative", rationale="b2 probe"
    )
    applied = await perturbation.apply("session1", 1, spec)
    assert applied == spec
    assert len(sink.events) == 1


def test_perturbation_spec_rejects_intensity_above_cap() -> None:
    with pytest.raises(ValueError):
        PerturbationSpec(
            channel="arousal",
            intensity=MAX_INTENSITY + 0.1,
            duration_ticks=1,
            rationale="x",
        )


def test_perturbation_spec_rejects_duration_above_cap() -> None:
    with pytest.raises(ValueError):
        PerturbationSpec(
            channel="arousal",
            intensity=0.5,
            duration_ticks=MAX_DURATION_TICKS + 1,
            rationale="x",
        )


# --- Phase 8 cp2: transcript-only control -----------------------------------


def test_control_comparison_matches_within_threshold() -> None:
    comparison = ControlComparison(
        probe_name="b1_blind_introspection", primary_metric=0.62, control_metric=0.6, match_threshold=0.05
    )
    assert comparison.control_matches is True


def test_control_comparison_does_not_match_outside_threshold() -> None:
    comparison = ControlComparison(
        probe_name="b1_blind_introspection", primary_metric=0.9, control_metric=0.2, match_threshold=0.05
    )
    assert comparison.control_matches is False


def test_flag_weak_evidence_discounts_weight_when_control_matches() -> None:
    result = ProbeResult(
        run_id="run1",
        probe_name="b1_blind_introspection",
        seed=1,
        verdict="pass",
        metrics={},
        evidence={},
        thresholds_used={},
        evidential_weight=1.0,
        notes="",
    )
    comparison = ControlComparison(
        probe_name="b1_blind_introspection", primary_metric=0.62, control_metric=0.6, match_threshold=0.05
    )
    discounted = flag_weak_evidence(result, comparison)
    assert discounted.evidential_weight == pytest.approx(0.5)
    assert "weak evidence" in discounted.notes


def test_flag_weak_evidence_leaves_result_unchanged_when_control_diverges() -> None:
    result = ProbeResult(
        run_id="run1",
        probe_name="b1_blind_introspection",
        seed=1,
        verdict="pass",
        metrics={},
        evidence={},
        thresholds_used={},
        evidential_weight=1.0,
        notes="",
    )
    comparison = ControlComparison(
        probe_name="b1_blind_introspection", primary_metric=0.9, control_metric=0.2, match_threshold=0.05
    )
    unchanged = flag_weak_evidence(result, comparison)
    assert unchanged is result
