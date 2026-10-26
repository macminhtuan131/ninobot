#!/usr/bin/env python3
"""Separate descriptive survey: bounded collection/uncertainty, no H2 decision.

Formal H2 executor, application and frozen parent bundle are not modified.
Live mode requires a descriptive authorization sealed before attempt one.
"""
import argparse
from copy import deepcopy
import fcntl
import json
from pathlib import Path
import shutil
import signal

import analyze_governor_h2_replication as analysis
import run_governor_h2_replication as executor
from prepare_governor_h2_protocol import ROOT,sha,validate_bundle,write

MODE="descriptive_only_no_H2_decision"
USER_SELECTION="Khảo sát mô tả tối đa 16 attempts: giữ ngưỡng ở mức đề xuất, báo số đo và khoảng bất định, chưa kết luận H2 đạt/không đạt"
CLAIM_BANK=ROOT/"rl_runs/.governor_descriptive_budget_claims"


def prepare(parent, output):
    validation=validate_bundle(parent)
    old=json.loads((parent/"protocol.json").read_text())
    output.mkdir(parents=True,exist_ok=False)
    for name in old["frozen_bundle_sha256"]:
        target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(parent/name,target)
    shutil.copy2(parent/"application_requirements.json",output/"application_requirements.json")
    spec=dict(mode=MODE,metrics=list(analysis.METRICS),units=analysis.UNITS,
        bootstrap=dict(draws=analysis.BOOTSTRAP_DRAWS,seed=analysis.BOOTSTRAP_SEED,
            unit="intact pair within each of two fixed seed blocks",interval="percentile95",
            same_draws_across_metrics=True,small_sample_coverage_not_guaranteed=True),
        estimand="equal-weight mean of two block1-meanGovernor/meanPI; no selected primary or scalar objective",
        missing="retain all16 assigned slots and8 pairs; unavailable metrics/intervals stay null; no successful-only means",
        sampling="GT native timestamp primary representation with20ms/+10ms grid sensitivity; no favorable-grid selection",
        windows=deepcopy(old["outcome_windows"]),measurement=deepcopy(old["measurement"]),
        no_application_thresholds=True,no_formal_H2_decision=True,no_tuning_promotion=True,
        timing="existing causal read_evidence checks; report available opportunity and body/wheel snapshots without claiming identified motor latency",
        comparability="report existing approach checks without dropping or replacing attempts",
        limitations="one fixed6mm rigid obstacle; seeds label repeated cold starts, not new terrain or exact-state branching; no sim-to-real or H3 claim")
    write(output/"survey_spec.json",spec)
    write(output/"user_authorization.json",dict(date="2026-10-18",user_selection=USER_SELECTION,
        mode=MODE,maximum_attempts=16,execution_authorized=True,criteria_accepted=False,
        real_robot_work_on_hold=True,retries=0,replacements=0,automatic_extension=False))
    snapshot=output/"source_snapshot/descriptive_survey.py"
    shutil.copy2(Path(__file__),snapshot)
    protocol=deepcopy(old)
    protocol.update(contract="descriptive_fixed_reactive_v1_2026_10_18",status="authorized_descriptive_prepared",
        purpose="Descriptive repeated comparison of frozen PI and reactive governor; retain proposed criteria without applying them.",
        parent_protocol=dict(path=str(parent.resolve()),sha256=sha(parent/"protocol.json")),
        decision=dict(mode=MODE,primary_metric=None,minimum_improvement=None,maximum_added_seconds=None,
            H2_decision="not_assessed",automatic_promotion=False),
        execution=dict(runner_implemented=True,runner=str(Path(__file__).relative_to(ROOT)),mode=MODE),
        prerequisites=["explicit descriptive16-attempt user authorization and sealed spec/release",
            "same physical/runtime source hashes, schedule, reset/stop gates and cleanup",
            "no retries, replacements, additional smoke episodes or threshold-based decisions"])
    protocol["budget"].update(released=True,retries=0,replacements=0,automatic_extension=False)
    for name in ("survey_spec.json","user_authorization.json","source_snapshot/descriptive_survey.py"):
        protocol["frozen_bundle_sha256"][name]=sha(output/name)
    write(output/"protocol.json",protocol)
    write(output/"prepared_manifest.json",dict(protocol_sha256=sha(output/"protocol.json"),
        parent_protocol_sha256=sha(parent/"protocol.json"),application_sealed=False,application_confirmed=False,
        mode=MODE,note="Descriptive authorization is separate from formal H2 acceptance; proposed application unchanged."))
    release=dict(mode=MODE,maximum_attempts=16,budget_released=True,execution_authorized=True,
        criteria_accepted=False,formal_H2_authorized=False,protocol_sha256=sha(output/"protocol.json"),
        application_sha256=sha(output/"application_requirements.json"),
        user_authorization_sha256=sha(output/"user_authorization.json"),
        survey_source_sha256=sha(Path(__file__)),execution_dependency_sha256=executor.execution_dependencies(),
        authorization_reference="2026-10-18 explicit user selection: "+USER_SELECTION)
    write(output/"survey_release.json",release)
    validate_survey(output)
    return dict(mode=MODE,maximum_attempts=16,simulation_episodes=0,parent_validation=validation,
        protocol_sha256=sha(output/"protocol.json"),release_sha256=sha(output/"survey_release.json"))


