"""Prepared PI-screen backend. No physics runner/release in this module."""
from copy import deepcopy
import json,math,subprocess,time
from .gain_factory_backend import GainReadinessBackend
from .gain_reference_map import diagnostic_support
from .pi_screen_contract import (CONTEXT_ID,require_ki,expected_parameters,
    require_parameters,require_audit)


class PiScreenBackend(GainReadinessBackend):
    kind='gazebo_pi_screen_context_v1'

    def __init__(self,c,directory,world,g,task,condition,independent,*,allow_physics=False):
        if allow_physics is not True:
            raise ValueError('PI screen has no physics release in offline qualification')
        self.pi_ki=require_ki(c['backend']['pi_ki'])
        if c['backend']['sim_common_gain']!=1.:raise ValueError('PI contrast requires gain one')
        super().__init__(c,directory,world,g,task,condition,independent,allow_physics=True)
        self.environment.pop('NINO_SIM_GAIN_CONTEXT',None)
        self.environment['NINO_SIM_PI_SCREEN_CONTEXT']=CONTEXT_ID

    def _start_io(self):
        super()._start_io()
        from std_msgs.msg import Float64MultiArray
        self.node.create_subscription(Float64MultiArray,'/nino_drive/pi_screen',self._pi_receive,10)

    def _pi_receive(self,msg):
        try:
            fields=msg.layout.dim[0].label.split(',')
            if len(fields)!=len(msg.data) or len(set(fields))!=len(fields):
                raise ValueError('PI diagnostic schema mismatch')
            values=dict(zip(fields,msg.data));require_audit(values,self.pi_ki)
            self._store('pi_screen',values['sim_time_s'],values)
        except Exception as exc:
            with self.lock:self.error=repr(exc)

    def _wait_feedback(self,target):
        lags=super()._wait_feedback(target);deadline=time.monotonic()+5.
        while time.monotonic()<deadline:
            self._check()
            with self.lock:
                audit=deepcopy(self.messages.get('pi_screen'))
                drive=deepcopy(self.messages.get('drive'))
            if audit and drive and diagnostic_support(audit['stamp_s'],drive['stamp_s'],target):
                require_audit(audit['values'],self.pi_ki)
                return dict(lags,pi_screen=target-audit['stamp_s'])
            time.sleep(.002)
        raise RuntimeError('PI/drive diagnostics missing, stale or unmatched; no physics retry')

    def reset(self,seed=None):
        view,info=self._reset_guided(seed=seed)
        names=list(expected_parameters(self.pi_ki))
        values=self._parameter_readback(self.params,names)
        actual={name:({1:v.bool_value,2:v.integer_value,3:v.double_value,4:v.string_value}.get(v.type))
                for name,v in zip(names,values)}
        (self.episode_dir/'pi_screen_parameters.json').write_text(json.dumps(actual,indent=2)+'\n')
        require_parameters(actual,self.pi_ki)
        return view,dict(info,pi_screen_context=CONTEXT_ID,evaluation_ki=self.pi_ki)

    def advance_reference(self,v,w,dt):
        view,labels,term,trunc,info=super().advance_reference(v,w,dt)
        with self.lock:audit=deepcopy(self.messages['pi_screen']['values'])
        require_audit(audit,self.pi_ki)
        info.update(pi_screen_audit=audit,pi_screen_context=CONTEXT_ID,evaluation_ki=self.pi_ki)
        return view,labels,term,trunc,info

    def _reset_factory(self,seed=None):
        if self.episode+1>=int(self.config['backend']['max_episodes']):
            raise RuntimeError('Factory smoke episode budget exhausted; retain failure, no further reset')
        if self.launch is not None:self._stop_episode()
        self.episode+=1;self.episode_dir=self.directory/('episode_'+str(self.episode));self.episode_dir.mkdir()
        self.messages={};self.counts={};self.raw=[];self.error=None;self.request=(0.,0.);self.clock=0.;self.iterations=0
        self.closed=False;self.assembler.reset();self._start_io()
        self.log=(self.episode_dir/'launch.log').open('w')
        args=['ros2','launch',str(self.repo/'src/nino_rl/launch/training_sim_pi_screen.launch.py'),
              'world:='+str(self.world),'world_name:=factory_floor_lab','headless:=true','verbosity:=2',
              'accept_torque:=false','contact_lab:=true','terrain_preview:=false',
              'caster_wheel_damping:=0.001','pi_integrator_profile:=conditional_v1',
              'max_wheel_torque:=4.0','controller_startup_timeout:=300','sim_common_gain:='+str(self.sim_common_gain),'velocity_ki:='+str(self.pi_ki)]
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
        for key,expected in dict(control_rate=500.,velocity_kp=.3,velocity_ki=self.pi_ki,max_wheel_torque=4.,max_effort_rate=10.,max_wheel_acceleration=12.).items():
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

    _reset_guided=GainReadinessBackend._reset_guided
