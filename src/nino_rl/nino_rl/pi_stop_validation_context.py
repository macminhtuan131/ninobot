"""New103D/1D simulation context; same shape never authorizes old checkpoints."""
from copy import deepcopy
import hashlib,json,math
from pathlib import Path
import numpy as np
from . import residual_ready_eval_only as parent
from . import sim_benchmark_decision as benchmark
from .gain_reference_map import diagnostic_support
from .pi_screen_contract import CONTEXT_ID as DRIVER_CONTEXT_ID,require_ki,require_audit

CONTEXT_ID = 'nino_sim_pi_stop_validation_context_v1_2026_11_07'
from . import gain_context as gain_parent

contract=parent.parent.frozen.contract


def fingerprint():
    from . import pi_screen_context as frozen
    base=benchmark.repo()/'src/nino_rl'
    names=['nino_rl/pi_stop_validation_context.py','test/test_pi_stop_validation_context.py']
    return hashlib.sha256(json.dumps(dict(parent=frozen.fingerprint(),
        files={name:benchmark.sha(base/name) for name in names}),sort_keys=True).encode()).hexdigest()


def configuration(ki):
    ki=require_ki(ki)
    c,g,task,condition=parent.parent.configuration(6.)
    c['purpose']=task['protocol_id']=CONTEXT_ID
    c['backend'].update(sim_common_gain=1.,pi_ki=ki,scenario_id='clear_box_pi_stop_validation_v1')
    if not (c['backend']['command_until_s']==c['task']['command_until_s']==task['command_until_s']==6.):
        raise ValueError('Stop6 schedule drift')
    return c,g,task,condition


def identity():
    inherited=contract.identity()
    ident=dict(id=CONTEXT_ID,fingerprint=fingerprint(),parent_abi_sha256=inherited['abi_sha256'],
        observation=inherited['observation'],action=inherited['action'],
        last_final_semantic=gain_parent.identity()['last_final_semantic'],
        source_stop_s=6.,plant_map='gain one; frozen velocity PI kernel; readonly Ki condition 0.10 or 0.15',
        conditions_not_controller_inputs=True,hardware_authorized=False,training_released=False,
        actor_loading_allowed=False,allowed_arm='B0',allowed_residual=0.)
    ident['abi_sha256']=hashlib.sha256(json.dumps(ident,sort_keys=True).encode()).hexdigest()
    return ident


def require_identity(actual):
    if actual!=identity():raise ValueError('PI-context identity mismatch; no old103D/1D checkpoint conversion')


def environment(c,backend,task,condition):
    import gymnasium as gym
    if (c['backend']['command_until_s']!=6. or c['task']['command_until_s']!=6.
            or task['command_until_s']!=6. or c['backend']['sim_common_gain']!=1.
            or c['training']['allowed'] or c['hardware_authority']!=0.):
        raise ValueError('Validation requires stop6/gain1/no learning/no hardware')
    require_ki(c['backend']['pi_ki'])
    inner=contract.environment(c,backend,task,condition)
    class PiScreenEnv(gym.Wrapper):
        def __init__(self):
            super().__init__(inner);self.contract=identity()
        def stamp(self,info):
            return dict(info,pi_stop_parent_abi_sha256=info['abi_sha256'],
                pi_stop_identity=deepcopy(self.contract),
                abi_sha256=self.contract['abi_sha256'],experiment_contract=self.contract['abi_sha256'])
        def reset(self,**kwargs):
            obs,info=self.env.reset(**kwargs)
            return obs,self.stamp(info)
        def step(self,action):
            if np.asarray(action).shape!=(1,) or not np.array_equal(action,np.zeros(1)):
                raise ValueError('PI stop validation is B0 only; nonzero residual/actor prohibited')
            obs,reward,term,trunc,info=self.env.step(action)
            return obs,reward,term,trunc,self.stamp(info)
    return PiScreenEnv()


def request(arm,observation,geometry):
    if arm!='B0':raise ValueError('PI stop validation is B0 only; no actor or adaptive baseline')
    return np.zeros(1,np.float32)


def wrapper_parity():
    """Same-input equivalence at stop6; the fixture does not model Ki dynamics."""
    from .pi_stop_validation_preflight import fixture_backend
    results=[];ident=identity()
    for ki in (.1,.15):
        c,g,task,bc=configuration(ki)
        c['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
        old=contract.environment(c,fixture_backend(c),task,bc)
        new=environment(c,fixture_backend(c),task,bc)
        previous=None;rows=[]
        try:
            a,_=old.reset(seed=701);b,reset=new.reset(seed=701)
            require_identity(reset['pi_stop_identity'])
            for step in range(140):
                np.testing.assert_array_equal(a,b)
                a,r1,t1,u1,i1=old.step(np.zeros(1,np.float32))
                b,r2,t2,u2,i2=new.step(request('B0',b,c['nominal_geometry']))
                np.testing.assert_array_equal(a,b)
                if (r1,t1,u1)!=(r2,t2,u2):raise ValueError('Stop6 reward/terminal drift')
                for key in ('reference_trace','plan_projection','applied_target_rad_s','final_ros_reference'):
                    if i1[key]!=i2[key]:raise ValueError('Stop6 reference/projection drift')
                row=dict(step=step,reward=r2,terminated=t2,truncated=u2,done=t2 or u2,**i2,
                    qualification_condition=dict(arm='B0',source_stop_s=6.,ki=ki),
                    **{'TimeLimit.truncated':bool(u2 and not t2)})
                epoch=row['sensor_clock_s']-row['task']['elapsed_s'] if previous is None else epoch
                verify_transition(row,previous,epoch,ki,expected_identity=ident)
                previous=row;rows.append(row)
            if not rows[-1]['terminated'] or rows[-1]['truncated']:raise ValueError('Stop6 terminal drift')
        finally:old.close();new.close()
        results.append(dict(ki=ki,source_stop_s=6.,paired_decisions=140,wrapper_transitions=280,
            observation_reward_reference_projection_terminal_exact=True,Ki_dynamics_modeled=False))
    return results


def verify_transition(row,previous,epoch,ki,*,expected_identity=None):
    # A runner may pin this immutable record before its loop, provided it also
    # checks source fingerprint after closure; no persistent identity cache.
    ki=require_ki(ki);gain=1.;ident=identity() if expected_identity is None else expected_identity
    condition=row['qualification_condition']
    if condition.get('source_stop_s')!=6. or condition.get('arm')!='B0' or condition.get('ki')!=ki:
        raise ValueError('Stop6 validation condition mismatch')
    if row['pi_stop_identity']!=ident:raise ValueError('Gain-context identity mismatch')
    if row['pi_stop_parent_abi_sha256']!=ident['parent_abi_sha256']:
        raise ValueError('Gain context inherited reference ABI changed')
    parent.require_uninhibited_transition(row)
    parent.parent.frozen.qualified.verify_transition(row,previous,epoch,ident['abi_sha256'])
    parent.parent.frozen.feasibility(row,.04)
    audit=require_audit(row['pi_screen_audit'],ki)
    if row.get('evaluation_ki')!=ki or row.get('pi_screen_context')!=DRIVER_CONTEXT_ID:
        raise ValueError('PI condition metadata mismatch')
    if not diagnostic_support(audit['sim_time_s'],row['drive_diagnostics']['sim_time_s'],row['sensor_clock_s']):
        raise ValueError('PI/drive source support mismatch')
    if (not np.array_equal(row['requested_scalar_action'],[0.])
            or any(row['reference_trace']['accepted_policy_delta_wheel_m_s'])):
        raise ValueError('Nonzero residual in PI screen')
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