def validate_survey(bundle):
    validate_bundle(bundle)
    protocol=json.loads((bundle/"protocol.json").read_text())
    release=json.loads((bundle/"survey_release.json").read_text())
    auth=json.loads((bundle/"user_authorization.json").read_text())
    app=json.loads((bundle/"application_requirements.json").read_text())
    checks=[protocol["decision"]["mode"]==MODE,release.get("mode")==MODE,
        release.get("maximum_attempts")==16,release.get("budget_released") is True,
        release.get("execution_authorized") is True,release.get("criteria_accepted") is False,
        release.get("formal_H2_authorized") is False,auth.get("user_selection")==USER_SELECTION,
        auth.get("execution_authorized") is True,auth.get("criteria_accepted") is False,
        auth.get("maximum_attempts")==16,app.get("status")!="confirmed",
        app.get("primary_metric") is None,app.get("minimum_relative_improvement") is None,
        app.get("maximum_added_route_seconds") is None,
        release.get("protocol_sha256")==sha(bundle/"protocol.json"),
        release.get("application_sha256")==sha(bundle/"application_requirements.json"),
        release.get("user_authorization_sha256")==sha(bundle/"user_authorization.json"),
        release.get("survey_source_sha256")==sha(Path(__file__)),
        release.get("execution_dependency_sha256")==executor.execution_dependencies()]
    if not all(checks):
        raise ValueError("Descriptive contract/release/source drift or attempted application acceptance")
    return protocol,release


def descriptive_report(protocol, slots, evidence):
    rows,structural=analysis.normalize(protocol,slots,evidence)
    pairs=analysis.paired_metrics(rows)
    estimates=analysis.estimate(pairs)
    approach=analysis.approach_pairs(rows)
    sampled={}
    for label in ("77500","77501","aggregate"):
        metrics={key:(estimates[key]["aggregate"] if label=="aggregate" else estimates[key]["blocks"][label]) for key in ("post_slip","grid_slip","shifted_slip")}
        values={key:value["relative_benefit"] for key,value in metrics.items()}
        finite=[v for v in values.values() if v is not None]
        sampled[label]=dict(relative_benefits=values,sign_reversal=(min(finite)<0<max(finite)) if len(finite)==3 else None)
    return dict(mode=MODE,H2_decision="not_assessed",thresholds_applied=False,primary_metric=None,
        automatic_promotion=False,structural_issues=structural,
        counts=dict(assigned=16,attempted=sum(r["status"]!="not_attempted" for r in rows),
            arrivals=sum(r["physical_success"] is True for r in rows),
            failures=sum(r["physical_success"] is False for r in rows),
            native_unknown=sum(r["physical_success"] is None for r in rows),
            stopping_failures=sum(r["stop_pass"] is False for r in rows),
            metric_missing={key:sum(r["metrics"][key] is None for r in rows) for key in analysis.METRICS}),
        estimates=estimates,pairs=pairs,episodes=rows,approach_pairs=approach,sampling_sensitivity=sampled,
        bootstrap=dict(draws=analysis.BOOTSTRAP_DRAWS,seed=analysis.BOOTSTRAP_SEED,interval="percentile95",
            qualification="4 pairs per fixed seed; descriptive uncertainty, not guaranteed power/coverage"),
        interpretation="No pass/fail application claim, no conclusion beyond driving slower, no extension/tuning/predictor/PPO authorized.")


