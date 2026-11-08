"""Prepared isolated gain backend; construction requires explicit future release.

Reset copies below preserve the frozen factory/guided lifecycle, with a new
launch and an additional diagnostic prerequisite. No physics entry CLI here.
"""
from copy import deepcopy
import json,math,os,subprocess,time
from pathlib import Path
from .drive_readiness_candidate import DriveReadinessBackend
from .factory_velocity_backend import simulation_seconds
from .causal_planar_estimator import CausalPlanarEstimator
from .residual_guidance import GuidanceReference
from .gain_reference_map import CONTEXT_ID,require_gain,diagnostic_support


class GainReadinessBackend(DriveReadinessBackend):
    kind='gazebo_common_gain_reference_context_v1'

    def __init__(self,c,directory,world,g,task,condition,independent,*,allow_physics=False):
        if allow_physics is not True:
            raise ValueError('Gain backend has no physics release in offline qualification')
        self.sim_common_gain=require_gain(c['backend']['sim_common_gain'])
        super().__init__(c,directory,world,g,task,condition,independent)
        self.environment['NINO_SIM_GAIN_CONTEXT']=CONTEXT_ID

    def _start_io(self):
        super()._start_io()
        from std_msgs.msg import Float64MultiArray
        self.node.create_subscription(Float64MultiArray,'/nino_drive/gain_map',
            self._gain_receive,10)

    def _gain_receive(self,msg):
        try:
            fields=msg.layout.dim[0].label.split(',')
            if len(fields)!=len(msg.data) or len(set(fields))!=len(fields):
                raise ValueError('Gain diagnostic schema mismatch')
            values=dict(zip(fields,msg.data))
            if not all(math.isfinite(v) for v in values.values()):raise ValueError('Nonfinite gain diagnostic')
            self._store('gain_map',values['sim_time_s'],values)
        except Exception as exc:
            with self.lock:self.error=repr(exc)

    def _wait_feedback(self,target):
        deadline=time.monotonic()+5.
        lags=super()._wait_feedback(target)
        while time.monotonic()<deadline:
            self._check()
            with self.lock:
                gain=deepcopy(self.messages.get('gain_map'))
                drive=deepcopy(self.messages.get('drive'))
            if gain and drive and diagnostic_support(gain['stamp_s'],drive['stamp_s'],target):
                if gain['values']['common_gain']!=self.sim_common_gain:
                    raise ValueError('Gain diagnostic disagrees with immutable condition')
                return dict(lags,gain_map=target-gain['stamp_s'])
            time.sleep(.002)
        raise RuntimeError('Gain/drive diagnostics missing, stale or unmatched; no physics retry')

    def reset(self,seed=None):
        view,info=self._reset_guided(seed=seed)
        names=['sim_common_gain','use_sim_time','accept_torque','max_wheel_speed',
               'max_velocity_control_torque']
        values=self._parameter_readback(self.params,names)
        actual=dict(zip(names,[values[0].double_value,values[1].bool_value,values[2].bool_value,
                              values[3].double_value,values[4].double_value]))
        expected=dict(sim_common_gain=self.sim_common_gain,use_sim_time=True,accept_torque=False,
                      max_wheel_speed=12.,max_velocity_control_torque=4.)
        (self.episode_dir/'gain_parameters.json').write_text(json.dumps(actual,indent=2)+'\n')
        if actual!=expected:raise ValueError('Gain context parameter readback mismatch')
        return view,dict(info,gain_context=CONTEXT_ID,evaluation_gain=self.sim_common_gain)

    def advance_reference(self,v,w,dt):
        view,labels,term,trunc,info=super().advance_reference(v,w,dt)
        with self.lock:audit=deepcopy(self.messages['gain_map']['values'])
        # Evaluation only. Never replace view.features / source_samples with
        # gain-normalized driver/encoder values or inject gain into observations.
        info.update(gain_map_audit=audit,gain_context=CONTEXT_ID,
            effective_drive_reference=[audit['effective_linear_m_s'],audit['effective_yaw_rad_s']],
            gain_map_evidence='simulated target calibration map before unchanged motor limits')
        return view,labels,term,trunc,info

    def _reset_factory(self,seed=None):
        if self.episode+1>=int(self.config['backend']['max_episodes']):
            raise RuntimeError('Factory smoke episode budget exhausted; retain failure, no further reset')
        if self.launch is not None:self._stop_episode()
        self.episode+=1;self.episode_dir=self.directory/('episode_'+str(self.episode));self.episode_dir.mkdir()
        self.messages={};self.counts={};self.raw=[];self.error=None;self.request=(0.,0.);self.clock=0.;self.iterations=0
        self.closed=False;self.assembler.reset();self._start_io()
        self.log=(self.episode_dir/'launch.log').open('w')
        args=['ros2','launch',str(self.repo/'src/nino_rl/launch/training_sim_gain.launch.py'),
              'world:='+str(self.world),'world_name:=factory_floor_lab','headless:=true','verbosity:=2',
              'accept_torque:=false','contact_lab:=true','terrain_preview:=false',
              'caster_wheel_damping:=0.001','pi_integrator_profile:=conditional_v1',
              'max_wheel_torque:=4.0','controller_startup_timeout:=300','sim_common_gain:='+str(self.sim_common_gain)]
        (self.episode_dir/'launch_argv.json').write_text(json.dumps(args,indent=2)+'\n')
        self.launch=subprocess.Popen(args,env=self.environment,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        end=time.monotonic()+330.;last_report=0
        while time.monotonic()<end:
            self._check()
            with self.lock:ready=all(k in self.messages for k in ('imu','wheel','truth','drive','gain_map')) and self.clock>0
            if ready and self.publisher.get_subscription_count()==1:break
            if time.monotonic()-last_report>10:
                from .residual_workflow import emit
                emit('factory-td3','Factory startup; received '+str(self.counts));last_report=time.monotonic()
            time.sleep(.05)
        else:raise TimeoutError('Factory startup deadline; retain launch.log')
        names=['accept_torque','pi_integrator_profile','wheel_radius','wheel_separation','control_rate',
               'velocity_kp','velocity_ki','max_wheel_torque','max_effort_rate','max_wheel_acceleration']
        values=self._parameter_readback(self.params,names)
        readback={name:({1:value.bool_value,2:value.integer_value,3:value.double_value,4:value.string_value}.get(value.type))
                  for name,value in zip(names,values)}
        (self.episode_dir/'drive_parameters.json').write_text(json.dumps(readback,indent=2)+'\n')
        if values[0].bool_value or values[1].string_value!='conditional_v1':raise ValueError('Wrong factory motor backend mode')
        if not math.isclose(values[2].double_value,.0625) or not math.isclose(values[3].double_value,.34273666):raise ValueError('Factory geometry readback mismatch')
        for key,expected in dict(control_rate=500.,velocity_kp=.3,velocity_ki=.1,max_wheel_torque=4.,max_effort_rate=10.,max_wheel_acceleration=12.).items():
            if readback[key] is None or not math.isclose(readback[key],expected):raise ValueError('Factory drive parameter mismatch: '+key)
        urdf=self._parameter_readback(self.description,['robot_description'])[0].string_value
        (self.episode_dir/'robot.urdf').write_text(urdf)
        if not all(name in urdf for name in ('caster_left_swivel_joint','caster_right_swivel_joint')):raise ValueError('Actual Nino caster model missing')
        if not self._control(0):raise RuntimeError('Factory initial pause ACK missing; no physics request retried')
        time.sleep(.12)
        self.settle()
        self._wait_feedback(self.time);self.start_time=self.time
        self.origin=deepcopy(self.messages['truth']['values']['pose']);self.previous_x=self.origin[0]
        self.flush_raw();return self.view(),dict(backend=self.kind,world=str(self.world),partition=self.partition,
            ros_domain=129,seed=seed,reset='fresh_owned_launch_not_snapshot',calibrated_to_hardware=False)

    def _reset_guided(self,seed=None):
        self.active=False;self.estimator=None;self.guidance=None;self.cached_view=None
        _,info=self._reset_factory(seed=seed)
        with self.lock:
            epoch='guided_baseline_episode_'+str(self.episode)
            self.estimator=CausalPlanarEstimator(radius_l=self.config['nominal_geometry']['radius_l'],
                radius_r=self.config['nominal_geometry']['radius_r'],**self.protocol['estimator'])
            self.estimator.reset(stamp_s=simulation_seconds(self.start_time),pose=self.protocol['initial_pose_m_rad'],epoch=epoch)
            r=self.messages['wheel']
            self.estimator.push('wheel',r['stamp_s'],r['values'],r['receipt_monotonic_s'])
            self.guidance=GuidanceReference(self.gconf,epoch=epoch);self.active=True
        result=self.view();self.flush_raw()
        return result,dict(info,estimator_initialization=self.estimator.initialization,
            initial_pose_from_protocol=self.protocol['initial_pose_m_rad'],guidance_contract=self.guidance.contract,
            condition=self.condition,truth_used_for_guidance=False)
