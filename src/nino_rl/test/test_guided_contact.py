"""Finite contact screen orchestration, without physics or optimizer."""
import json
import pytest
from nino_rl import residual_guided_contact as contact

def test_fixed_budget_and_frozen_parent_settings():
    p = contact.protocol()
    assert len(p['order']) == 4 and p['maximum_transitions'] == 560
    assert p['training_transitions'] == 0 and p['hardware_actions'] == 0
    assert all(r['arm']=='guided' and r['path_bearing_deg']==0 for r in p['order'])

def test_failure_closes_remaining_slots_instead_of_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(contact, 'prepare_worlds', lambda out: {'clear_box':'clear', 'box_c1_6mm':'c1'})
    calls = []
    def rollout(out, p, condition, world):
        calls.append(condition)
        return dict(physical_failure=False, guidance_faults=0, steps=140,
                    functional_proposal_pass=condition['scenario']=='clear_box')
    monkeypatch.setattr(contact, 'rollout', rollout)
    r = contact.evaluate(tmp_path, contact.protocol())
    assert len(calls)==2 and r['completed_runs']==2 and r['closed_unused_slots']==2
    assert not r['baseline_functional_candidate'] and r['training_transitions']==0
    assert r['closure_reason']=='functional_gate_failure_remaining_slots_closed'

def test_physical_failure_is_not_a_completed_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(contact, 'prepare_worlds', lambda out: {'clear_box':'clear'})
    monkeypatch.setattr(contact, 'rollout', lambda *args: dict(physical_failure=True, guidance_faults=0, steps=20))
    with pytest.raises(RuntimeError, match='no retry'):
        contact.evaluate(tmp_path, contact.protocol())
    assert not (tmp_path/'evaluation_result.json').exists()

def test_closed_root_cannot_reopen(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path/'isolated_home'))
    (tmp_path/'state.json').write_text(json.dumps(dict(runs=[])))
    with pytest.raises(ValueError, match='already closed'):
        contact.run(tmp_path)
