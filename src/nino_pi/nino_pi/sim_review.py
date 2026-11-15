"""Read a dated Sim review, validating any linked integration result before display."""
import hashlib
import json
from pathlib import Path


def load(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name('sim_review_status.json')
    review = json.loads(path.read_text())
    if review.get('schema_version') != 1:
        raise ValueError('Unsupported Sim review schema')
    record = review.get('v2_integration')
    if record:
        report = Path(record['report'])
        actual = hashlib.sha256(report.read_bytes()).hexdigest()
        if actual != record['report_sha256']:
            raise ValueError('Integration evidence changed; review is not verified')
        data = json.loads(report.read_text())
        if data.get('status') != 'integration_pass_after_reader_correction':
            raise ValueError('Integration evidence did not pass')
        for key in ('training_transitions', 'critic_updates', 'actor_updates', 'complete_training_episodes'):
            if data[key] != record[key]:
                raise ValueError('Integration counter mismatch: ' + key)
    preparation = review.get('obstacle_authority_preparation')
    if preparation:
        protocol = Path(preparation['protocol'])
        if hashlib.sha256(protocol.read_bytes()).hexdigest() != preparation['protocol_sha256']:
            raise ValueError('Obstacle authority draft changed; preparation is not verified')
        plan = json.loads(protocol.read_text())
        if (plan.get('status') != 'prepared_not_released'
                or plan.get('release', {}).get('physics_allowed') is not False
                or plan['release'].get('allocated_attempts') != 0
                or plan['release'].get('runtime_implemented') is not False):
            raise ValueError('Obstacle preparation cannot represent an execution release')
    runtime = review.get('obstacle_authority_runtime')
    if runtime:
        path = Path(runtime['qualification'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != runtime['qualification_sha256']:
            raise ValueError('E2 runtime qualification changed')
        data = json.loads(path.read_text())
        if (data.get('status') != 'offline_e2_runtime_qualified_not_Gazebo'
                or data.get('runtime_implemented') is not True
                or data.get('allocated_attempts') != 0 or data.get('new_physics_steps') != 0
                or data['identity']['id'] != runtime['runtime_id']):
            raise ValueError('E2 offline qualification is not physics validation')
        root = Path(runtime['source_root']).resolve()
        for name, digest in data['identity']['sources']['files'].items():
            source = (root / name).resolve()
            if not source.is_relative_to(root) or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise ValueError('E2 runtime source changed: ' + name)
        tests = data['software_tests']
        if hashlib.sha256(Path(tests['path']).read_bytes()).hexdigest() != tests['sha256']:
            raise ValueError('E2 runtime software evidence changed')
    neutral = review.get('obstacle_authority_neutral')
    if neutral:
        report = Path(neutral['report'])
        if hashlib.sha256(report.read_bytes()).hexdigest() != neutral['report_sha256']:
            raise ValueError('E2 neutral result changed')
        result = json.loads(report.read_text())
        if (result.get('status') != 'neutral_slot_pass_no_benefit'
                or result.get('launches') != 1 or result.get('task_transitions') != 140
                or result.get('nonzero_residual_ticks') != 0
                or result.get('useful_body_authority_verified') is not False):
            raise ValueError('E2 neutral evidence cannot establish controller benefit')
        ledger = Path(neutral['ledger'])
        if hashlib.sha256(ledger.read_bytes()).hexdigest() != neutral['ledger_sha256']:
            raise ValueError('E2 neutral allocation evidence changed')
        state = json.loads(ledger.read_text())
        if (state.get('status') != 'allocation_exhausted'
                or state.get('allocated_attempts') != 1 or len(state.get('attempts', [])) != 1):
            raise ValueError('E2 neutral prefix is not closed')
    pair = review.get('obstacle_authority_first_pair')
    if pair:
        report = Path(pair['report'])
        if hashlib.sha256(report.read_bytes()).hexdigest() != pair['report_sha256']:
            raise ValueError('E2 first-pair evidence changed')
        data = json.loads(report.read_text())
        if (data.get('status') != 'first_pair_eligible_for_next_declared_condition_not_benefit'
                or data.get('slots') != ['E2-01', 'E2-02']
                or data.get('task_transitions') != 280
                or data.get('consumed_attempts') != 2 or data.get('allocated_attempts') != 2
                or data.get('pair_comparable') is not True
                or data.get('useful_body_authority_verified') is not True
                or data.get('benefit_verified') is not False
                or data.get('next_allocation') != 0):
            raise ValueError('E2 first pair cannot establish general controller benefit or release')
        contract = Path(data['contract'])
        if hashlib.sha256(contract.read_bytes()).hexdigest() != data['contract_sha256']:
            raise ValueError('E2 first-pair comparison contract changed')
        ledger = Path(pair['ledger'])
        if hashlib.sha256(ledger.read_bytes()).hexdigest() != pair['ledger_sha256']:
            raise ValueError('E2 first-pair allocation evidence changed')
        state = json.loads(ledger.read_text())
        if (state.get('status') != 'allocation_exhausted'
                or state.get('allocated_attempts') != 2
                or [a.get('slot', {}).get('id') for a in state.get('attempts', [])] != ['E2-01', 'E2-02']
                or any(not a.get('reviewed_summary_sha256') for a in state['attempts'])):
            raise ValueError('E2 first-pair allocation is not closed and reviewed')
    cell = review.get('obstacle_authority_first_cell')
    if cell:
        report = Path(cell['report'])
        if hashlib.sha256(report.read_bytes()).hexdigest() != cell['report_sha256']:
            raise ValueError('E2 first-cell evidence changed')
        result = json.loads(report.read_text())
        allowed = {'first_cell_action_ranking_supported_no_benefit',
                   'unknown_conflicting_wheel_source_timestamp',
                   'unknown_preintervention_approach_caliper_exceeded',
                   'unknown_support_or_sampling_ranking_conflict',
                   'first_cell_does_not_pass_authority_or_task_gate'}
        if (result.get('status') not in allowed or result.get('status') != cell['verdict']
                or result.get('slots') != ['E2-01', 'E2-02', 'E2-03']
                or result.get('allocated_attempts') != 3 or result.get('consumed_attempts') != 3
                or result.get('task_transitions') != 420 or result.get('benefit_verified') is not False
                or result.get('next_allocation') != 0 or result.get('optimizer_updates') != 0
                or result.get('hardware_actions') != 0):
            raise ValueError('E2 first-cell badge overclaims results or allocation')
        if (result['status'] == 'first_cell_action_ranking_supported_no_benefit'
                and (result.get('pairwise_comparable') is not True
                     or result.get('ranking_consistent') is not True
                     or result.get('useful_positive_authority_verified') is not True)):
            raise ValueError('E2 action ranking requires comparable supported authority')
        contract = Path(result['contract'])
        if hashlib.sha256(contract.read_bytes()).hexdigest() != result['contract_sha256']:
            raise ValueError('E2 first-cell contract changed')
        ledger = Path(cell['ledger'])
        if hashlib.sha256(ledger.read_bytes()).hexdigest() != cell['ledger_sha256']:
            raise ValueError('E2 first-cell allocation evidence changed')
        state = json.loads(ledger.read_text())
        if (state.get('status') != 'allocation_exhausted' or state.get('allocated_attempts') != 3
                or [a.get('slot', {}).get('id') for a in state.get('attempts', [])] != result['slots']
                or any(not a.get('reviewed_summary_sha256') for a in state['attempts'])):
            raise ValueError('E2 first-cell allocation is not closed and reviewed')
    corrected = review.get('obstacle_authority_timestamp_reanalysis')
    if corrected:
        def verified_json(path, expected, label):
            path = Path(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('E2 corrected ' + label + ' changed')
            return json.loads(path.read_text())
        data = verified_json(corrected['report'], corrected['report_sha256'], 'report')
        allowed = {'first_cell_action_ranking_supported_no_benefit',
                   'unknown_preintervention_approach_caliper_exceeded',
                   'unknown_support_or_sampling_ranking_conflict',
                   'first_cell_does_not_pass_authority_or_task_gate'}
        if (data.get('analysis_id') != 'nino_e2_ambiguity_query_review_v2'
                or data.get('status') not in allowed or data.get('status') != corrected['verdict']
                or data.get('analysis_correction_applied') is not True
                or data.get('primary_metrics_unchanged') is not True
                or data.get('unambiguous_first_pair_parity_verified') is not True
                or data.get('original_unknown_retained') is not True
                or data.get('task_transitions_reused') != 420
                or data.get('benefit_verified') is not False
                or any(data.get(k) != 0 for k in ('new_physics_steps','new_allocated_attempts','optimizer_updates','hardware_actions','next_allocation'))):
            raise ValueError('E2 corrected report overclaims results or release')
        if (data['status'] == 'first_cell_action_ranking_supported_no_benefit'
                and (data.get('pairwise_comparable') is not True or data.get('ranking_consistent') is not True
                     or data.get('useful_positive_authority_verified') is not True
                     or data.get('unsupported_authority_queries') != {'negative':0,'positive':0})):
            raise ValueError('E2 corrected success lacks supported authority')
        old = verified_json(data['original_unknown_report'],data['original_unknown_report_sha256'],'original unknown')
        if old.get('status') != 'unknown_conflicting_wheel_source_timestamp':
            raise ValueError('E2 original unknown evidence was replaced')
        contract = verified_json(data['contract'],data['contract_sha256'],'contract')
        if (contract.get('status') != 'offline_review_only' or contract.get('correction_index') != 1
                or contract.get('correction_budget') != 1
                or any(contract.get(k) != 0 for k in ('new_physics_steps','new_allocated_attempts','next_allocation'))):
            raise ValueError('E2 correction contract cannot allocate physics')
        source_root = Path(corrected['source_root']).resolve()
        for name,digest in contract['sources'].items():
            path = (source_root/name).resolve()
            if not path.is_relative_to(source_root) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('E2 corrected reader source changed')
        for key in ('reader_tests','regression_tests'):
            if hashlib.sha256(Path(contract[key]).read_bytes()).hexdigest() != contract[key+'_sha256']:
                raise ValueError('E2 correction software evidence changed')
        verified_json(data['query_support'],data['query_support_sha256'],'query support')
        verified_json(data['ambiguities'],data['ambiguities_sha256'],'ambiguities')
        state = verified_json(corrected['ledger'],contract['ledger_sha256'],'ledger')
        if (state.get('status') != 'allocation_exhausted' or state.get('allocated_attempts') != 3
                or [a.get('slot',{}).get('id') for a in state.get('attempts',[])] != ['E2-01','E2-02','E2-03']):
            raise ValueError('E2 correction must retain the closed three-slot allocation')
    stop8 = review.get('obstacle_authority_stop8')
    if stop8:
        def checked_json(path,digest,label):
            path=Path(path)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('E2 stop8 '+label+' changed')
            return json.loads(path.read_text())
        result=checked_json(stop8['report'],stop8['report_sha256'],'report')
        allowed={'unknown_stop8_approach_caliper','unknown_stop8_support_or_sampling',
                 'stop8_does_not_pass_authority_or_task_gate','stop8_cell_candidate_for_block1_not_benefit',
                 'stop8_cell_no_profile_advances'}
        if (result.get('status') not in allowed or result.get('status')!=stop8['verdict']
                or result.get('stop_s')!=8. or result.get('block')!=0 or result.get('control')!='E2-05'
                or result.get('allocated_attempts')!=6 or result.get('inherited_consumed_attempts')!=3
                or result.get('benefit_verified') is not False
                or any(result.get(k)!=0 for k in ('optimizer_updates','hardware_actions','next_allocation'))):
            raise ValueError('E2 stop8 report overclaims scope or release')
        closure=checked_json(stop8['closure'],stop8['closure_sha256'],'closure')
        consumed=closure.get('consumed_attempts')
        if (closure.get('status')!='stop8_allocation_closed' or closure.get('allocated_attempts')!=6
                or consumed not in (5,6) or closure.get('scientific_status')!=result['status']
                or closure.get('scientific_report_sha256')!=stop8['report_sha256']
                or closure.get('next_allocation')!=0
                or result.get('new_task_transitions')!=(consumed-3)*140
                or result.get('slots')!=[f'E2-0{i}' for i in range(4,consumed+1)]
                or closure.get('cancelled_unused_allocated_slots')!=[f'E2-0{i}' for i in range(consumed+1,7)]):
            raise ValueError('E2 stop8 closure/count mismatch')
        if result['status']=='stop8_cell_candidate_for_block1_not_benefit':
            authorities=result.get('authorities',{})
            if (consumed!=6 or result.get('pairwise_comparable') is not True
                    or result.get('ranking_consistent') is not True
                    or not result.get('descriptive_performance_eligible_profiles')
                    or set(authorities)!={'negative','positive'}
                    or any(v.get('supported') is not True or v.get('descriptive_chain_persistence_pass') is not True
                           for v in authorities.values())):
                raise ValueError('E2 stop8 candidate lacks supported authority')
        contract=checked_json(result['contract'],result['contract_sha256'],'contract')
        source_root=Path(stop8['source_root'])
        for name,key in (('causal_source_support.py','reader_source_sha256'),
                         ('obstacle_authority_review_v2.py','review_source_sha256')):
            if hashlib.sha256((source_root/'src/nino_rl/nino_rl'/name).read_bytes()).hexdigest()!=contract[key]:
                raise ValueError('E2 stop8 frozen reader changed')
        checked_json(result['query_support'],result['query_support_sha256'],'query support')
        state=checked_json(stop8['ledger'],closure['ledger_sha256'],'ledger')
        if (state.get('status') not in ('allocation_exhausted','closed_stop8_unknown','closed_stop8_no_go')
                or state.get('allocated_attempts')!=6
                or [a.get('slot',{}).get('id') for a in state.get('attempts',[])]!=[f'E2-0{i}' for i in range(1,consumed+1)]
                or any(a.get('reviewed_summary_sha256')!=a.get('summary_sha256')
                       or not a.get('summary_sha256') for a in state['attempts'])):
            raise ValueError('E2 stop8 ledger not closed/reviewed')
    sampling = review.get('obstacle_authority_sampling_audit')
    if sampling:
        def pinned_json(path, digest):
            path = Path(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('E2 sampling audit evidence changed')
            return json.loads(path.read_text())
        result = pinned_json(sampling['report'], sampling['report_sha256'])
        if (result.get('analysis_id') != 'nino_stop8_native_gt_phase_audit_v1_2026_11_09'
                or result.get('status') != 'sampling_sensitive_unknown_retain_classical_close_promotion'
                or result.get('source_equation_verified') is not True
                or result.get('auxiliary_all_queries_supported') is not True
                or result.get('original_primary_unchanged') is not True
                or result.get('original_stop8_status') != 'unknown_stop8_support_or_sampling'
                or result.get('benefit_verified') is not False
                or any(result.get(k) != 0 for k in ('new_physics_steps', 'new_allocated_attempts',
                                                   'optimizer_updates', 'hardware_actions', 'next_allocation'))):
            raise ValueError('E2 sampling audit cannot promote or allocate training')
        contract = pinned_json(result['contract'], result['contract_sha256'])
        if contract.get('status') != 'offline_only' or contract.get('pair') != ['E2-05', 'E2-06']:
            raise ValueError('E2 sampling diagnostic is not an execution contract')
        for name, digest in contract['pins'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                raise ValueError('E2 sampling audit pinned input changed: ' + name)
        timing = pinned_json(sampling['timing_summary'], sampling['timing_summary_sha256'])
        for slot in ('E2-05', 'E2-06'):
            eq = result['runs'][slot]['equation']
            if (eq.get('rows') != 140 or eq.get('failed_steps') != []
                    or eq.get('pass_equation_and_source') is not True
                    or timing[slot].get('error_mismatch_count') != 0
                    or timing[slot].get('auxiliary_supported') != 30
                    or timing[slot].get('auxiliary_body_source_matches_native') is not True):
                raise ValueError('E2 sampling audit lacks native/GT equation parity')
    motion = review.get('motion_quality_preparation')
    if motion:
        def pinned_motion(path, digest):
            path=Path(path)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('Motion-quality preparation evidence changed')
            return json.loads(path.read_text())
        q=pinned_motion(motion['qualification'],motion['qualification_sha256'])
        if (q.get('status')!='offline_motion_quality_preparation_only'
                or q.get('protocol_id')!='nino_known_route_motion_quality_draft_v1_2026_11_09'
                or any(q.get(k) is not False for k in ('objective_accepted','thresholds_accepted',
                    'runtime_implemented','benefit_verified','actual_time_matching_verified'))
                or any(q.get(k)!=0 for k in ('new_physics_steps','new_allocated_attempts',
                    'optimizer_updates','hardware_actions','next_allocation'))):
            raise ValueError('Motion-quality draft cannot claim execution or acceptance')
        from nino_rl.motion_quality_draft import load as load_motion
        p=load_motion(q['protocol'])
        if hashlib.sha256(Path(q['protocol']).read_bytes()).hexdigest()!=q['protocol_sha256']:
            raise ValueError('Motion-quality protocol changed')
        if (q.get('proposed_attempts')!=len(p['proposed_attempts'])
                or q.get('proposed_task_ticks')!=p['proposed_budget']['task_ticks_max']):
            raise ValueError('Motion-quality proposed counts changed')
        root=Path(q['source_root']).resolve()
        for name,digest in q['sources'].items():
            source=(root/name).resolve()
            if not source.is_relative_to(root) or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
                raise ValueError('Motion-quality prepared software changed')
        if hashlib.sha256(Path(q['fixture_tests']).read_bytes()).hexdigest()!=q['fixture_tests_sha256']:
            raise ValueError('Motion-quality fixture evidence changed')
        analytic=pinned_motion(q['analytic_reference'],q['analytic_reference_sha256'])
        if analytic.get('status')!='analytic_reference_only_not_body_response' or analytic.get('actual_time_matching_verified') is not False:
            raise ValueError('Reference timing is not measured body timing')
        pinned_motion(q['historical_audit_manifest'],q['historical_audit_manifest_sha256'])
        ledger=pinned_motion(q['old_closed_ledger'],q['old_closed_ledger_sha256'])
        if ledger.get('status')!='allocation_exhausted' or ledger.get('allocated_attempts')!=6:
            raise ValueError('Prior E2 allocation must remain closed')
    unknown = review.get('unknown_step_task_selection')
    if unknown:
        path=Path(unknown['protocol'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=unknown['protocol_sha256']:
            raise ValueError('Unknown-step selected task changed')
        from nino_rl import unknown_step_task
        if hashlib.sha256(Path(unknown_step_task.__file__).read_bytes()).hexdigest()!=unknown['module_sha256']:
            raise ValueError('Unknown-step task validator changed')
        selected=unknown_step_task.load(path)
        if (selected['objective']['user_selected'] is not True
                or selected['controller_information']['obstacle_preview'] is not False
                or selected['controller_information']['privileged_contact_trigger'] is not False
                or selected['supersedes']['known_route_motion_quality_active'] is not False):
            raise ValueError('Unknown-step task cannot display the superseded preview goal')
    prepared = review.get('unknown_step_software_preparation')
    if prepared:
        import xml.etree.ElementTree as ET
        path = Path(prepared['qualification'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != prepared['qualification_sha256']:
            raise ValueError('Unknown-step software qualification changed')
        qualification = json.loads(path.read_text())
        gates = qualification.get('gates', {})
        if (qualification.get('status') != 'software_prepared_not_gazebo_integrated'
                or gates != dict(software_fixture_pass=True, gazebo_integration_verified=False,
                                 training_released=False, hardware_authorized=False)
                or qualification.get('new_physics_launches') != 0
                or qualification.get('new_optimizer_updates') != 0):
            raise ValueError('Unknown-step software badge cannot imply Gazebo/training release')
        root = Path(qualification['source_root']).resolve()
        for name, expected in qualification['sources'].items():
            source = (root / name).resolve()
            if not source.is_relative_to(root) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError('Unknown-step prepared source changed: ' + name)
        report = Path(qualification['fixture_report'])
        if hashlib.sha256(report.read_bytes()).hexdigest() != qualification['fixture_report_sha256']:
            raise ValueError('Unknown-step fixture report changed')
        suites = list(ET.parse(report).getroot().iter('testsuite'))
        tests = sum(int(s.get('tests', 0)) for s in suites)
        problems = sum(int(s.get(k, 0)) for s in suites for k in ('failures', 'errors', 'skipped'))
        if tests != qualification['tests_passed'] or tests <= 0 or problems:
            raise ValueError('Unknown-step fixture tests incomplete or failed')
    integrated = review.get('unknown_step_gazebo_integration')
    if integrated:
        path=Path(integrated['report'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=integrated['report_sha256']:
            raise ValueError('Goal100 Gazebo integration report changed')
        result=json.loads(path.read_text())
        if (result.get('status')!='integrated_smoke_complete_not_benefit'
                or result.get('training_transitions')!=384 or result.get('critic_updates')!=368
                or result.get('actor_updates')!=184 or result.get('hash_mismatches')!=0
                or result.get('baseline_successes')!=2 or result.get('baseline_attempts')!=3
                or result.get('benefit_verified') is not False
                or result.get('long_training_started') is not False or result.get('hardware_actions')!=0):
            raise ValueError('Goal100 integration cannot imply promotion, clean 3/3 baseline, or long training')
        root=Path(integrated['source_root']).resolve()
        for name,expected in integrated['sources'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Goal100 integration source changed: '+name)
    return review
