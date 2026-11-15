import hashlib
import json
from pathlib import Path
import pytest
from nino_pi.sim_review import load


@pytest.mark.parametrize('fault',['none','report_hash','physics','runtime','acceptance','analytic'])
def test_new_design_does_not_reopen_old_allocation_or_claim_measured_timing(tmp_path,fault):
    current=load()['motion_quality_preparation']
    q=json.loads(Path(current['qualification']).read_text())
    if fault=='physics':q['new_physics_steps']=1
    if fault=='runtime':q['runtime_implemented']=True
    if fault=='acceptance':q['objective_accepted']=True
    if fault=='analytic':
        a=json.loads(Path(q['analytic_reference']).read_text());a['actual_time_matching_verified']=True
        p=tmp_path/'analytic.json';p.write_text(json.dumps(a))
        q['analytic_reference']=str(p);q['analytic_reference_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    p=tmp_path/'qualification.json';p.write_text(json.dumps(q))
    record=dict(qualification=str(p),qualification_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    if fault=='report_hash':p.write_text('{}')
    review=tmp_path/'review.json';review.write_text(json.dumps(dict(schema_version=1,motion_quality_preparation=record)))
    if fault=='none':assert load(review)['motion_quality_preparation']==record
    else:
        with pytest.raises(ValueError):load(review)
