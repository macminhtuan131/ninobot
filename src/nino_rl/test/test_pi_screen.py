"""PI contrast software gates. No ROS init, Gazebo, actor or hardware IO."""
from copy import deepcopy
from types import SimpleNamespace as NS
import threading
import numpy as np
import pytest
from nino_control.effort_drive import EffortDrive
from nino_rl import pi_screen_context as c
from nino_rl.pi_screen_contract import (CONTEXT_ID,require_ki,expected_parameters,
    require_parameters,require_simulation_environment,runtime_audit)
from nino_rl.pi_screen_preflight import (driver_parity,wrapper_parity,reset_ast_parity,fixture_backend)
from nino_rl.pi_screen_effort_drive import PiScreenEffortDrive
from nino_rl.pi_screen_backend import PiScreenBackend
from nino_rl.gain_factory_backend import GainReadinessBackend
from nino_rl.gain_drive_fixture import fixture,Sink


def test_reset_lifecycle_has_only_declared_launch_ki_readback_diff():
    assert reset_ast_parity()['factory_reset_only_launch_ki_readback_changed']
    assert PiScreenBackend.settle is GainReadinessBackend.settle
    assert PiScreenEffortDrive.stop is EffortDrive.stop


def test_actual_kernel_baseline_parity_and_candidate_reaches_pi():
    report,rows=driver_parity()
    assert report['synthetic_callbacks']==3600 and len(rows)==1200
    assert report['baseline_exact_state_effort_diagnostics_odometry']
    assert report['candidate_effort_different_callbacks']>0
    assert any(not r['fresh'] for r in rows) and any(not r['have_wheel_state'] for r in rows)


@pytest.fixture(scope='module')
def paired():return wrapper_parity()


def test_both_wrapper_conditions_exact_parity_on_identical_synthetic_inputs(paired):
    assert sum(r['old_and_new_transitions'] for r in paired[0])==560
    assert all(r['ki_dynamics_not_modeled'] for r in paired[0])
    assert all(len(rows)==140 for rows in paired[1])


@pytest.mark.parametrize('ki',[.1,.15])
def test_condition_metadata_not_controller_input_and_identity_not_old(ki):
    config,*_=c.configuration(ki)
    assert config['backend']['pi_ki']==ki and config['backend']['sim_common_gain']==1.
    assert 'pi_ki' not in str(c.identity()['observation'])
    assert c.identity()['conditions_not_controller_inputs']
    assert c.identity()['abi_sha256']!=c.gain_parent.identity()['abi_sha256']
    with pytest.raises(ValueError,match='no old103D'):c.require_identity(c.gain_parent.identity())


@pytest.mark.parametrize('bad',[True,None,'0.15',0.,.15001,float('nan'),float('inf')])
def test_no_undeclared_ki(bad):
    with pytest.raises(ValueError):require_ki(bad)


@pytest.mark.parametrize('key,value',[('velocity_ki',.1),('velocity_kp',.31),
    ('max_wheel_torque',12.),('use_sim_time',False),('accept_torque',True),
    ('command_timeout',.51),('sim_common_gain',.98),('integral_limit',5.)])
def test_readback_must_match_all_pinned_parameters(key,value):
    actual=expected_parameters(.15);actual[key]=value
    with pytest.raises(ValueError,match='readback mismatch'):require_parameters(actual,.15)


@pytest.mark.parametrize('fault',['wrong_ki','wrong_kp','stale_pi','future_pi','residual','oldabi','hidden_source','gain'])
def test_row_validator_rejects_wrong_condition_or_causality(paired,fault):
    row=deepcopy(paired[1][1][40]);previous=paired[1][1][39]
    if fault=='wrong_ki':row['pi_screen_audit']['velocity_ki']=.1
    if fault=='wrong_kp':row['pi_screen_audit']['velocity_kp']=.4
    if fault=='stale_pi':row['pi_screen_audit']['sim_time_s']-=.1
    if fault=='future_pi':row['pi_screen_audit']['sim_time_s']+=.1
    if fault=='residual':row['requested_scalar_action']=.1
    if fault=='oldabi':row['abi_sha256']=c.gain_parent.identity()['abi_sha256']
    if fault=='hidden_source':row['reference_trace']['source_samples']['ki']={'values':.15}
    if fault=='gain':row['gain_map_audit']['common_gain']=.98
    with pytest.raises((ValueError,AssertionError)):
        c.verify_transition(row,previous,row['sensor_clock_s']-row['task']['elapsed_s'],.15,expected_identity=c.identity())


