import hashlib
import json
from pathlib import Path

import pytest

from nino_pi.sim_review import load


def test_prepared_task_is_shown_as_software_only_without_releasing_gazebo():
    r = load()
    p = r['unknown_step_software_preparation']
    q = json.loads(Path(p['qualification']).read_text())
    assert q['tests_passed'] >= 50
    assert not q['gates']['gazebo_integration_verified'] and not q['gates']['training_released']
    assert 'SOFTWARE' in r['steps'][3]['status']


def test_preparation_badge_rejects_changed_proof_or_false_execution_claim(tmp_path):
    record = dict(load()['unknown_step_software_preparation'])
    record['qualification_sha256'] = '0' * 64
    review = tmp_path / 'review.json'
    review.write_text(json.dumps(dict(schema_version=1, unknown_step_software_preparation=record)))
    with pytest.raises(ValueError):
        load(review)
    record = dict(load()['unknown_step_software_preparation'])
    q = json.loads(Path(record['qualification']).read_text())
    q['gates']['gazebo_integration_verified'] = True
    altered = tmp_path / 'qualification.json'
    altered.write_text(json.dumps(q))
    record.update(qualification=str(altered), qualification_sha256=hashlib.sha256(altered.read_bytes()).hexdigest())
    review.write_text(json.dumps(dict(schema_version=1, unknown_step_software_preparation=record)))
    with pytest.raises(ValueError, match='badge'):
        load(review)
