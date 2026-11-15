import json
from pathlib import Path
import pytest
from nino_pi.sim_review import load


def test_active_direction_uses_user_goal_and_keeps_preview_only_as_history():
    r=load()
    assert 'unknown_step_task_selection' in r
    assert 'motion_quality_preparation' in r  # Preserved historical evidence.
    assert 'không biết trước' in r['summary']
    assert 'VƯỢT GỜ' in r['steps'][3]['name']
    assert r['document']=='docs/NINO_UNKNOWN_STEP_TASK_DIRECTION_2026-11-09.md'


def test_gui_does_not_accept_changed_task_or_validator(tmp_path):
    record=load()['unknown_step_task_selection']
    for field in ('protocol_sha256','module_sha256'):
        altered=dict(record);altered[field]='0'*64
        path=tmp_path/'review.json';path.write_text(json.dumps(dict(schema_version=1,unknown_step_task_selection=altered)))
        with pytest.raises(ValueError):load(path)
