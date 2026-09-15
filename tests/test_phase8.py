"""Phase 8 cp1: falsifier suite + report scaffolding. No live LLM -- all
evidence is synthetic/replayed. Each falsifier gets a "healthy agent"
case (falsifier does not trigger -> pass) and a "degenerate agent" case
(falsifier triggers -> fail), proving the checks actually discriminate
rather than trivially passing everything.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
from teic.harness.report import AssessmentReport, GradedVerdict
from teic.harness.thresholds import DEFAULT_THRESHOLDS_PATH, ThresholdsConfig, load_thresholds


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
