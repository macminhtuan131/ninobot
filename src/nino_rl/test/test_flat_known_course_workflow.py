"""Verify the conditional pilot's real snapshot and actor transfer without ROS."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/nino_rl/scripts'))


def test_known_course_snapshot_and_actor_transfer():
    import run_flat_quiet_tail_workflow as workflow
    old=workflow.OUTPUT
    # An isolated source transform, not a fake passing experiment or rollout.
    workflow.OUTPUT=workflow.SOURCE
    try:
        with tempfile.TemporaryDirectory(prefix='flat-known-contract-test-') as directory:
            root=Path(directory)
            workflow.build_learning_snapshot(root)
            program="""
import sys,yaml,torch,numpy as np,gymnasium as gym
from types import SimpleNamespace
from stable_baselines3 import PPO
from nino_rl.known_course_reference import target,observed_reference
from nino_rl.policies import policy_spec
from nino_rl.model_transfer import initialize_actor,ACTOR_PREFIXES
from nino_rl.training_contract import training_contract,validate_resume
from nino_rl.control_v2 import validate_action_mode
cfg=yaml.safe_load(open(sys.argv[1]))
assert not cfg['policy_v2']['require_terrain_preview']
assert target(3.89)==1 and target(3.9)==.7 and target(4.55)==.7 and target(4.56)==1
assert len(observed_reference(SimpleNamespace(x=4.45)))==4
class Dummy(gym.Env):
    observation_space=gym.spaces.Box(-5,5,(300,),dtype=np.float32)
    action_space=gym.spaces.Box(-1,1,(2,),dtype=np.float32)
    def reset(self,**kwargs):return np.zeros(300,np.float32),{}
    def step(self,a):return np.zeros(300,np.float32),0.,False,False,{}
cls,kw=policy_spec(cfg)
fresh=PPO(cls,Dummy(),policy_kwargs=kw,seed=42,device='cpu',n_steps=1024)
critic={k:v.clone() for k,v in fresh.policy.state_dict().items() if k.startswith(
    ('vf_features_extractor.','mlp_extractor.value_net.','value_net.'))}
assert critic
source=PPO.load(sys.argv[2],device='cpu');validate_action_mode(source,cfg)
keys=initialize_actor(fresh,source)
for k in keys:assert torch.equal(fresh.policy.state_dict()[k],source.policy.state_dict()[k]),k
for k,v in critic.items():assert torch.equal(fresh.policy.state_dict()[k],v),k
assert fresh.num_timesteps==0 and not fresh.policy.optimizer.state
assert training_contract(cfg)['revision']==50
try:validate_resume(source,cfg)
except ValueError:pass
else:raise AssertionError('Old optimizer resume accepted')
print('PASS: mapped reference, actor copy, fresh critic/optimizer, old resume rejection')
"""
            env=os.environ.copy();env['PYTHONPATH']=str(root/'python')
            subprocess.run([sys.executable,'-c',program,str(root/'config.yaml'),str(workflow.ACTOR)],
                           env=env,check=True)
    finally:workflow.OUTPUT=old
