#!/usr/bin/env python3
"""Offline recorded-artifact fixture; never admits or edits the closed v4 run.

The temporary candidate view is quarantined after checks, including on error.
This is a software integration diagnostic, not a replacement experiment result.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('src/nino_rl','src/nino_control','src/nino_rl/scripts')]
from nino_rl.acquisition_contract import finalize_view,verify_view
from nino_rl.acquisition_frames import atomic_json
from nino_rl.slip_reporting import integrate,synchronized_series,replay_native_trace
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from audit_clear_floor_stability import audit,settling_audit
from run_frozen_governor_confirmation import clearance_time
from prepare_governor_contact_sequence import analyze as sequence_analysis


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def main():
    out=Path(__file__).resolve().parent
    manifest=json.loads((out/'closed_run_sha256.json').read_text())
    assert all(sha(p)==h for p,h in manifest.items())
    ledger=json.loads((ROOT/'rl_runs/governor_isolated_cadence_v4_2026-10-23/ledger.json').read_text())
    result=ledger['slots'][0]['result']
    raw_case=Path(result['case']);evaluation=Path(result['evaluation']);primary=Path(result['logger'])
    work=Path(tempfile.mkdtemp(prefix='nino_v4_recorded_schema_fixture_'))
    case=work/'case';case.mkdir()
    for name in ('joint_gt','evaluation'):
        (case/name).symlink_to(raw_case/name,target_is_directory=True)
    view=case/'measurement_view'
    diagnostic=dict(mode='offline_recorded_artifact_fixture',simulation_attempts=0,
        closed_batch_remains_invalid=True,performance_comparison=False,
        work_directory=str(work),fixture_code_sha256=sha(__file__))
    try:
        view=finalize_view(case,evaluation,primary,raw_case/'acquisition/session.json')
        proof=verify_view(view)
        diagnostic['candidate_composition']=dict(run_id=proof['run_id'],
            native_identity_source=proof['native_identity_source'],
            isolated_topic_counts=proof['isolated_topic_counts'],
            missing_values_filled=proof['missing_values_filled'],resampling=proof['resampling'])
        stability=audit(evaluation,view)
        trace=next(evaluation.glob('episode-*/control_trace.csv'))
        controls=list(csv.DictReader(trace.open()))
        end=float(controls[-1]['sim_time_s'])
        diagnostic['stopping_fixture']=settling_audit(view,end)
        data=load(case,dict(seed=77600,profile='full',evaluation=str(evaluation),logger=str(view)))
        gt=gt_timestamp_series(data)
        old=result['quality']['existing_reports'];first=old['first_contact_s']
        clear=clearance_time(data['ground'],first,dict(x_m=3.1,angle_deg=8.))
        windows=dict(whole_route=(data['start'],data['end']),crossing=(first+.05,clear),post=(first+.05,first+3.))
        methods=dict(gt_native=gt,grid20ms=synchronized_series(data),shifted10ms=synchronized_series(data,offset=.01))
        checks={method:{label:integrate(signal,*bounds) for label,bounds in windows.items()}
                for method,signal in methods.items()}
        diagnostic['coverage_fixture']={method:{label:dict(available=v['available'],coverage_fraction=v['coverage_fraction'])
            for label,v in values.items()} for method,values in checks.items()}
        native=next(csv.DictReader((evaluation/'episodes.csv').open()))
        replay=replay_native_trace(controls)
        diagnostic['native_replay_matches']=math.isclose(replay['rms'],float(native['rms_wheel_slip']),rel_tol=1e-10,abs_tol=1e-10)
        row=dict(old,case=str(case),logger=str(view),evaluation=str(evaluation),arm='full',
                 gt_native={k:v for k,v in checks['gt_native'].items() if k!='post'})
        sequence=sequence_analysis(row)
        diagnostic['sequence_fixture']=dict(available=sequence.get('available'),reason=sequence.get('reason'),
            windows={name:{'slip':{'available':v['slip']['available'],'coverage_fraction':v['slip']['coverage_fraction']},
                           'vertical':{'available':v['vertical']['available'],'coverage_fraction':v['vertical']['coverage_fraction']}}
                     for name,v in sequence.get('metrics',{}).items()} if 'metrics' in sequence else None)
        diagnostic['stability_fixture_completed']=bool(stability)
        diagnostic['software_path_completed']=True
    except Exception as error:
        diagnostic.update(software_path_completed=False,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if (view/'view_manifest.json').exists():
            value=json.loads((view/'view_manifest.json').read_text())
            value.update(admitted_for_new_contract=False,diagnostic_only=True,
                qualification='Post-hoc recorded-artifact software fixture. Closed v4 batch remains invalid; no performance comparison or promotion.')
            atomic_json(view/'view_manifest.json',value)
            try:
                verify_view(view)
            except ValueError:
                diagnostic['diagnostic_view_quarantined']=True
            else:
                raise AssertionError('Diagnostic view must never be admitted')
        diagnostic['closed_run_files_unchanged']=all(sha(p)==h for p,h in manifest.items())
        assert diagnostic['closed_run_files_unchanged']
        atomic_json(out/'recorded_schema_fixture.json',diagnostic)
    print(json.dumps(diagnostic,indent=2))


if __name__=='__main__':main()
