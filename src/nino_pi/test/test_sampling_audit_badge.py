import hashlib
import json
import pytest
from nino_pi.sim_review import load


@pytest.mark.parametrize('fault', ['none', 'report_hash', 'source_pin', 'physics', 'benefit', 'equation', 'timing'])
def test_sampling_badge_preserves_unknown_and_cannot_release(tmp_path, fault):
    def write(name, data):
        p=tmp_path/name; p.write_text(json.dumps(data)); return p
    def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
    source=tmp_path/'source'; source.write_text('fixture')
    contract=write('contract.json', dict(status='offline_only', pair=['E2-05','E2-06'], pins={str(source):digest(source)}))
    eq=dict(rows=140,failed_steps=[],pass_equation_and_source=True)
    result=dict(analysis_id='nino_stop8_native_gt_phase_audit_v1_2026_11_09',
        status='sampling_sensitive_unknown_retain_classical_close_promotion',source_equation_verified=True,
        auxiliary_all_queries_supported=True,original_primary_unchanged=True,
        original_stop8_status='unknown_stop8_support_or_sampling',benefit_verified=False,
        new_physics_steps=0,new_allocated_attempts=0,optimizer_updates=0,hardware_actions=0,next_allocation=0,
        contract=str(contract),contract_sha256=digest(contract),runs={k:dict(equation=eq) for k in ('E2-05','E2-06')})
    if fault=='physics': result['new_physics_steps']=1
    if fault=='benefit': result['benefit_verified']=True
    if fault=='equation': result['runs']['E2-06']['equation']=dict(eq,failed_steps=[42])
    report=write('report.json',result)
    timing=write('timing.json',{k:dict(error_mismatch_count=0,auxiliary_supported=30,auxiliary_body_source_matches_native=True)
                              for k in ('E2-05','E2-06')})
    record=dict(report=str(report),report_sha256=digest(report),timing_summary=str(timing),timing_summary_sha256=digest(timing))
    if fault=='report_hash':report.write_text('{}')
    if fault=='source_pin':source.write_text('changed')
    if fault=='timing':timing.write_text('{}')
    path=write('review.json',dict(schema_version=1,obstacle_authority_sampling_audit=record))
    if fault=='none':assert load(path)['obstacle_authority_sampling_audit']==record
    else:
        with pytest.raises(ValueError):load(path)
