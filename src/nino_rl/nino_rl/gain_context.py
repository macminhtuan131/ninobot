"""New103D/1D simulation context; same shape never authorizes old checkpoints."""
from copy import deepcopy
import hashlib,json,math
from pathlib import Path
import numpy as np
from . import residual_ready_eval_only as parent
from . import sim_benchmark_decision as benchmark
from .gain_reference_map import CONTEXT_ID,require_gain,diagnostic_support

contract=parent.parent.frozen.contract


def fingerprint():
    base=benchmark.repo()/'src/nino_rl'
    names=['nino_rl/gain_reference_map.py','nino_rl/gain_drive_kernel.py',
        'nino_rl/gain_effort_drive.py','nino_rl/gain_factory_backend.py','nino_rl/gain_context.py',
        'launch/training_sim_gain.launch.py','nino_rl/gain_context_preflight.py',
        'nino_rl/gain_drive_fixture.py','test/test_gain_context.py','test/test_gain_drive_kernel.py']
    return hashlib.sha256(json.dumps(dict(parent=parent.fingerprint(),benchmark=benchmark.fingerprint(),
        files={name:benchmark.sha(base/name) for name in names}),sort_keys=True).encode()).hexdigest()


def configuration(gain):
    gain=require_gain(gain)
    c,g,task,condition=parent.parent.configuration(8.)
    c['purpose']=task['protocol_id']=CONTEXT_ID
    c['backend'].update(sim_common_gain=gain,scenario_id='clear_box_common_gain_context_v1')
    return c,g,task,condition


def identity():
    inherited=contract.identity()
    ident=dict(id=CONTEXT_ID,fingerprint=fingerprint(),parent_abi_sha256=inherited['abi_sha256'],
        observation=inherited['observation'],action=inherited['action'],
        last_final_semantic='driver execution reference before common target map; not effective target or measured body',
        plant_map='fixed common gain before unchanged wheel ramp/PI/torque limits; yaw unchanged before wheel limits',
        conditions_not_controller_inputs=True,hardware_authorized=False,training_released=False)
    ident['abi_sha256']=hashlib.sha256(json.dumps(ident,sort_keys=True).encode()).hexdigest()
    return ident


def require_identity(actual):
    if actual!=identity():raise ValueError('Gain-context identity mismatch; no old103D/1D checkpoint conversion')


def environment(c,backend,task,condition):
    import gymnasium as gym
    inner=contract.environment(c,backend,task,condition)
    class GainContextEnv(gym.Wrapper):
        def __init__(self):
            super().__init__(inner);self.contract=identity()
        def stamp(self,info):
            return dict(info,gain_context_parent_abi_sha256=info['abi_sha256'],
                gain_context_identity=deepcopy(self.contract),
                abi_sha256=self.contract['abi_sha256'],experiment_contract=self.contract['abi_sha256'])
        def reset(self,**kwargs):
            obs,info=self.env.reset(**kwargs)
            return obs,self.stamp(info)
        def step(self,action):
            obs,reward,term,trunc,info=self.env.step(action)
            return obs,reward,term,trunc,self.stamp(info)
    return GainContextEnv()


def request(arm,observation,geometry):
    if arm=='B0':return np.zeros(1,np.float32)
    if arm=='Classical_scheduled':return contract.classical_request(observation)
    if arm=='Causal_gain_candidate':
        value,_=benchmark.causal_gain_request(observation,geometry,benchmark.specification()['candidate'])
        return np.array([value],np.float32)
    raise ValueError('Only declared baselines; no actor in gain qualification')


def verify_transition(row,previous,epoch,gain,*,expected_identity=None):
    # A runner may pin this immutable record before its loop, provided it also
    # checks source fingerprint after closure; no persistent identity cache.
    gain=require_gain(gain);ident=identity() if expected_identity is None else expected_identity
    if row['gain_context_identity']!=ident:raise ValueError('Gain-context identity mismatch')
    if row['gain_context_parent_abi_sha256']!=ident['parent_abi_sha256']:
        raise ValueError('Gain context inherited reference ABI changed')
    parent.require_uninhibited_transition(row)
    parent.parent.frozen.qualified.verify_transition(row,previous,epoch,ident['abi_sha256'])
    parent.parent.frozen.feasibility(row,.04)
    a=row['gain_map_audit'];drive=row['drive_diagnostics']
    required=['sim_time_s','common_gain','reference_linear_m_s','reference_yaw_rad_s',
        'effective_linear_m_s','effective_yaw_rad_s','left_unlimited_target_rad_s','right_unlimited_target_rad_s',
        'left_target_rad_s','right_target_rad_s','map_calls_this_update','map_active','post_limit_targets_valid',
        'speed_clip_required','target_ramp_active']
    if not all(math.isfinite(float(a[k])) for k in required):raise ValueError('Nonfinite gain map evidence')
    if (a['common_gain']!=gain or a['map_calls_this_update']!=1 or a['map_active']!=1
            or a['post_limit_targets_valid']!=1):raise ValueError('Gain mapping missing or applied more than once')
    if not diagnostic_support(a['sim_time_s'],drive['sim_time_s'],row['sensor_clock_s']):
        raise ValueError('Gain/drive source support mismatch')
    np.testing.assert_allclose([a['reference_linear_m_s'],a['reference_yaw_rad_s']],
        [drive['executed_linear_m_s'],drive['executed_yaw_rad_s']],atol=1e-10,rtol=0)
    np.testing.assert_allclose([a['effective_linear_m_s'],a['effective_yaw_rad_s']],
        [gain*a['reference_linear_m_s'],a['reference_yaw_rad_s']],atol=1e-10,rtol=0)
    np.testing.assert_allclose(row['final_ros_reference'],
        [a['reference_linear_m_s'],a['reference_yaw_rad_s']],atol=1e-10,rtol=0)
    np.testing.assert_allclose(row['applied_target_rad_s'],[a['left_target_rad_s'],a['right_target_rad_s']],atol=1e-10,rtol=0)
    np.testing.assert_allclose(row['applied_target_rad_s'],[drive['left_target_rad_s'],drive['right_target_rad_s']],atol=1e-10,rtol=0)
    if max(map(abs,row['applied_target_rad_s']))>12.+1e-9:
        raise ValueError('Post-gain wheel speed limit violated')
    # Existing target ramps and effort slew are part of the unchanged plant,
    # with flags retained. An out-of-envelope post-map speed request is not a
    # clean gain contrast and cannot silently enter this qualification.
    if a['speed_clip_required']:
        raise ValueError('Post-map speed clipping retained; clean gain contrast not established')
    if not all(math.isfinite(drive[k]) and abs(drive[k])<=4.+1e-9
            for k in ('left_applied_nm','right_applied_nm')):
        raise ValueError('Post-gain torque envelope violation')
    samples=row['reference_trace']['source_samples']
    if set(samples)!={'imu','wheel','baseline','final','status'}:
        raise ValueError('Privileged or undeclared source entered controller packet')
    if set(row['next_source_samples'])!=set(samples):raise ValueError('Next controller packet source drift')
    return row
