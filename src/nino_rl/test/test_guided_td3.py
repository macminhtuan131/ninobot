"""V3 reward/action/checkpoint semantics, without ROS/Gazebo collection."""
from copy import deepcopy
import json
import numpy as np
import pytest
from nino_rl import residual_guided_td3 as task
from nino_rl.guided_td3_contract import zero_initialize, LearningScore, require_identity, audit_replay


def model_fixture():
    import gymnasium as gym
    from stable_baselines3 import TD3
    class NoStep(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,(100,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,(2,),dtype=np.float32)
        def reset(self,**kwargs):raise AssertionError('No fixture collection')
        def step(self,action):raise AssertionError('No fixture collection')
    return TD3('MlpPolicy',NoStep(),seed=7,policy_kwargs={'net_arch':[32,32]},buffer_size=32,device='cpu')


def info_fixture():
    return dict(truth_pose_m_rad=[0.,0.,0.],body_speed_m_s=.1,body_yaw_rad_s=.02,
        body_speed_norm_m_s=.1,feedback_wheel_rad_s=[1.,1.],estimator_audit={'pose':[0.,0.,0.]},
        reference_trace={'original_baseline_body':[.2,0.], 'accepted_reference_wheel_m_s':[.1,.1]})


def score():
    c,_,p,condition=task.configuration()
    return LearningScore(c,p,condition,task.protocol()['reward'])


def test_zero_head_preserves_critic_trunk_and_syncs_target():
    import torch
    model=model_fixture()
    critic=[p.detach().clone() for p in model.critic.parameters()]
    trunk=[p.detach().clone() for p in model.actor.mu[:4].parameters()]
    with torch.no_grad():next(model.actor_target.parameters()).add_(1.)
    zero_initialize(model)
    for a,b in zip(critic,model.critic.parameters()):assert torch.equal(a,b)
    for a,b in zip(trunk,model.actor.mu[:4].parameters()):assert torch.equal(a,b)
    observations=torch.as_tensor(np.random.default_rng(1).uniform(-5,5,(32,100)),dtype=torch.float32)
    with torch.no_grad():
        assert not torch.count_nonzero(model.actor(observations))
        assert not torch.count_nonzero(model.actor_target(observations))
    assert model._n_updates==0 and model.num_timesteps==0
    with pytest.raises(ValueError,match='fresh'):zero_initialize(model)


def test_zero_init_rejects_trained_model_and_roundtrip_keeps_identity(tmp_path):
    from stable_baselines3 import TD3
    model=model_fixture();model._n_updates=1
    with pytest.raises(ValueError,match='fresh'):zero_initialize(model)
    model._n_updates=0;zero_initialize(model);model.nino_guided_task=task.identity()
    model.save(tmp_path/'model.zip');loaded=TD3.load(tmp_path/'model.zip',device='cpu')
    require_identity(loaded.nino_guided_task,task.identity())
    np.testing.assert_array_equal(loaded.predict(np.ones(100,np.float32))[0],[0.,0.])
    wrong=deepcopy(task.identity());wrong['baseline_id']='V2_same_ABI'
    with pytest.raises(ValueError,match='identity mismatch'):require_identity(wrong,task.identity())


def test_reward_uses_nominal_not_accepted_policy_reference():
    a,b=info_fixture(),info_fixture()
    b['reference_trace']['accepted_reference_wheel_m_s']=[.2,.2]
    ra,ta=score().update(a,[0.,0.],4.,False)
    rb,tb=score().update(b,[0.,0.],4.,False)
    assert ra==rb and ta['nominal_shaped_body']==tb['nominal_shaped_body']
    assert 'progress' not in ta['reward_terms'] and ta['reward_terms']['velocity_tracking']<0


def test_proposal_cost_survives_projection_and_failure_penalties_are_preserved():
    r,info=score().update(info_fixture(),[.5,-.2],14.,True)
    terms=info['reward_terms']
    assert terms['action_size']<0 and terms['action_change']<0
    assert terms['physical_failure']==-10. and terms['missing_marker']==-5. and terms['not_stopped']==-10.
    assert r==sum(terms.values()) and not info['task_success']


def test_task_deadline_is_terminal_not_timeout(monkeypatch):
    import gymnasium as gym
    class Inner(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,(100,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,(2,),dtype=np.float32)
        def reset(self,**kwargs):return np.zeros(100,np.float32),{}
        def step(self,a):return np.zeros(100,np.float32),0.,False,True,info_fixture()
    monkeypatch.setattr(task,'make_environment',lambda *args:Inner())
    c,_,p,condition=task.configuration();env=task.environment(c,object(),p,condition)
    env.reset();env.steps=139
    _,_,terminal,truncated,info=env.step(np.zeros(2))
    assert terminal and not truncated and info['termination_reason']=='task_deadline_failure'
    assert info['reward_terms']['not_stopped']==-10.


def test_replay_keeps_requested_action_not_projected_reference():
    from types import SimpleNamespace
    row=dict(policy_proposal=[.7,-.4],reference_trace={'observation':[0.,0.], 'accepted_policy_delta_wheel_m_s':[.01,0.]},
        next_observation=[1.,0.],reward=-1.,done=True,**{'TimeLimit.truncated':False})
    b=SimpleNamespace(size=lambda:1,actions=np.array([[[.7,-.4]]]),observations=np.array([[[0.,0.]]]),
        next_observations=np.array([[[1.,0.]]]),rewards=np.array([[-1.]]),dones=np.array([[True]]),timeouts=np.array([[False]]))
    assert audit_replay(b,[row])['rows_checked']==1
    b.actions[0,0]=[.01,0.]
    with pytest.raises(AssertionError):audit_replay(b,[row])


def test_finite_budget_and_closed_stage_not_reopened(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'isolated_home'))
    p=task.protocol()
    assert len(p['evaluation_order'])==8 and p['training_transitions']==512 and p['hardware_actions']==0
    (tmp_path/'state.json').write_text(json.dumps(dict(runs=[{'action':task.ACTIONS[0]}])))
    with pytest.raises(ValueError,match='already consumed'):task.run(tmp_path,task.ACTIONS[0])
