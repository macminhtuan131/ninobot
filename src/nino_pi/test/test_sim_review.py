"""New integration counts need hash-verified evidence, not a hard-coded green badge."""
import hashlib
import json
import pytest
from nino_pi.sim_review import load


def test_integration_review_requires_unchanged_result_and_exact_counters(tmp_path):
    report=tmp_path/'evaluation.json'
    actual=dict(status='integration_pass_after_reader_correction',training_transitions=280,
                critic_updates=264,actor_updates=132,complete_training_episodes=2)
    report.write_text(json.dumps(actual))
    record={k:v for k,v in actual.items() if k!='status'}
    record.update(report=str(report),report_sha256=hashlib.sha256(report.read_bytes()).hexdigest())
    path=tmp_path/'review.json'
    review=dict(schema_version=1,v2_integration=record)
    path.write_text(json.dumps(review))
    assert load(path)['v2_integration']['training_transitions']==280
    report.write_text('{}')
    with pytest.raises(ValueError,match='changed'):
        load(path)
    report.write_text(json.dumps(actual))
    record['training_transitions']=281
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError,match='counter mismatch'):
        load(path)


def test_obstacle_preparation_is_hash_verified_and_never_a_release(tmp_path):
    protocol=tmp_path/'protocol.json'
    plan=dict(status='prepared_not_released',release=dict(physics_allowed=False,
              allocated_attempts=0,runtime_implemented=False))
    protocol.write_text(json.dumps(plan))
    path=tmp_path/'review.json'
    record=dict(protocol=str(protocol),protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest())
    review=dict(schema_version=1,obstacle_authority_preparation=record)
    path.write_text(json.dumps(review))
    assert load(path)['obstacle_authority_preparation']==record
    protocol.write_text('{}')
    with pytest.raises(ValueError,match='changed'):
        load(path)
    plan['release']['physics_allowed']=True
    protocol.write_text(json.dumps(plan))
    record['protocol_sha256']=hashlib.sha256(protocol.read_bytes()).hexdigest()
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError,match='execution release'):
        load(path)


def test_runtime_offline_badge_requires_current_software_and_source_hashes(tmp_path):
    source=tmp_path/'runner.py';source.write_text('fixture only')
    tests=tmp_path/'tests.xml';tests.write_text('<testsuites/>')
    qualification=tmp_path/'qualification.json'
    data=dict(status='offline_e2_runtime_qualified_not_Gazebo',runtime_implemented=True,
        allocated_attempts=0,new_physics_steps=0,identity=dict(id='fixture',sources=dict(files={
            source.name:hashlib.sha256(source.read_bytes()).hexdigest()})),
        software_tests=dict(path=str(tests),sha256=hashlib.sha256(tests.read_bytes()).hexdigest()))
    qualification.write_text(json.dumps(data))
    record=dict(qualification=str(qualification),qualification_sha256=hashlib.sha256(qualification.read_bytes()).hexdigest(),
                runtime_id='fixture',source_root=str(tmp_path))
    path=tmp_path/'review.json';path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_runtime=record)))
    assert load(path)['obstacle_authority_runtime']==record
    source.write_text('changed')
    with pytest.raises(ValueError,match='source changed'):load(path)
    source.write_text('fixture only');tests.write_text('changed')
    with pytest.raises(ValueError,match='software evidence changed'):load(path)
    tests.write_text('<testsuites/>');data['new_physics_steps']=1
    qualification.write_text(json.dumps(data))
    record['qualification_sha256']=hashlib.sha256(qualification.read_bytes()).hexdigest()
    path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_runtime=record)))
    with pytest.raises(ValueError,match='not physics validation'):load(path)


def test_neutral_badge_requires_closed_single_slot_and_no_benefit_claim(tmp_path):
    report=tmp_path/'evaluation.json';ledger=tmp_path/'ledger.json'
    result=dict(status='neutral_slot_pass_no_benefit',launches=1,task_transitions=140,
                nonzero_residual_ticks=0,useful_body_authority_verified=False)
    report.write_text(json.dumps(result))
    ledger.write_text(json.dumps(dict(status='allocation_exhausted',allocated_attempts=1,attempts=[{}])))
    record=dict(report=str(report),report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
                ledger=str(ledger),ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest())
    path=tmp_path/'review.json';path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_neutral=record)))
    assert load(path)['obstacle_authority_neutral']==record
    ledger.write_text('{}')
    with pytest.raises(ValueError,match='allocation evidence changed'):load(path)
    record['ledger_sha256']=hashlib.sha256(ledger.read_bytes()).hexdigest()
    path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_neutral=record)))
    with pytest.raises(ValueError,match='not closed'):load(path)
    result['useful_body_authority_verified']=True;report.write_text(json.dumps(result))
    record['report_sha256']=hashlib.sha256(report.read_bytes()).hexdigest()
    path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_neutral=record)))
    with pytest.raises(ValueError,match='cannot establish controller benefit'):load(path)


