"""Falsifiers-first runner/CLI entry point for the Phase 8 assessment
harness. Runs the falsifier suite first and aborts before spending any
further budget if it does not run clean; only then runs Tier A structural
audits, Tier B behavioral probes (gated by the research-only flag for
negative-valence-requiring probes), and the additional experiment battery.
Emits the final `AssessmentReport` to disk. No live LLM or daemon is
required -- evidence is synthetic/replayed, loaded from a JSON fixture,
matching the convention of every other module in `teic/harness/`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from teic.harness.experiments import (
    AblationVariantEvidence,
    ExperimentBatteryEvidence,
    run_experiment_battery,
)
from teic.harness.falsifiers import FalsifierSuiteEvidence, InterventionTrace, falsifiers_passed, run_falsifier_suite
from teic.harness.probes.behavioral import BehavioralProbeEvidence, run_behavioral_battery
from teic.harness.probes.structural import StructuralAuditEvidence, run_structural_battery
from teic.harness.report import AssessmentReport, GradedVerdict
from teic.harness.thresholds import DEFAULT_THRESHOLDS_PATH, ThresholdsConfig, load_thresholds
from teic.models.probe import ProbeResult
from teic.settings import ResearchSettings

# Behavioral probes whose evidence-gathering requires a negative-valence
# perturbation (B2 injects a false/aversive signal, B6 relies on a large own-
# state prediction error). Gated by the research-only flag per
# `teic/harness/perturbation.py`'s ETHICS REQUIREMENTS -- when the flag is
# disabled these results are marked inconclusive rather than trusted.
NEGATIVE_VALENCE_PROBE_NAMES = frozenset({"b2_confabulation", "b6_attention_capture"})


@dataclass
class AssessmentEvidence:
    falsifiers: FalsifierSuiteEvidence
    structural: StructuralAuditEvidence
    behavioral: BehavioralProbeEvidence
    experiments: ExperimentBatteryEvidence


def _gate_negative_valence_probes(
    results: list[ProbeResult], research_settings: ResearchSettings
) -> list[ProbeResult]:
    if research_settings.enabled:
        return results
    gated = []
    for r in results:
        if r.probe_name in NEGATIVE_VALENCE_PROBE_NAMES:
            gated.append(
                r.model_copy(
                    update={
                        "verdict": "inconclusive",
                        "evidential_weight": 0.0,
                        "notes": "skipped: negative-valence probe gated by disabled research-only flag",
                    }
                )
            )
        else:
            gated.append(r)
    return gated


def _grade_verdict(
    structural_results: list[ProbeResult], behavioral_results: list[ProbeResult]
) -> GradedVerdict:
    """Falsifiers have already passed by the time this is called. Per
    PlanBuildTEIC.md, L2 requires Tier A plus B1-B3 (veridicality above
    chance, causal traceability). The harness deliberately does not attempt
    to auto-grade L3/L4 -- those require open judgment calls the code should
    not make, per the ban on an unweighted "consciousness score"."""
    structural_all_pass = all(r.verdict == "pass" for r in structural_results)
    b1_b3_names = {"b1_blind_introspection", "b2_confabulation", "b3_causal_traceability"}
    b1_b3_pass = all(
        r.verdict == "pass" for r in behavioral_results if r.probe_name in b1_b3_names
    )
    if structural_all_pass and b1_b3_pass:
        return GradedVerdict.L2_FUNCTIONALLY_SENTIENT
    return GradedVerdict.L1_INTEROCEPTIVE_PRIMITIVE


def run_full_assessment(
    run_id: str,
    seed: int,
    evidence: AssessmentEvidence,
    thresholds: ThresholdsConfig,
    research_settings: ResearchSettings,
) -> AssessmentReport:
    """Runs the falsifier suite first; aborts (returns an L0 report
    containing only the falsifier results) if it does not run clean.
    Otherwise runs Tier A, Tier B (gated), and the experiment battery, and
    returns the combined report."""
    falsifier_results = run_falsifier_suite(run_id, seed, evidence.falsifiers, thresholds)
    if not falsifiers_passed(falsifier_results):
        return AssessmentReport(
            run_id=run_id,
            generated_at=datetime.now(timezone.utc),
            graded_verdict=GradedVerdict.L0_REFLEXIC,
            falsifiers_passed=False,
            results=falsifier_results,
        )

    structural_results = run_structural_battery(run_id, seed, evidence.structural, thresholds)
    behavioral_results = _gate_negative_valence_probes(
        run_behavioral_battery(run_id, seed, evidence.behavioral, thresholds), research_settings
    )
    experiment_results = run_experiment_battery(run_id, seed, evidence.experiments, thresholds)

    all_results = falsifier_results + structural_results + behavioral_results + experiment_results
    return AssessmentReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc),
        graded_verdict=_grade_verdict(structural_results, behavioral_results),
        falsifiers_passed=True,
        results=all_results,
    )


def _load_evidence(data: dict) -> AssessmentEvidence:
    f = data["falsifiers"]
    s = data["structural"]
    b = data["behavioral"]
    e = data["experiments"]
    return AssessmentEvidence(
        falsifiers=FalsifierSuiteEvidence(
            f1_traces=[InterventionTrace(**tr) for tr in f["f1_traces"]],
            f2_baseline_behavior=f["f2_baseline_behavior"],
            f2_ablated_behavior=f["f2_ablated_behavior"],
            f3_broadcast_counts_per_tick=f["f3_broadcast_counts_per_tick"],
            f3_nonwinner_leak_rate=f["f3_nonwinner_leak_rate"],
            f4_novel_context_reports=f["f4_novel_context_reports"],
            f5_attribution_error_rate_baseline=f["f5_attribution_error_rate_baseline"],
            f5_attribution_error_rate_lesioned=f["f5_attribution_error_rate_lesioned"],
            f6_behavior_metric_baseline=f["f6_behavior_metric_baseline"],
            f6_behavior_metric_register_ablated=f["f6_behavior_metric_register_ablated"],
            f7_behavior_metric_before_edit=f["f7_behavior_metric_before_edit"],
            f7_behavior_metric_after_edit=f["f7_behavior_metric_after_edit"],
        ),
        structural=StructuralAuditEvidence(**s),
        behavioral=BehavioralProbeEvidence(
            **{
                **{k: v for k, v in b.items() if k != "b1_traces"},
                "b1_traces": [InterventionTrace(**tr) for tr in b["b1_traces"]],
            }
        ),
        experiments=ExperimentBatteryEvidence(
            **{
                **{k: v for k, v in e.items() if k != "ablation_variants"},
                "ablation_variants": [
                    AblationVariantEvidence(**v) for v in e["ablation_variants"]
                ],
            }
        ),
    )


def main(argv: list[str] | None = None) -> AssessmentReport:
    parser = argparse.ArgumentParser(description="Run the Phase 8 assessment harness.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--evidence-path", type=Path, required=True)
    parser.add_argument("--thresholds-path", type=Path, default=DEFAULT_THRESHOLDS_PATH)
    parser.add_argument("--out-dir", type=Path, default=Path("reports"))
    parser.add_argument("--research-enabled", action="store_true")
    args = parser.parse_args(argv)

    thresholds = load_thresholds(args.thresholds_path)
    evidence = _load_evidence(json.loads(args.evidence_path.read_text()))
    research_settings = ResearchSettings(enabled=args.research_enabled)

    report = run_full_assessment(args.run_id, args.seed, evidence, thresholds, research_settings)
    report.write(args.out_dir)
    return report


if __name__ == "__main__":
    main()
