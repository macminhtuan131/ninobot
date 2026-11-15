import hashlib,json
from pathlib import Path

import pytest
from nino_pi.sim_review import load


def test_studio_keeps_baseline_failure_and_smoke_separate_from_long_research():
    r=load();p=r['unknown_step_gazebo_integration'];q=json.loads(Path(p['report']).read_text())
    assert q['baseline_successes']==2 and q['baseline_attempts']==3
    assert q['training_transitions']==384 and not q['long_training_started']
    assert '384' in r['steps'][3]['status'] and 'SOFTWARE' in r['steps'][3]['status']


def test_integration_badge_rejects_claim_of_completed_long_training(tmp_path):
    record=dict(load()['unknown_step_gazebo_integration'])
    q=json.loads(Path(record['report']).read_text());q['long_training_started']=True
    path=tmp_path/'report.json';path.write_text(json.dumps(q))
    record.update(report=str(path),report_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    review=tmp_path/'review.json';review.write_text(json.dumps(dict(schema_version=1,unknown_step_gazebo_integration=record)))
    with pytest.raises(ValueError,match='long training'):load(review)
