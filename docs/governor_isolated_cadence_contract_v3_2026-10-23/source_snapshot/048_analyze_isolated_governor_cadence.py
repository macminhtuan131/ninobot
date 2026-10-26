#!/usr/bin/env python3
"""Admit both acquisition sources before the unchanged descriptive cadence analysis."""
import argparse
import json
from pathlib import Path

from prepare_isolated_cadence_contract import validate,sha,write
from analyze_governor_cadence_experiment import analyze as descriptive_analysis
from nino_rl.acquisition_contract import verify_view


def analyze(bundle,run,output):
    validate(bundle)
    ledger=json.loads((run/"ledger.json").read_text())
    if ledger.get("dry_run"):raise ValueError("Software ledger is not physical experiment data")
    issues=[]
    for slot in ledger["slots"]:
        if not slot.get("adapter_requested"):continue
        result=slot.get("result") or {}
        try:
            manifest=verify_view(result["logger"])
            if manifest["protocol_sha256"]!=sha(bundle/"protocol.json"):
                raise ValueError("Foreign measurement protocol")
            if result.get("measurement_integrity_pass") is not True:
                raise ValueError("Original replay/coverage/timestamp/cadence gate did not pass")
        except (OSError,ValueError,KeyError,TypeError) as error:
            issues.append(dict(attempt=slot["attempt"],error=f"{type(error).__name__}: {error}"))
    if issues:
        output.mkdir(parents=True,exist_ok=False)
        write(output/"report.json",dict(status="measurement_invalid_no_performance_comparison",
            H2_decision="not_assessed",thresholds_applied=False,issues=issues,
            all_assigned_slots_and_native_outcomes=ledger["slots"],contrasts=None,
            no_failures_dropped=True,no_retry=True))
        return dict(measurement_valid=False,performance_comparison=False)
    counts=descriptive_analysis(bundle,run,output,bundle_validator=validate)
    write(output/"ordered_questions.json",dict(
        measurement_valid=True,H2_decision="not_assessed",thresholds_applied=False,
        questions=[
            dict(order=1,question="Did reduced commands arrive earlier?",
                 evidence="report.json:timing and preintervention_pairs command_execution_offsets_s; use drive receipt/publication, not only governor decision"),
            dict(order=2,question="Did actual wheel AND body speed change earlier BEFORE a subsequent loaded contact?",
                 evidence="report.json:timing.response_snapshots + joint/GT trajectory in sealed measurement_view; retain pre-intervention differences",
                 automatic_answer=None,
                 warning="An earlier target, presence of snapshots or timing_pass is NOT proof of actual speed response or useful authority. Inspect actual trajectories and complete contact sequence; unavailable evidence stays unknown."),
            dict(order=3,question="Was crossing quality better with reasonable time/tracking cost?",
                 evidence="report.json:contrasts and sampling_sensitivity; post-contact + whole-route/sequence, failures, slip/vibration, time/tracking intervals",
                 automatic_answer=None,warning="Application thresholds remain proposals; no automatic H2 promotion or tuning")]))
    return counts


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("bundle","run","output"):parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(analyze(args.bundle,args.run,args.output),indent=2))
