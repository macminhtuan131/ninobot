#!/usr/bin/env python3
"""Full recorded-artifact collector/analyzer fixture, without a simulator.

Only path bindings in a copied child summary are changed. Native outcomes,
timestamps, controller traces, samples and source provenance remain verbatim.
No experimental release/validation is bypassed: this calls read-only collection
functions, not an executor. The derived view is quarantined after checks.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('src/nino_rl','src/nino_control','src/nino_rl/scripts')]
from nino_rl.acquisition_contract import finalize_view,verify_view
from nino_rl.acquisition_frames import atomic_json
from run_isolated_governor_cadence import collect
from run_governor_h2_replication import classify
from analyze_governor_h2_replication import extract_metrics
from analyze_governor_cadence_experiment import timing


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def main():
    out=Path(__file__).resolve().parent
    raw=ROOT/'rl_runs/governor_isolated_cadence_v5_2026-10-23'
    files=json.loads((out/'closed_run_sha256.json').read_text())
    assert all(sha(p)==h for p,h in files.items())
    ledger=json.loads((raw/'ledger.json').read_text());slot=ledger['slots'][0];old=slot['result']
    raw_case=Path(old['case']);evaluation=Path(old['evaluation']);primary=Path(old['primary_logger'])
    work=Path(tempfile.mkdtemp(prefix='nino_v5_full_collector_fixture_'))
    attempt=work/'attempt_01';screen=attempt/'confirmation/height/screen';screen.mkdir(parents=True)
    case=screen/raw_case.name;case.mkdir()
    for name in ('config.yaml','evaluation','contact','joint_gt','acquisition'):
        (case/name).symlink_to(raw_case/name,target_is_directory=(raw_case/name).is_dir())
    shutil.copy2(raw/'attempt_01/protocol_before_results.json',attempt/'protocol_before_results.json')
    child=json.loads((raw_case.parent/'summary.json').read_text())
    view=case/'measurement_view'
    result=dict(mode='offline_full_collector_recorded_fixture',simulation_attempts=0,
        closed_batch_remains_invalid=True,performance_comparison=False,
        fixture_directory=str(work),fixture_source_sha256=sha(__file__))
    try:
        finalize_view(case,evaluation,primary,raw_case/'acquisition/session.json')
        verify_view(view)
        assert (view/'world_metadata.json').read_bytes()==(primary/'world_metadata.json').read_bytes()
        child['results'][0]['measurement_logger']=str(view)
        atomic_json(screen/'summary.json',child)
        job={k:slot[k] for k in ('attempt','seed','repeat','triad_id','position','arm','profile','cold_start')}
        collected=collect(ROOT/'docs/governor_isolated_cadence_contract_v5_2026-10-23',job,attempt)
        # These are the actual saved runner outcomes, not invented success flags.
        collected.update(runner_exit=old['runner_exit'],cleanup_confirmed=old['cleanup_confirmed'])
        atomic_json(attempt/'full_fixture_collection.json',collected)
        flags={k:collected.get(k) for k in ('physical_success','stop_pass','setup_pass',
            'provenance_pass','measurement_integrity_pass','quality_available','physical_state_valid','cleanup_confirmed')}
        result['collector_flags']=flags
        result['collector_errors']={k:collected.get(k) for k in ('collection_error','acquisition_error','hard_stop_reason')}
        result['executor_classification']=classify(collected)
        metrics=extract_metrics(collected)
        result['metric_availability']={k:v is not None for k,v in metrics.items()}
        result['native_replay_matches']=collected.get('integrity',{}).get('native_match')
        diagnostic_slot=deepcopy(slot);diagnostic_slot['result']=collected
        evidence,_=timing(diagnostic_slot)
        result['timing_reader_completed']=isinstance(evidence,dict)
        result['cadence_check']=collected.get('cadence_integrity')
        result['software_path_completed']=all(v is True for v in flags.values()) and result['executor_classification'] is None and all(result['metric_availability'].values())
        assert result['software_path_completed'],result
    finally:
        if (view/'view_manifest.json').exists():
            manifest=json.loads((view/'view_manifest.json').read_text())
            manifest.update(admitted_for_new_contract=False,diagnostic_only=True,
                qualification='Post-hoc full collector software fixture only; closed v5 remains invalid. Not an experiment view.')
            atomic_json(view/'view_manifest.json',manifest)
            try:verify_view(view)
            except ValueError:result['diagnostic_view_quarantined']=True
            else:raise AssertionError('Fixture view must not be admitted')
        result['closed_run_files_unchanged']=all(sha(p)==h for p,h in files.items())
        assert result['closed_run_files_unchanged']
        atomic_json(out/'full_collector_fixture.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
