import json

import numpy as np
import pytest

from nino_rl import goal_checkpoint_evaluation as ev


def test_matrix_is_balanced_and_cannot_consume_reserved_worlds():
    rows=ev.matrix(ev.protocol())
    assert len(rows)==24 and rows[0]['arm']=='B0' and rows[0]['layout']=='dev_clear'
    assert len({(r['block'],r['layout'],r['arm']) for r in rows})==24
    assert {r['layout'] for r in rows}==set(ev.LAYOUTS)
    for layout in ev.LAYOUTS:
        for arm in ev.ARMS:
            matches=[r for r in rows if r['layout']==layout and r['arm']==arm]
            assert len(matches)==2 and {r['reset_seed'] for r in matches}=={701,702}


@pytest.mark.parametrize('change',[dict(raw_gap_limit_s=.06),dict(new_training_steps=1),
    dict(maximum_rollouts=25),dict(layouts=['val_mid']),dict(controller_promotion=True)])
def test_protocol_changes_cannot_silently_relax_measurement_or_training_scope(tmp_path,change):
    p=dict(ev.protocol(),**change);path=tmp_path/'changed.json';path.write_text(json.dumps(p))
    with pytest.raises(ValueError):ev.protocol(path)


class FakeEnv:
    def __init__(self,out,bank,order,**kwargs):
        assert (out/'ledger.json').exists()  # Local launch counting, including slot2+.
        self.closed=False;self.last=None
    def reset(self,seed):return np.zeros(100,np.float32),dict(physical_sample={'stamp_s':1.})
    def step(self,action):
        self.last=dict(done=True,reward=-10.,task=dict(task_success=False,termination_reason='stall',
            cross_track_rmse_m=.01,maximum_cross_track_m=.02,elapsed_s=4.))
        return np.zeros(100,np.float32),-10.,True,False,dict(task=self.last['task'])
    def close(self):self.closed=True


def test_task_failure_is_retained_as_valid_outcome_and_action_is_deterministic(tmp_path):
    class Policy:
        def predict(self,obs,deterministic):
            assert deterministic is True
            return np.zeros(1,np.float32),None
        def learn(self,*args,**kwargs):raise AssertionError('Evaluation must never optimize')
    slot=ev.matrix(ev.protocol())[1]
    r=ev.rollout(tmp_path/'slot',{},slot,Policy(),env_factory=FakeEnv,qc_factory=lambda _:dict(valid=True))
    assert r['measurement_valid'] and not r['outcome']['task_success'] and r['steps']==1
    assert json.loads((tmp_path/'slot/summary.json').read_text())['outcome']['termination_reason']=='stall'


def test_measurement_failure_is_not_a_success_or_a_replacement_trial(tmp_path):
    slot=ev.matrix(ev.protocol())[0]
    r=ev.rollout(tmp_path/'slot',{},slot,env_factory=FakeEnv,qc_factory=lambda _:dict(valid=False))
    assert r['status']=='invalid' and not r['measurement_valid']
    rows=ev.matrix(ev.protocol());rows[0]=r
    s=ev.summary(rows)
    assert s['attempts']==1 and s['measurement_valid']==0 and s['task_successes']==0
    assert s['status']=='incomplete_or_measurement_unknown'
    assert s['arms']['B0']['dev_clear']['valid']==0


def test_original_raw_qc_still_rejects_a_54ms_drive_gap(tmp_path):
    raw=tmp_path/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    raw.parent.mkdir(parents=True)
    (tmp_path/'episode_0_reset.json').write_text(json.dumps(dict(reset=dict(physical_sample=dict(stamp_s=0.)))))
    def write(drive_stamps):
        rows=[dict(channel=key,stamp_s=t) for key in ('wheel','truth','imu','drive')
              for t in (drive_stamps if key=='drive' else [0.,.02,.04,.06,.08])]
        raw.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    write([0.,.054,.074])
    assert ev.short.raw_qc(tmp_path)['valid'] is False
    write([0.,.02,.04,.06,.08])
    assert ev.short.raw_qc(tmp_path)['valid'] is True


def test_wall_deadline_closes_slot_and_propagates_instead_of_starting_more_slots(tmp_path):
    class DeadlineEnv(FakeEnv):
        def step(self,action):raise ev.EvaluationDeadline('deadline')
        def close(self):
            (tmp_path/'closed').write_text('yes')
    with pytest.raises(ev.EvaluationDeadline):
        ev.rollout(tmp_path/'slot',{},ev.matrix(ev.protocol())[0],env_factory=DeadlineEnv)
    assert (tmp_path/'closed').read_text()=='yes'