def markdown(report):
    def fmt(v):return "N/A" if v is None else f"{v:.6g}"
    def ci(v):return "N/A" if v is None else f"[{fmt(v[0])}, {fmt(v[1])}]"
    lines=["# Khảo sát mô tả governor — 18/10/2026", "", "**Không áp dụng ngưỡng đề xuất và không kết luận H2 đạt/không đạt.**", "",
        "Counts: `"+json.dumps(report["counts"],ensure_ascii=False)+"`", "",
        "## Hai block và aggregate", "", "Benefit dương nghĩa là governor thấp hơn PI. Delta = governor − PI. CI là bootstrap percentile 95% theo cặp; N nhỏ, không bảo đảm power/coverage.", "",
        "| Metric | Nhóm | PI | Governor | Delta [CI95] | Relative benefit [CI95] |", "|---|---|---:|---:|---|---|"]
    for key,estimate in report["estimates"].items():
        for label in ("77500","77501","aggregate"):
            row=estimate["aggregate"] if label=="aggregate" else estimate["blocks"][label]
            lines.append(f"| {key} ({estimate['unit']}) | {label} | {fmt(row['full_mean'])} | {fmt(row['reactive_mean'])} | {fmt(row['mean_delta'])} {ci(row['delta_CI95'])} | {fmt(row['relative_benefit'])} {ci(row['benefit_CI95'])} |")
    lines += ["", "## Mọi attempt, failures và timing", "",
        "| Attempt | Seed/lặp | Arm | Status | Arrival | Stop | Termination | Timing evidence |", "|---:|---|---|---|---|---|---|---|"]
    for row in report["episodes"]:
        timing=row["timing"]
        lines.append(f"| {row['attempt']} | {row['seed']}/{row['repeat']} | {row['profile']} | {row['status']} | {row['physical_success']} | {row['stop_pass']} | {row['termination']} | {timing.get('reason') or timing.get('error')} |")
    lines += ["", "## Tám cặp (giữ cả dữ liệu thiếu)", "", "| Seed/lặp | Post slip PI/Gov | Post rung PI/Gov | Time delta s | Tracking PI/Gov m |", "|---|---|---|---|---|"]
    for pair in report["pairs"]:
        m=pair["metrics"]
        both=lambda k:fmt(m[k]["full"])+" / "+fmt(m[k]["reactive"])
        lines.append(f"| {pair['seed']}/{pair['repeat']} | {both('post_slip')} | {both('post_vibration')} | {fmt(m['time']['delta'])} | {both('tracking')} |")
    lines += ["", "Sampling sensitivity: `"+json.dumps(report["sampling_sensitivity"])+"`", "",
        "Approach comparability và toàn bộ response snapshots nằm trong report.json; không lọc hoặc bù lượt không so sánh được.",
        "Metric thiếu không thành 0. Aggregate cần đủ tám cặp; không dùng mean của các lượt thành công để thay thế.",
        "Một hình học gờ cứng 6 mm, không phải terrain generalization, same-snapshot branching hay sim-to-real.",
        "Không tự mở thêm simulation, tuning, predictor hoặc PPO từ báo cáo này.", ""]
    return "\n".join(lines)


