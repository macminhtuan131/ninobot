import json

import gymnasium as gym
import numpy as np
import pytest

from nino_rl import goal_studio_contract as spec
from nino_rl import training_studio_api_v3 as api
from nino_rl.common_training_studio_v2 import build_model
from nino_rl.goal_training_studio import checkpoint


def request():
    return dict(schema_version=1,mode='train',scenario='unknown_step_dev_bank_v1',
                profile='nino_td3_research_h5_v1',timesteps=20000,seed=11,
                checkpoint_every=5000,wall_minutes=240,evaluate=True,resume=None)


def test_new_engine_is_100d_goal_task_and_old_dispatcher_stays_separate():
    r=dict(request(),schema_version=2,engine=spec.ENGINE)
    engine,checked=api.split(r)
    assert engine==spec.ENGINE and checked['timesteps']==20000
    assert spec.profiles()[checked['profile']]['algorithm']['buffer_size']==100000
    assert api.validate_request(r)==r


@pytest.mark.parametrize('changes',[dict(timesteps=10000),dict(scenario='box_c1_6mm_dr'),
                                   dict(profile='nino_td3_research_h8_v1'),dict(timesteps=True),
                                   dict(mode='smoke'),dict(evaluate='true')])
def test_invalid_or_wrong_task_requests_are_blocked(changes):
    with pytest.raises(ValueError):spec.validate_request(dict(request(),**changes))


def test_smoke_uses_384_steps_and_budget_never_opens_a_job():
    r=dict(request(),mode='smoke',profile=spec.SMOKE_PROFILE,timesteps=384)
    assert spec.validate_request(r)['timesteps']==384
    b=spec.budget(request())
    assert b['training_launches_max']==201 and b['evaluation_launches']==6
    assert b['hardware_actions']==0 and b['required_free_bytes']>b['estimated_output_bytes']


def test_real_td3_synthetic_checkpoint_has_matching_model_optimizer_replay_and_gui_kind(tmp_path):
    from stable_baselines3 import TD3
    class Toy(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,(100,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,(1,),dtype=np.float32)
        def reset(self,seed=None,options=None):
            super().reset(seed=seed);self.n=0
            return np.zeros(100,np.float32),{}
        def step(self,a):
            self.n+=1
            return np.zeros(100,np.float32),-float(a[0]**2),self.n==4,False,{}
    model=build_model(Toy(),dict(profile=spec.SMOKE_PROFILE,seed=11))
    model.learn(32)
    identity=dict(engine=spec.ENGINE,profile=spec.SMOKE_PROFILE,seed=11,scenario='unknown_step_dev_bank_v1')
    cp=tmp_path/'checkpoint';checkpoint(model,cp,identity)
    got=api.inspect_checkpoint(cp,verify_files=True)
    assert got['engine']==spec.ENGINE and got['global_steps']==32 and got['replay_size']==32
    restored=TD3.load(cp/'model.zip',device='cpu');restored.load_replay_buffer(cp/'replay_buffer.pkl')
    assert restored._n_updates==model._n_updates and restored.replay_buffer.size()==32
    (cp/'checkpoint.json').write_text('{}')
    with pytest.raises((ValueError,KeyError)):api.inspect_checkpoint(cp)
