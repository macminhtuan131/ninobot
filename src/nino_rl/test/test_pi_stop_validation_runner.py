"""Actual coordinator/wrapper and fail-closed ledger; synthetic interfaces only."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from nino_rl import pi_stop_validation_runner as job
from nino_rl import pi_stop_validation_preflight as preflight


@pytest.fixture(scope='module')
def identity():return job.context.identity()


@pytest.fixture
def lifecycle(monkeypatch,identity):
    from contextlib import ExitStack
    instances=[]
    with ExitStack() as stack:
        for patch in preflight.fixture_patches():stack.enter_context(patch)
        monkeypatch.setattr(preflight.SyntheticLifecycle,'instances',instances)
        monkeypatch.setattr(job.context,'identity',lambda:deepcopy(identity))
        yield instances


@pytest.mark.parametrize('index',[0,1])
def test_actual_cell_full_140_wrapper_validator_and_cleanup(tmp_path,lifecycle,index,identity):
    result=job.evaluate(tmp_path/'cell',job.protocol()['evaluation_order'][index],'synthetic')
    rows=[json.loads(s) for s in (tmp_path/'cell/trace.jsonl').read_text().splitlines()]
    assert result['steps']==len(rows)==lifecycle[0].calls==140 and lifecycle[0].closed
    assert rows[-1]['terminated'] and not rows[-1]['truncated']
    assert all(row['pi_stop_identity']==identity for row in rows)
    assert all(row['requested_scalar_action']==[0.] for row in rows)
    assert result['actor_loads']==result['optimizer_updates_in_job']==0


@pytest.mark.parametrize('fault',['permission','wrong_ki','cleanup'])
def test_cell_fault_retains_trace_and_closes_backend(tmp_path,lifecycle,monkeypatch,fault):
    cls=preflight.SyntheticLifecycle
    if fault=='permission':
        original=cls.view
        def view(obj):
            v=original(obj);v['permission']=False;return v
        monkeypatch.setattr(cls,'view',view)
    if fault=='wrong_ki':
        original=cls.advance_reference
        def advance(obj,*a,**kw):
            v,l,t,u,i=original(obj,*a,**kw);i['pi_screen_audit']['velocity_ki']=.15
            return v,l,t,u,i
        monkeypatch.setattr(cls,'advance_reference',advance)
    if fault=='cleanup':
        original=cls.close
        def close(obj):original(obj);raise RuntimeError('synthetic close failure')
        monkeypatch.setattr(cls,'close',close)
    with pytest.raises((ValueError,RuntimeError)):
        job.evaluate(tmp_path/'cell',job.protocol()['evaluation_order'][0],'synthetic')
    assert lifecycle[0].closed
    if fault=='permission':assert lifecycle[0].calls==0
    if fault=='wrong_ki':
        assert lifecycle[0].calls==1
        assert job.parent.read(tmp_path/'cell/failure.json')['valid_rows']==0
        assert (tmp_path/'cell/trace.jsonl').is_file()
    if fault=='cleanup':assert (tmp_path/'cell/cleanup_failure.json').is_file()


def test_unknown_condition_cannot_create_backend(tmp_path,monkeypatch):
    monkeypatch.setattr(job,'EpisodeLifecycle',lambda *a,**k:pytest.fail('No backend'))
    with pytest.raises(ValueError,match='Undeclared'):
        job.evaluate(tmp_path/'cell',dict(ki=.2,arm='TD3'),'none')
    assert not (tmp_path/'cell').exists()


def test_protocol_matrix_and_zero_learning_budget():
    p=job.protocol()
    assert [r['ki'] for r in p['evaluation_order']]==[.1,.15,.15,.1]
    assert [r['block'] for r in p['evaluation_order']]==[0,0,1,1]
    assert p['maximum_launches']==4 and p['maximum_eval_ticks']==4*140==560
    assert all(r['gain']==1. and r['arm']=='B0' and r['source_stop_s']==6. for r in p['evaluation_order'])
    assert all(p[k]==0 for k in ('training_transitions','optimizer_updates','actor_loads','probes','retries','extra_smokes','hardware_actions'))
    assert p['constraints']['max_physical_path_rmse_m']==.04
    assert p['constraints']['quiet_stop_s']==2.


def fixture_results(kind):
    runs=[]
    for condition in job.protocol()['evaluation_order']:
        value=.94 if condition['ki']==.15 else 1.
        if condition['ki']==.15:
            if kind=='worse':value=1.02
            if kind=='small':value=.98
            if kind=='mixed' and condition['block']==1:value=1.02
        gt=1.02 if kind=='grid' and condition['ki']==.15 else value
        if kind=='zero' and condition['ki']==.1:value=0.
        if kind=='nan':value=float('nan')
        runs.append(dict(steps=140,evaluation_condition=deepcopy(condition),
            functional_proposal_pass=True,nominal_velocity_rmse_m_s=value,
            timestamp_diagnostic=dict(valid=True,header_grid={'0.0':dict(rmse_m_s=gt),'0.01':dict(rmse_m_s=gt)})))
    return runs


@pytest.mark.parametrize('kind,expected',[
    ('better','descriptive_PI_stop6_validation_pass_baseline_review_required'),
    ('worse','no_go_candidate_retain_Ki_0_10'),
    ('small','unknown_small_or_block_dependent_effect'),
    ('mixed','unknown_small_or_block_dependent_effect'),
    ('grid','unknown_grid_sensitive'),('zero','unknown_nonfinite_or_zero_denominator'),
    ('nan','unknown_nonfinite_or_zero_denominator')])
def test_compare_keeps_two_pairs_primary_and_grids(kind,expected):
    result=job.compare(fixture_results(kind))
    assert result['decision']==expected and not result['benefit_verified'] and not result['training_released']
    if kind=='better':
        assert result['pairs'][1]['baseline_indices']==[3,2]


@pytest.mark.parametrize('fault',['short','reorder','duplicate','task','timing'])
def test_invalid_matrix_cannot_be_compared(fault):
    runs=fixture_results('better')
    if fault=='short':runs.pop()
    if fault=='reorder':runs.reverse()
    if fault=='duplicate':runs[1]=deepcopy(runs[0])
    if fault=='task':runs[0]['functional_proposal_pass']=False
    if fault=='timing':runs[0]['timestamp_diagnostic']['valid']=False
    with pytest.raises(ValueError):job.compare(runs)


@pytest.mark.parametrize('at',[0,1,2,3])
def test_first_failure_closes_all_unattempted_slots(tmp_path,monkeypatch,at):
    monkeypatch.setattr(job.parent.frozen,'prepare_worlds',lambda out:dict(clear_box='none'))
    calls=[];runs=fixture_results('better')
    def evaluate(out,condition,world):
        calls.append(condition)
        if len(calls)-1==at:raise RuntimeError('synthetic cell fault')
        return runs[len(calls)-1]
    monkeypatch.setattr(job,'evaluate',evaluate)
    with pytest.raises(RuntimeError):job.execute(tmp_path,{})
    progress=job.parent.read(tmp_path/'evaluation_progress.json')
    assert calls==job.protocol()['evaluation_order'][:at+1]
    assert progress['remaining_slots_closed'] and progress['unused_slots_closed']==3-at


def test_world_preparation_failure_closes_all_four_slots(tmp_path,monkeypatch):
    def fail(out):raise RuntimeError('synthetic world preparation failure')
    monkeypatch.setattr(job.parent.frozen,'prepare_worlds',fail)
    with pytest.raises(RuntimeError):job.execute(tmp_path,{})
    p=job.parent.read(tmp_path/'evaluation_progress.json')
    assert p['attempted']==[] and p['unused_slots_closed']==4 and p['remaining_slots_closed']


def test_execute_exact_four_conditions_no_fifth(tmp_path,monkeypatch):
    monkeypatch.setattr(job.parent.frozen,'prepare_worlds',lambda out:dict(clear_box='none'))
    calls=[];runs=fixture_results('better')
    def evaluate(out,c,w):calls.append(c);return runs[len(calls)-1]
    monkeypatch.setattr(job,'evaluate',evaluate)
    result=job.execute(tmp_path,{})
    assert calls==job.protocol()['evaluation_order'] and result['evaluation_transitions']==560
    assert result['remaining_slots_closed'] and result['actor_loads']==0


def test_actual_unreleased_gate_before_root_or_source(tmp_path,monkeypatch):
    monkeypatch.setattr(job,'source',lambda *a:pytest.fail('No source/runtime IO after denied release'))
    with pytest.raises(ValueError,match='not released'):job.run(tmp_path/'unused')
    assert not (tmp_path/'unused').exists()


@pytest.mark.parametrize('state',['broken','running','failed','completed'])
def test_any_existing_ledger_blocks_reentry_before_release(tmp_path,monkeypatch,state):
    (tmp_path/'state.json').write_text(state)
    monkeypatch.setattr(job,'release_ready',lambda *a:pytest.fail('Consumed first'))
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path)


@pytest.mark.parametrize('kind',['failure','cancel','success'])
def test_coordinator_always_seals_state_and_never_reopens(tmp_path,monkeypatch,kind):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    monkeypatch.setattr(job,'release_ready',lambda root:dict(synthetic=True))
    monkeypatch.setattr(job,'source',lambda *a:dict(synthetic=True))
    monkeypatch.setattr(job,'fingerprint',lambda:'synthetic')
    monkeypatch.setattr(job,'source_fingerprint',lambda:'synthetic')
    monkeypatch.setattr(job,'runtime_versions',lambda:{'fixture':True})
    def execute(out,deps):
        if kind=='failure':raise RuntimeError('synthetic')
        if kind=='cancel':raise KeyboardInterrupt()
        return dict(fixture=True)
    monkeypatch.setattr(job,'execute',execute)
    root=tmp_path/'root'
    if kind=='success':out=job.run(root)
    else:
        with pytest.raises(KeyboardInterrupt if kind=='cancel' else RuntimeError):job.run(root)
    state=job.parent.read(root/'state.json');row=state['runs'][0]
    out=root/row['path'];m=job.parent.read(out/'manifest.json')
    assert row['status']==m['status']==('completed' if kind=='success' else 'cancelled' if kind=='cancel' else 'failed')
    assert row['remaining_slots_closed'] and state['allocated_slots']==4 and not state['retry_allowed']
    assert (job.ACTION in state['latest']) is (kind=='success')
    with pytest.raises(ValueError,match='already consumed'):job.run(root)


def test_release_with_changed_protocol_or_wrong_root_is_denied(tmp_path,monkeypatch):
    record=job.release_record().copy()
    record.update(released=True,fingerprint=job.fingerprint(),protocol_sha256='wrong',
        result_root=str(tmp_path))
    monkeypatch.setattr(job,'release_record',lambda:record)
    with pytest.raises(ValueError,match='not released'):job.release_ready(tmp_path)


def test_resource_lock_prevents_two_coordinators(tmp_path,monkeypatch):
    import fcntl
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    monkeypatch.setattr(job,'release_ready',lambda root:dict(synthetic=True))
    monkeypatch.setattr(job,'source',lambda *a:pytest.fail('Must fail at resource lock'))
    shared=tmp_path/'home/nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True)
    with shared.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):job.run(tmp_path/'root')
    assert not (tmp_path/'root/state.json').exists()


@pytest.fixture
def released_fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
    monkeypatch.setattr(job,'fingerprint',lambda:'fixture')
    root=tmp_path/'nino_research'/job.ROOT_NAME
    report=tmp_path/'tests.xml'
    report.write_text('<testsuites><testsuite tests="15" failures="0" errors="0" skipped="0">'+
        ''.join('<testcase classname="test_pi_stop_validation_runner" name="fixture%d"/>'%i for i in range(15))+
        '</testsuite></testsuites>')
    proof=tmp_path/'proof';proof.mkdir();(proof/'manifest.json').write_text('{}')
    r=dict(protocol_id=job.PROTOCOL_ID,released=True,fingerprint='fixture',hardware_authorized=False,
        training_authorized=False,allocated_physics_slots=4,scope='pi_stop6_4_launches_560_ticks_B0_no_actor',
        result_root=str(root),protocol_sha256=job.parent.sha(job.parent.frozen.repo()/'src/nino_rl/config/sim_pi_stop_validation_protocol_v1.json'),
        software_test_report=str(report),software_test_report_sha256=job.parent.sha(report),
        runner_preflight=str(proof),runner_preflight_manifest_sha256=job.parent.sha(proof/'manifest.json'))
    monkeypatch.setattr(job,'release_record',lambda:r)
    monkeypatch.setattr(preflight,'verified_report',lambda p:dict(synthetic=True))
    return root,r


def test_complete_reviewed_release_fields_are_required_without_running(tmp_path,released_fixture):
    root,record=released_fixture
    assert job.release_ready(root)==record
    assert not root.exists()


@pytest.mark.parametrize('key,value',[('training_authorized',True),('hardware_authorized',True),
    ('allocated_physics_slots',5),('fingerprint','other'),('protocol_sha256','other'),('released',False)])
def test_release_field_mutation_cannot_open_slots(released_fixture,key,value):
    root,record=released_fixture;record[key]=value
    with pytest.raises(ValueError,match='not released'):job.release_ready(root)
    assert not root.exists()


def test_modified_offline_proof_denies_release(released_fixture):
    root,record=released_fixture
    (Path(record['runner_preflight'])/'manifest.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='offline proof changed'):job.release_ready(root)


def test_failed_or_incomplete_test_report_denies_release(released_fixture):
    root,record=released_fixture
    path=Path(record['software_test_report'])
    path.write_text('<testsuites><testsuite tests="60" failures="0" errors="0" skipped="1"/></testsuites>')
    record['software_test_report_sha256']=job.parent.sha(path)
    with pytest.raises(ValueError,match='Software gate'):job.release_ready(root)