def analyze(bundle,run,output):
    protocol,release=validate_survey(bundle)
    output.mkdir(parents=True,exist_ok=False)
    paths=[bundle/"protocol.json",bundle/"survey_spec.json",bundle/"survey_release.json",run/"ledger.json",
           run/"protocol_snapshot.json",run/"authorization_snapshot.json"]
    hashes={str(p.resolve()):sha(p) for p in paths if p.is_file()}
    issues=[]
    if json.loads((run/"protocol_snapshot.json").read_text())!=protocol:
        issues.append("protocol_snapshot_mismatch")
    authorization=json.loads((run/"authorization_snapshot.json").read_text())
    if authorization.get("release")!=release or authorization.get("mode")!=MODE:
        issues.append("descriptive_authorization_snapshot_mismatch")
    slots=json.loads((run/"ledger.json").read_text())["slots"]
    evidence={}
    for row in slots:
        if row["status"]=="not_attempted" or not row.get("result"):continue
        try:
            evidence[row["attempt"]],inputs=analysis.read_evidence(row,run)
            hashes.update(inputs)
        except (ValueError,KeyError,OSError,TypeError) as exc:
            evidence[row["attempt"]]=dict(available=False,reason=f"{type(exc).__name__}: {exc}")
    report=descriptive_report(protocol,slots,evidence)
    changed=[p for p,h in hashes.items() if sha(Path(p))!=h]
    report["input_issues"]=issues+(["inputs_changed_while_reading"] if changed else [])
    write(output/"report.json",report)
    write(output/"input_sha256.json",hashes)
    (output/"REPORT.md").write_text(markdown(report))
    return report


def execute(bundle,run,domain,adapter=None):
    protocol,release=validate_survey(bundle)
    def verify():
        p,r=validate_survey(bundle)
        if p!=protocol or r!=release:raise ValueError("Survey release changed during collection")
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    with open(f"/tmp/nino_h2_executor_domain_{domain}.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if run.exists():raise FileExistsError("No overwrite, resume, retry or replacement attempts")
        claim=executor.claim_release(bundle/"survey_release.json",run,CLAIM_BANK)
        inner=adapter or executor.LiveAdapter(bundle,domain)
        def collect(job,attempt):
            print(f"ATTEMPT {job['attempt']}/16 seed={job['seed']} repeat={job['repeat']} profile={job['profile']}",flush=True)
            result=inner(job,attempt)
            print(f"COLLECTED {job['attempt']}: arrival={result.get('physical_success')} termination={result.get('termination')} integrity={result.get('measurement_integrity_pass')} cleanup={result.get('cleanup_confirmed')}",flush=True)
            return result
        summary=executor.run_attempts(protocol,run,collect,verify,dict(mode=MODE,release=release,
            application=json.loads((bundle/"application_requirements.json").read_text()),release_claim=str(claim),
            domain=domain,partition=f"nino_h2_replication_{domain}"))
    summary.update(mode=MODE,H2_decision="not_assessed",thresholds_applied=False)
    executor.atomic_json(run/"summary.json",summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","validate","execute","analyze"))
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--parent",type=Path,default=ROOT/"docs/governor_h2_replication_protocol_2026-10-17")
    parser.add_argument("--run",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--domain",type=int,default=109)
    args=parser.parse_args()
    if not 0<=args.domain<=232:parser.error("domain must be0..232")
    if args.action in ("execute","analyze") and args.run is None:parser.error("--run required")
    if args.action=="prepare":result=prepare(args.parent.resolve(),args.bundle.resolve())
    elif args.action=="validate":
        p,r=validate_survey(args.bundle.resolve())
        result=dict(mode=MODE,maximum_attempts=16,protocol_sha256=sha(args.bundle/"protocol.json"),validated=True)
    elif args.action=="execute":result=execute(args.bundle.resolve(),args.run.resolve(),args.domain)
    else:
        if args.output is None:parser.error("--output required")
        report=analyze(args.bundle.resolve(),args.run.resolve(),args.output.resolve())
        result=dict(mode=report["mode"],counts=report["counts"],H2_decision=report["H2_decision"])
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":main()