@pytest.mark.parametrize('action',[[.01],[float('nan')],[0.,0.],0.])
def test_nonzero_or_wrong_shape_never_reaches_backend(action):
    config,_,task,condition=c.configuration(.1);backend=fixture_backend(config)
    env=c.environment(config,backend,task,condition)
    try:
        env.reset(seed=701)
        def fail(*a):raise AssertionError('Backend must not be called')
        backend.advance_reference=fail
        with pytest.raises(ValueError,match='B0 only'):env.step(action)
    finally:env.close()


def test_actor_request_rejected():
    with pytest.raises(ValueError,match='B0 only'):c.request('TD3',None,None)


def test_no_physics_release_fails_before_io_or_directory(tmp_path):
    with pytest.raises(ValueError,match='no physics release'):
        PiScreenBackend({},tmp_path/'unused',None,None,None,None,None)
    assert not (tmp_path/'unused').exists()


def test_entry_guards_before_ros_init(monkeypatch):
    from nino_rl import pi_screen_effort_drive as m
    monkeypatch.delenv('NINO_SIM_PI_SCREEN_CONTEXT',raising=False)
    monkeypatch.setattr(m.rclpy,'init',lambda **kw:pytest.fail('ROS must not initialize'))
    with pytest.raises(ValueError,match='isolated simulation'):m.main()
    env=dict(ROS_DOMAIN_ID='129',NINO_ROS_DOMAIN_ID='129',NINO_SIM_PI_SCREEN_CONTEXT=CONTEXT_ID,
        GZ_PARTITION='nino_factory_td3_fixture',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    require_simulation_environment(env)
    for key in env:
        bad=env.copy();bad.pop(key)
        with pytest.raises(ValueError):require_simulation_environment(bad)


def test_reset_clears_pi_and_map_without_ros_init():
    template=fixture(1.);obj=object.__new__(PiScreenEffortDrive);obj.__dict__.update(template.__dict__)
    obj.target_velocity=[2.,2.];obj.error_integral=[1.,1.];obj.last_gain_map={'stale':True};obj.gain_map_calls=3
    response=PiScreenEffortDrive._reset_odometry(obj,None,NS())
    assert response.success and obj.error_integral==[0.,0.] and obj.target_velocity==[0.,0.]
    assert obj.last_gain_map is None and obj.gain_map_calls==0


@pytest.mark.parametrize('state',['ready','missing','mismatched_stamp','wrong_ki'])
def test_backend_waits_for_pi_source_ack_without_extra_physics(state,monkeypatch):
    from nino_rl import pi_screen_backend as m
    monkeypatch.setattr(GainReadinessBackend,'_wait_feedback',lambda *a:dict(gain_map=0.))
    ticks=iter(i*.5 for i in range(30));monkeypatch.setattr(m.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(m.time,'sleep',lambda *a:None)
    f=fixture(1.);f.ki=.15;f.last_control_ns=2_300_000_000
    messages=dict(drive=dict(stamp_s=2.3),pi_screen=dict(stamp_s=2.3,values=runtime_audit(f)))
    if state=='missing':messages.pop('pi_screen')
    if state=='mismatched_stamp':messages['pi_screen']['stamp_s']-=.001
    if state=='wrong_ki':messages['pi_screen']['values']['velocity_ki']=.1
    obj=object.__new__(PiScreenBackend)
    obj.__dict__.update(pi_ki=.15,messages=messages,lock=threading.RLock(),_check=lambda:None)
    if state=='ready':assert obj._wait_feedback(2.3)['pi_screen']==0.
    else:
        with pytest.raises((ValueError,RuntimeError)):obj._wait_feedback(2.3)


@pytest.mark.parametrize('wrong',[False,True])
def test_reset_records_actual_readback_and_rejects_requested_actual_mismatch(tmp_path,wrong):
    obj=object.__new__(PiScreenBackend)
    actual=expected_parameters(.15)
    if wrong:actual['velocity_ki']=.1
    def readback(params,names):
        out=[]
        for name in names:
            v=actual[name];typ=1 if isinstance(v,bool) else 4 if isinstance(v,str) else 3
            out.append(NS(type=typ,bool_value=v,integer_value=0,double_value=v,string_value=v))
        return out
    obj.__dict__.update(pi_ki=.15,episode_dir=tmp_path,params=None,
        _reset_guided=lambda **kw:(None,{}),_parameter_readback=readback)
    if wrong:
        with pytest.raises(ValueError,match='velocity_ki'):obj.reset()
    else:assert obj.reset()[1]['evaluation_ki']==.15
    import json
    assert json.loads((tmp_path/'pi_screen_parameters.json').read_text())==actual


def test_condition_telemetry_changes_do_not_change_observation():
    cfg,_,task,condition=c.configuration(.1)
    a=c.environment(cfg,fixture_backend(cfg),task,condition)
    cfg2=deepcopy(cfg);cfg2['backend']['pi_ki']=.15
    b=c.environment(cfg2,fixture_backend(cfg2),task,condition)
    try:
        x,_=a.reset(seed=701);y,_=b.reset(seed=701);np.testing.assert_array_equal(x,y)
        for _ in range(8):
            x,*_=a.step([0.]);y,*_=b.step([0.]);np.testing.assert_array_equal(x,y)
    finally:a.close();b.close()


@pytest.mark.parametrize('ki',[.1,.15])
def test_node_constructor_uses_parameter_override_as_cached_kernel_ki(ki,monkeypatch):
    from nino_rl import pi_screen_effort_drive as m
    monkeypatch.setattr(m,'require_simulation_environment',lambda *a:None)
    params=expected_parameters(ki);declared=[]
    def base_init(obj):
        obj.__dict__.update(fixture(1.).__dict__);obj.ki=ki
    monkeypatch.setattr(EffortDrive,'__init__',base_init)
    monkeypatch.setattr(PiScreenEffortDrive,'get_parameter',lambda obj,name:NS(value=params[name]))
    monkeypatch.setattr(PiScreenEffortDrive,'declare_parameter',lambda obj,*a:declared.append(a))
    monkeypatch.setattr(PiScreenEffortDrive,'create_publisher',lambda *a:Sink())
    obj=object.__new__(PiScreenEffortDrive);obj.__init__()
    assert obj.ki==ki and runtime_audit(obj)['velocity_ki']==ki
    assert declared[0][0]=='sim_common_gain' and declared[0][2].read_only
    # A request/parameter cannot conceal a different value in the kernel cache.
    params['velocity_ki']=.1 if ki==.15 else .15
    with pytest.raises(ValueError,match='velocity_ki'):obj.__init__()


def test_launch_builds_new_entry_with_typed_ki_and_disabled_old_drive():
    import importlib.util
    path=c.benchmark.repo()/'src/nino_rl/launch/training_sim_pi_screen.launch.py'
    spec=importlib.util.spec_from_file_location('pi_launch_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    launch=module.generate_launch_description()
    # Constructing launch actions is offline; never run a LaunchService.
    assert launch.entities
    source=path.read_text()
    assert 'executable="sim_pi_screen_effort_drive"' in source
    assert '"start_effort_drive": "false"' in source
    assert '"velocity_ki": ParameterValue(LaunchConfiguration("velocity_ki"),value_type=float)' in source


@pytest.mark.parametrize('fault',['missing_trace','tampered_trace','physics_claim'])
def test_artifact_verification_rejects_missing_changed_or_runtime_claim(tmp_path,monkeypatch,fault):
    import json
    from nino_rl import pi_screen_preflight as p
    source=tmp_path/'source';source.mkdir();(source/'manifest.json').write_text('{}')
    output=tmp_path/'artifact';output.mkdir();ident={'abi_sha256':'fixture'}
    monkeypatch.setattr(p.context,'fingerprint',lambda:'fixture')
    monkeypatch.setattr(p.context,'identity',lambda:ident)
    monkeypatch.setattr(p.context,'require_identity',lambda x:None if x==ident else pytest.fail('identity drift'))
    monkeypatch.setattr(p,'dependency',lambda:source)
    report=dict(abi_sha256='fixture',source_dynamics_artifact=str(source),
        source_dynamics_manifest_sha256=p.context.benchmark.sha(source/'manifest.json'),
        physics_released=False,benefit_verified=False,candidate_ki_response_identified=False,
        old_checkpoint_compatible=False,new_gazebo_launches=1 if fault=='physics_claim' else 0,
        new_physics_steps=0,actor_loads=0,optimizer_updates=0,training_transitions=0,hardware_actions=0)
    for name,data in {'qualification.json':report,'identity.json':ident,'driver_fixture_trace.json':[],
                      'wrapper_fixture_0.jsonl':[],'wrapper_fixture_1.jsonl':[]}.items():
        (output/name).write_text(json.dumps(data))
    files={f.name:p.context.benchmark.sha(f) for f in output.iterdir()}
    if fault=='missing_trace':files.pop('wrapper_fixture_1.jsonl')
    (output/'manifest.json').write_text(json.dumps(dict(status='completed',fingerprint='fixture',files=files)))
    if fault=='tampered_trace':(output/'driver_fixture_trace.json').write_text('[1]')
    with pytest.raises(ValueError):p.verified_report(output)