@pytest.mark.parametrize('fault', ['report_hash', 'benefit_claim', 'allocation', 'contract_hash', 'unreviewed'])
def test_first_pair_badge_rejects_stale_or_overclaimed_evidence(tmp_path, fault):
    report, ledger, contract = [tmp_path / name for name in ('pair.json', 'ledger.json', 'contract.json')]
    contract.write_text('{}')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(status='first_pair_eligible_for_next_declared_condition_not_benefit',
        slots=['E2-01', 'E2-02'], task_transitions=280, consumed_attempts=2,
        allocated_attempts=2, pair_comparable=True, useful_body_authority_verified=True,
        benefit_verified=False, next_allocation=0, contract=str(contract), contract_sha256=digest(contract))
    state = dict(status='allocation_exhausted', allocated_attempts=2,
        attempts=[dict(slot=dict(id=k), reviewed_summary_sha256='fixture') for k in ('E2-01', 'E2-02')])
    report.write_text(json.dumps(result)); ledger.write_text(json.dumps(state))
    record = dict(report=str(report), report_sha256=digest(report), ledger=str(ledger), ledger_sha256=digest(ledger))
    path = tmp_path / 'review.json'
    def write(): path.write_text(json.dumps(dict(schema_version=1, obstacle_authority_first_pair=record)))
    write()
    assert load(path)['obstacle_authority_first_pair'] == record
    if fault == 'report_hash': report.write_text('{}')
    elif fault == 'contract_hash': contract.write_text('changed')
    elif fault == 'unreviewed':
        state['attempts'][1].pop('reviewed_summary_sha256')
        ledger.write_text(json.dumps(state)); record['ledger_sha256'] = digest(ledger)
    else:
        result['benefit_verified' if fault == 'benefit_claim' else 'next_allocation'] = True if fault == 'benefit_claim' else 1
        report.write_text(json.dumps(result)); record['report_sha256'] = digest(report)
    write()
    with pytest.raises(ValueError): load(path)


@pytest.mark.parametrize('fault', ['report_hash', 'false_success', 'allocation', 'unreviewed', 'contract_hash'])
def test_first_cell_unknown_is_retained_and_cannot_be_shown_as_success(tmp_path, fault):
    report,ledger,contract=[tmp_path/name for name in ('cell.json','ledger.json','contract.json')]
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    contract.write_text('{}')
    result=dict(status='unknown_preintervention_approach_caliper_exceeded',slots=['E2-01','E2-02','E2-03'],
        allocated_attempts=3,consumed_attempts=3,task_transitions=420,benefit_verified=False,next_allocation=0,
        optimizer_updates=0,hardware_actions=0,pairwise_comparable=False,ranking_consistent=True,
        useful_positive_authority_verified=False,contract=str(contract),contract_sha256=digest(contract))
    state=dict(status='allocation_exhausted',allocated_attempts=3,
        attempts=[dict(slot=dict(id=k),reviewed_summary_sha256='fixture') for k in result['slots']])
    report.write_text(json.dumps(result));ledger.write_text(json.dumps(state))
    record=dict(report=str(report),report_sha256=digest(report),ledger=str(ledger),ledger_sha256=digest(ledger),verdict=result['status'])
    path=tmp_path/'review.json'
    def write():path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_first_cell=record)))
    write();assert load(path)['obstacle_authority_first_cell']['verdict'].startswith('unknown')
    if fault=='report_hash':report.write_text('{}')
    elif fault=='contract_hash':contract.write_text('changed')
    elif fault=='unreviewed':
        state['attempts'][2].pop('reviewed_summary_sha256');ledger.write_text(json.dumps(state));record['ledger_sha256']=digest(ledger)
    else:
        if fault=='false_success':
            result['status']='first_cell_action_ranking_supported_no_benefit';record['verdict']=result['status']
        else:result['next_allocation']=1
        report.write_text(json.dumps(result));record['report_sha256']=digest(report)
    write()
    with pytest.raises(ValueError):load(path)


