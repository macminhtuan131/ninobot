"""New residual experiment contract; deliberately incompatible with legacy torque PPO.

Backend adapters must explicitly implement this reference/observation contract.
This module does not launch Gazebo/ROS or train/deploy on import or preparation.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from nino_control.residual_velocity import CONTRACT_ID, FEATURES, actor_contract
from nino_control.residual_pipeline import ResidualPipeline


def source_fingerprint():
    import nino_control.residual_velocity as reference
    import nino_control.residual_pipeline as pipeline
    import nino_rl.velocity_backend as backend
    control=Path(reference.__file__).parent;rl=Path(__file__).parent
    paths=[control/name for name in ('residual_velocity.py','residual_pipeline.py','residual_actor.py','residual_shadow.py','governor_core.py')]
    paths += [rl/name for name in ('residual_experiment.py','velocity_backend.py','residual_workflow.py','residual_ros.py','gazebo_velocity_backend.py','residual_sysid.py','td3_config.py')]
    # The loader and YAML defaults also affect observations/reward/dynamics;
    # changing them must not leave an apparently current validation/checkpoint.
    paths.append(rl/'core.py')
    configs=rl.parent/'config'
    if not configs.is_dir():
        from ament_index_python.packages import get_package_share_directory
        configs=Path(get_package_share_directory('nino_rl'))/'config'
    paths += [configs/name for name in ('residual_velocity_td3.yaml','residual_velocity_ppo.yaml','td3_parameter_profiles.yaml')]
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()


def experiment_contract(config):
    if config.get('experiment_contract') != CONTRACT_ID:
        raise ValueError('New residual velocity contract required; no legacy checkpoint conversion')
    if config.get('algorithm') not in ('TD3','PPO','SAC'):raise ValueError('Unsupported comparator')
    actor=config.get('actor',{})
    if actor.get('privileged_inputs'):raise ValueError('Privileged actor input prohibited')
    k=actor.get('history_frames',5)
    if type(k) is not int or k<1:raise ValueError('Invalid history length')
    dt=float(config['control_interval_s'])
    if not math.isfinite(dt) or not 0<dt<=float(actor['max_history_gap_s']):raise ValueError('Invalid control/history interval')
    abi=actor_contract(config)
    contract=dict(abi,algorithm=config['algorithm'],source_fingerprint=source_fingerprint(),
        replay_action='policy_proposal; reference projection belongs to environment transition',configuration=deepcopy(config))
    body=json.dumps(contract,sort_keys=True,allow_nan=False)
    return dict(contract,sha256=hashlib.sha256(body.encode()).hexdigest())


def reward_terms(labels, weights, action, previous, dt):
    """Evaluation labels may be privileged sim truth; actor never receives them.

    Real matching metrics need an independently validated reference. A missing
    required label is unknown/error, never silently zero or encoder-derived GT.
    """
    if not math.isfinite(dt) or dt <= 0:raise ValueError('Invalid reward clock')
    required={name for name,w in weights.items() if w and name not in ('time','action_size','action_change')}
    if not required.issubset(labels):raise ValueError('Missing reward labels: '+str(sorted(required-set(labels))))
    if not all(math.isfinite(float(labels[name])) for name in required):raise ValueError('Nonfinite reward label')
    terms={}
    for name in required:
        value=float(labels[name])
        terms[name]=weights[name]*value if name=='progress_m' else -weights[name]*value*value*dt
    terms['time']=-weights.get('time',0.)*dt
    terms['action_size']=-weights.get('action_size',0.)*sum(x*x for x in action)*dt
    terms['action_change']=-weights.get('action_change',0.)*sum((a-b)**2 for a,b in zip(action,previous))/dt
    return sum(terms.values()),terms


def make_environment(config, backend, *, governor=False):
    """Gym transition and ROS use ResidualPipeline, including accepted-action history.

    Backend measurements/transport failures raise and quarantine the run. Explicit
    permission/fault stops produce terminal failure transitions, not lost episodes.
    Time limits remain truncated so the learner can bootstrap them correctly.
    """
    contract=experiment_contract(config)
    if getattr(backend,'residual_contract_id',None)!=CONTRACT_ID:raise ValueError('Backend reference adapter not validated for this contract')
    import gymnasium as gym
    from gymnasium import spaces
    import numpy as np
    class ResidualEnv(gym.Env):
        def __init__(self):
            self.backend=backend;self.contract=contract
            self.action_space=spaces.Box(-1.,1.,shape=(2,),dtype=np.float32)
            self.observation_space=spaces.Box(-5.,5.,shape=(contract['observation_size'],),dtype=np.float32)
            self.pipeline=ResidualPipeline(config,governor=governor)
            self.view=None;self.previous=(0.,0.);self.done=True
        def reset(self,*,seed=None,options=None):
            super().reset(seed=seed);self.pipeline.reset();self.previous=(0.,0.);self.done=False
            self.view,info=backend.reset(seed=seed)
            return np.asarray(self.pipeline.observe(self.view),dtype=np.float32),dict(info,experiment_contract=contract['sha256'])
        def step(self,action):
            if self.done:raise RuntimeError('Reset required after terminal/truncated transition')
            proposed=tuple(float(x) for x in action);dt=float(config['control_interval_s'])
            trace=self.pipeline.project(proposed,dt,float(config['simulation_authority']))
            self.view,labels,terminated,truncated,info=backend.advance_reference(*trace['body_reference'],dt)
            if self.pipeline.reference.latched:
                terminated=True;truncated=False
                value=-float(config.get('failure_penalty',10.));terms={'failure':value}
                info=dict(info,termination_reason=trace['reason'],intervention=True)
            else:value,terms=reward_terms(labels,config['reward_weights'],proposed,self.previous,dt)
            self.previous=proposed
            observation=np.asarray(self.pipeline.observe(self.view),dtype=np.float32)
            self.done=bool(terminated or truncated)
            return observation,value,bool(terminated),bool(truncated),dict(info,
                policy_proposal=proposed,reference_trace=trace,reward_terms=terms,
                next_source_samples=self.view.get('source_samples'),
                experiment_contract=contract['sha256'],abi_sha256=contract['abi_sha256'])
        def close(self):backend.close()
    return ResidualEnv()


def build_model(config, environment, seed):
    """Factory only; no .learn(). Gate must be changed by an explicit experiment protocol."""
    contract=experiment_contract(config)
    if config.get('training',{}).get('allowed') is not True:
        raise ValueError('Training is disabled: require backend validation, data/baseline gates and a new budget')
    training=config.get('training',{})
    if type(training.get('budget_transitions')) is not int or training['budget_transitions']<=0:
        raise ValueError('Explicit positive experiment budget required')
    if not training.get('backend_validation_artifact'):
        raise ValueError('Verified backend artifact required')
    validation=json.loads(Path(training['backend_validation_artifact']).read_text())
    if (validation.get('contract_id')!=CONTRACT_ID or validation.get('backend_validated') is not True
            or validation.get('features')!=list(FEATURES)
            or validation.get('history_frames')!=config['actor']['history_frames']):
        raise ValueError('Backend validation artifact does not match actor/reference contract')
    if float(config['simulation_authority'])<=0:raise ValueError('Residual learning requires nonzero simulation authority; zero is a shadow/fixture test only')
    if (validation.get('integration_pass') is not True or validation.get('abi_sha256')!=contract['abi_sha256']
            or validation.get('source_fingerprint')!=source_fingerprint()
            or validation.get('backend_configuration')!=config.get('backend',{})
            or validation.get('backend_kind')!=environment.backend.kind):
        raise ValueError('Stale/mismatched integration validation')
    from stable_baselines3 import TD3,PPO,SAC
    import numpy as np
    if environment.observation_space.shape!=(contract['observation_size'],) or environment.action_space.shape!=(2,):
        raise ValueError('Environment observation/action contract mismatch')
    kwargs=deepcopy(config.get('algorithm_parameters',{}).get(config['algorithm'],{}))
    kwargs.setdefault('device','cpu')
    kwargs.setdefault('policy_kwargs',{'net_arch':[64,64]})
    if config['algorithm']=='TD3':
        from .td3_config import validate_runtime
        validate_runtime(config)
        from stable_baselines3.common.noise import NormalActionNoise
        kwargs['action_noise']=NormalActionNoise(np.zeros(2),float(config.get('exploration_sigma',.1))*np.ones(2))
    model={'TD3':TD3,'PPO':PPO,'SAC':SAC}[config['algorithm']]('MlpPolicy',environment,seed=seed,**kwargs)
    model.nino_residual_contract=contract
    return model


def prepare_main(argv=None):
    import argparse
    from nino_rl.core import load_config
    p=argparse.ArgumentParser(description='Validate/write offline residual contract; never starts ROS or training')
    p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv);c=load_config(a.config);contract=experiment_contract(c)
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
    (a.output/'readiness.json').write_text(json.dumps(dict(software_prepared=True,training_released=False,
        hardware_residual_authority=0,backend_integration_verified=False,
        missing=['current hardware diagnostic/body reference','calibrated backend model','new sim adapter validation and experiment budget']),indent=2)+'\n')
    print('Prepared only:',a.output,'; no ROS, Gazebo, training or motor command started.')


if __name__=='__main__':prepare_main()