@pytest.mark.parametrize('fault',['report_hash','reader_source','original_unknown','contract','physics_claim','false_authority','ledger'])
def test_corrected_offline_badge_preserves_unknown_and_rejects_tamper(tmp_path,fault):
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    def write(name,data):
        p=tmp_path/name;p.write_text(json.dumps(data));return p
    unknown=write('unknown.json',dict(status='unknown_conflicting_wheel_source_timestamp'))
    source=tmp_path/'source.py';source.write_text('fixture reader')
    tests=tmp_path/'tests.xml';tests.write_text('<testsuites/>')
    support=write('support.json',{});ambiguity=write('ambiguity.json',{})
    state=dict(status='allocation_exhausted',allocated_attempts=3,
               attempts=[dict(slot=dict(id=k)) for k in ('E2-01','E2-02','E2-03')])
    ledger=write('ledger.json',state)
    plan=dict(status='offline_review_only',correction_index=1,correction_budget=1,new_physics_steps=0,
        new_allocated_attempts=0,next_allocation=0,sources={source.name:digest(source)},
        ledger_sha256=digest(ledger),reader_tests=str(tests),reader_tests_sha256=digest(tests),
        regression_tests=str(tests),regression_tests_sha256=digest(tests))
    contract=write('contract.json',plan)
    result=dict(status='first_cell_action_ranking_supported_no_benefit',analysis_id='nino_e2_ambiguity_query_review_v2',
        analysis_correction_applied=True,primary_metrics_unchanged=True,unambiguous_first_pair_parity_verified=True,
        original_unknown_retained=True,task_transitions_reused=420,benefit_verified=False,new_physics_steps=0,
        new_allocated_attempts=0,optimizer_updates=0,hardware_actions=0,next_allocation=0,pairwise_comparable=True,
        ranking_consistent=True,useful_positive_authority_verified=True,unsupported_authority_queries={'negative':0,'positive':0},
        original_unknown_report=str(unknown),original_unknown_report_sha256=digest(unknown),
        contract=str(contract),contract_sha256=digest(contract),query_support=str(support),query_support_sha256=digest(support),
        ambiguities=str(ambiguity),ambiguities_sha256=digest(ambiguity))
    report=write('evaluation.json',result)
    record=dict(report=str(report),report_sha256=digest(report),verdict=result['status'],ledger=str(ledger),source_root=str(tmp_path))
    path=write('review.json',dict(schema_version=1,obstacle_authority_timestamp_reanalysis=record))
    assert load(path)['obstacle_authority_timestamp_reanalysis']==record
    if fault=='report_hash':report.write_text('{}')
    elif fault=='reader_source':source.write_text('changed')
    elif fault=='original_unknown':unknown.write_text('{}')
    elif fault=='contract':contract.write_text('{}')
    elif fault=='ledger':ledger.write_text('{}')
    else:
        result['new_physics_steps' if fault=='physics_claim' else 'useful_positive_authority_verified']=1 if fault=='physics_claim' else False
        report.write_text(json.dumps(result));record['report_sha256']=digest(report)
        path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_timestamp_reanalysis=record)))
    with pytest.raises(ValueError):load(path)


@pytest.mark.parametrize('fault',['report_hash','false_candidate','unconsumed','closure_hash','query_hash','source_changed','ledger'])
def test_stop8_unknown_closes_at_five_and_cannot_show_full_cell_success(tmp_path,fault):
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    def write(name,data):
        p=tmp_path/name;p.write_text(json.dumps(data));return p
    modules=tmp_path/'src/nino_rl/nino_rl';modules.mkdir(parents=True)
    for name in ('causal_source_support.py','obstacle_authority_review_v2.py'):(modules/name).write_text('fixture')
    contract=write('contract.json',dict(reader_source_sha256=digest(modules/'causal_source_support.py'),
                                      review_source_sha256=digest(modules/'obstacle_authority_review_v2.py')))
    queries=write('queries.json',{})
    result=dict(status='unknown_stop8_approach_caliper',stop_s=8.,block=0,control='E2-05',allocated_attempts=6,
        inherited_consumed_attempts=3,benefit_verified=False,optimizer_updates=0,hardware_actions=0,next_allocation=0,
        new_task_transitions=280,slots=['E2-04','E2-05'],contract=str(contract),contract_sha256=digest(contract),
        query_support=str(queries),query_support_sha256=digest(queries))
    report=write('report.json',result)
    ledger=write('ledger.json',dict(status='closed_stop8_unknown',allocated_attempts=6,
        attempts=[dict(slot=dict(id=f'E2-0{i}'),summary_sha256='fixture',reviewed_summary_sha256='fixture') for i in range(1,6)]))
    closing=dict(status='stop8_allocation_closed',allocated_attempts=6,consumed_attempts=5,
        scientific_status=result['status'],scientific_report_sha256=digest(report),next_allocation=0,
        cancelled_unused_allocated_slots=['E2-06'],ledger_sha256=digest(ledger))
    closure=write('closure.json',closing)
    record=dict(report=str(report),report_sha256=digest(report),verdict=result['status'],
                closure=str(closure),closure_sha256=digest(closure),ledger=str(ledger),source_root=str(tmp_path))
    path=write('review.json',dict(schema_version=1,obstacle_authority_stop8=record))
    assert load(path)['obstacle_authority_stop8']['verdict'].startswith('unknown')
    if fault=='report_hash':report.write_text('{}')
    elif fault=='closure_hash':closure.write_text('{}')
    elif fault=='query_hash':queries.write_text('{"changed":true}')
    elif fault=='source_changed':(modules/'causal_source_support.py').write_text('changed')
    elif fault=='ledger':ledger.write_text('{}')
    elif fault=='unconsumed':
        result['new_task_transitions']=420;report.write_text(json.dumps(result));record['report_sha256']=digest(report)
        closing['scientific_report_sha256']=digest(report);closure.write_text(json.dumps(closing));record['closure_sha256']=digest(closure)
    else:
        result['status']='stop8_cell_candidate_for_block1_not_benefit';record['verdict']=result['status']
        report.write_text(json.dumps(result));record['report_sha256']=digest(report)
        closing['scientific_status']=result['status'];closing['scientific_report_sha256']=digest(report)
        closure.write_text(json.dumps(closing));record['closure_sha256']=digest(closure)
    path.write_text(json.dumps(dict(schema_version=1,obstacle_authority_stop8=record)))
    with pytest.raises(ValueError):load(path)
