"""Offline timing isolation, real step-prefix integration and bounded executor."""
import ast
from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace, MethodType

import numpy as np
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from nino_control.governor_core import GovernorSettings,GovernorFrame,ReactiveGovernor
from nino_rl.governor_cadence import GovernorCadence,chunk_steps
import prepare_governor_cadence_experiment as plan
import run_governor_cadence_experiment as run
import analyze_governor_cadence_experiment as analysis


@pytest.fixture(autouse=True)
def forbid_processes(monkeypatch):
    import subprocess
    def forbidden(*a,**k):raise AssertionError("Offline test cannot start a process")
    monkeypatch.setattr(subprocess,"Popen",forbidden)
    monkeypatch.setattr(subprocess,"run",forbidden)


def test_schedule_exact12_balanced_and_deterministic():
    jobs=plan.schedule()
    assert jobs==plan.schedule() and len(jobs)==12
    for arm in plan.ARMS:
        assert sum(j["arm"]==arm for j in jobs)==4
    with pytest.raises(ValueError):plan.validate_schedule(jobs+jobs[:1])
    bad=deepcopy(jobs);bad[0]["cold_start"]=False
    with pytest.raises(ValueError):plan.validate_schedule(bad)


def test_only_governor_cadence_differs_all_physical_and_scoring_settings_fixed():
    c=plan.configs()
    fast=deepcopy(c["reactive_20ms"])
    assert fast["governor"].pop("cadence_experiment")==plan.CADENCE
    assert fast==c["reactive_100ms"]
    full=deepcopy(c["full"]);full["governor"]["parameters"]["profile"]="reactive"
    assert full==c["reactive_100ms"]
    assert fast["governor"]["parameters"]["confirmation_seconds"]==.04


def test_legacy_core_decisions_bit_identical_to_frozen_source():
    path=plan.PARENT/"source_snapshot/06_governor_core.py"
    spec=importlib.util.spec_from_file_location("frozen_cadence_reference",path)
    old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
    settings=plan.configs()["reactive_100ms"]["governor"]["parameters"]
    a,b=ReactiveGovernor(settings),old.ReactiveGovernor(settings)
    rng=np.random.default_rng(246)
    for i in range(400):
        values=dict(vertical_m_s2=float(rng.normal()*4),body_rate_rad_s=float(abs(rng.normal())),
            left_velocity_rad_s=float(rng.normal()+6),right_velocity_rad_s=float(rng.normal()+6),
            left_target_rad_s=float(rng.normal()*.2+6),right_target_rad_s=float(rng.normal()*.2+6),
            executed_linear_m_s=.4,vertical_rms_m_s2=2.,vertical_peak_m_s2=5.)
        v=0. if i%53==0 else .4
        assert a.update(GovernorFrame(**values),.1,v)==b.update(old.GovernorFrame(**values),.1,v)


class FakeRos:
    imu_includes_gravity=True
    def __init__(self):self.now=0.;self.commands=[];self.windows=[];self.steps=[];self.future=False;self.stale=False
    def wait_for_motion_state(self,now,**kwargs):assert abs(now-self.now)<1e-8
    def wait_for_drive_diagnostics(self,start,end,**kwargs):
        return [dict(sim_time_s=end,left_target_rad_s=6.4+end,right_target_rad_s=6.4+end,
                     executed_linear_m_s=.4,have_wheel_state=1.)]
    def snapshot(self):
        stamp=self.now+(.01 if self.future else -.2 if self.stale else 0.)
        return SimpleNamespace(accel_x=0.,accel_y=0.,accel_z=9.80665,roll=0.,pitch=0.,
            gyro_x=0.,gyro_y=0.,left_wheel_velocity=6.4,right_wheel_velocity=6.4,
            imu_stamp_s=stamp,joint_stamp_s=stamp)
    def wait_for_impact(self,a,b,*args):
        self.windows.append((a,b));return dict(duration=b-a,square_integral=.4*(b-a),peak=9.)
    def publish_motion_command(self,v,w):self.commands.append((self.now,v,w))
    def publish_control(self,*args):pass
    def sensor_markers(self,names):return {}
    def advance_world(self,steps,**kwargs):self.steps.append(steps);self.now+=steps*.001;return steps*.001


def environment():
    config=plan.configs()["reactive_20ms"];config["evaluation_baseline"]=True
    ros=FakeRos()
    e=SimpleNamespace(config=config,ros=ros,control_dt=.1,governor=ReactiveGovernor(config["governor"]["parameters"]),
        governor_trace={},cadence_emit=lambda p:None)
    e.governor_cadence=GovernorCadence(e)
    return e


def test_full100ms_feature_window_not20ms_and_target_derivative_uses100ms():
    e=environment();c=e.governor_cadence
    for i in range(11):
        t=i*.02;e.ros.now=t
        if i%5==0:c.begin(.4,0.,t)
        else:c.boundary(t,(i%5)*.02)
    assert len(e.ros.windows)==10
    assert all(b-a==pytest.approx(.1) for a,b in e.ros.windows)
    assert c.updates[0]["target_acceleration_m_s2"]==pytest.approx(.0625)
    assert c.updates[0]["target_history_support_s"]==pytest.approx(.1)
    assert c.updates[0]["imu_window_start_s"]==pytest.approx(.1)


@pytest.mark.parametrize("field",["future","stale"])
def test_stale_or_future_feedback_stops_without_retry(field):
    e=environment();setattr(e.ros,field,True)
    with pytest.raises(RuntimeError):e.governor_cadence.begin(.4,0.,0.)
    assert e.ros.commands==[(0.,0.,0.)]
    assert e.ros.steps==[]


def test_reset_discards_target_history_and_skipped_ticks_rejected():
    e=environment();c=e.governor_cadence;c.begin(.4,0.,0.)
    e.ros.now=.04
    with pytest.raises(RuntimeError,match="Skipped"):c.command(.04)
    c.reset();e.governor.reset();c.begin(.4,0.,.04)
    assert len(c.history)==1 and not c.updates[0]["target_history_ready"]


def methods(path):
    tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="NinoGazeboEnv")
    return {n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}


@pytest.mark.parametrize("arm",plan.ARMS)
def test_actual_environment_step_prefix_advances_exact100ms_and_issues5_commands(arm,monkeypatch):
    """Execute the production step up to score boundary with deterministic IO."""
    nodes=methods(ROOT/"src/nino_rl/nino_rl/ros_env.py")
    prefix=deepcopy(nodes["step"])
    stop=next(i for i,n in enumerate(prefix.body) if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=="ended_sim" for t in n.targets))
    prefix.body=prefix.body[:stop+1]+[ast.parse("return ended_sim").body[0]]
    namespace=dict(np=np,json=json,BASELINE_ACTION=np.array([1.,0.,0.]),
        decode_control=lambda *a,**k:(1.,np.zeros(2),0.),route_command=lambda *a:(.4,0.))
    module=ast.fix_missing_locations(ast.Module(body=[prefix,deepcopy(nodes["_governor_command"])],type_ignores=[]))
    exec(compile(module,"<actual_step_prefix>","exec"),namespace)
    e=environment()
    if arm != "reactive_20ms":
        e.config=plan.configs()[arm];e.config["evaluation_baseline"]=True
        e.governor_cadence=None
        e.governor=ReactiveGovernor(e.config["governor"]["parameters"])
        e.governor_imu={};e.governor_epoch_sim_s=None
        e.governor_state_publisher=SimpleNamespace(publish=lambda m:None)
        monkeypatch.setitem(sys.modules,"std_msgs.msg",SimpleNamespace(String=lambda **kw:SimpleNamespace(**kw)))
    e.world_is_paused=True;e.lockstep_sim_time=0.;e.previous_tracking=SimpleNamespace(distance_remaining=6.)
    e.previous_robot_state=e.ros.snapshot();e.route_set=SimpleNamespace(enabled=True);e.path=None
    e.episode_started_sim=0.;e._reference=lambda *a:None
    e._randomization=dict(delay=0.,traction=1.,torque_noise=0.)
    e.physics_dt=.001;e.physics_steps_per_control=100;e.simulation_step_timeout=2.
    e.lockstep_min_completion_fraction=.8;e.action_scale=2.;e.np_random=np.random.default_rng(1)
    e._governor_command=MethodType(namespace["_governor_command"],e)
    end=namespace["step"](e,np.array([1.,0.,0.]))
    assert end==pytest.approx(.1) and sum(e.ros.steps)==100
    assert e.ros.steps==[20,20,20,20,20]
    assert [t for t,_,_ in e.ros.commands]==pytest.approx([0.,.02,.04,.06,.08] if arm=="reactive_20ms" else [0.])
    if arm=="reactive_20ms":assert len(e.governor_cadence.updates)==5
    assert e.governor_trace["governor_input_time_s"]==0.  # preserve coarse trace origin


def test_native_scoring_tail_and_legacy_governor_path_unchanged():
    new=methods(ROOT/"src/nino_rl/nino_rl/ros_env.py")
    old=methods(plan.PARENT/"source_snapshot/12_ros_env.py")
    a,b=deepcopy(new["_governor_command"]),deepcopy(old["_governor_command"])
    a.body=a.body[1:]
    assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
    def tail(node):
        node=deepcopy(node)
        start=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=="ended_sim" for t in n.targets))
        class RemoveTrace(ast.NodeTransformer):
            def visit_If(self,n):
                if isinstance(n.test,ast.Compare) and ast.unparse(n.test)=="self.governor_cadence is not None":
                    return None
                return self.generic_visit(n)
        node.body=node.body[start:]
        return ast.dump(RemoveTrace().visit(node),include_attributes=False)
    assert tail(new["step"])==tail(old["step"])


def test_40ms_confirmation_and_ramp_remain_seconds_not_frames():
    c=GovernorSettings(startup_seconds=0.,confirmation_seconds=.04,target_scale=.9)
    g=ReactiveGovernor(c)
    f=GovernorFrame(0.,1.,6.,6.,6.,6.,.4)
    assert g.update(f,.02,.4)["events"]==0
    assert g.update(f,.02,.4)["events"]==1
    assert g.scale==pytest.approx(.992)  # .4/s *20ms, not40ms per fast frame
    for i in range(12):g.update(f,.02,.4)
    assert g.scale==pytest.approx(.9)


def test_12_fake_attempts_ledger_before_adapter_and_no_simulation(tmp_path):
    protocol=dict(schedule=plan.schedule())
    seen=[];root=tmp_path/"dry"
    def fake(job,attempt):
        stored=json.loads((root/"ledger.json").read_text())["slots"][job["attempt"]-1]
        assert stored["adapter_requested"] and not stored["launch_requested"]
        seen.append(job);return run.synthetic(job,attempt)
    result=run.run_attempts(protocol,root,fake)
    assert len(seen)==12 and result["simulation_launches"]==0
    assert not result["unattempted"] and not result["thresholds_applied"]
    assert json.loads((root/"authorization_snapshot.json").read_text())["execution_authorized"] is False
    with pytest.raises(FileExistsError):run.run_attempts(protocol,root,fake)
    with pytest.raises(ValueError,match="execution release"):
        run.run_attempts(protocol,tmp_path/"unauthorized",fake,dry_run=False)


def test_ordinary_failure_and_missing_quality_retained_no_replacement(tmp_path):
    def fake(job,attempt):
        r=run.synthetic(job,attempt)
        if job["attempt"]==1:r.update(physical_success=False,termination="stall",quality_available=False,quality=None,stop_pass=None)
        return r
    s=run.run_attempts(dict(schedule=plan.schedule()),tmp_path/"failed",fake)
    assert s["physical_failures"]==1 and s["adapter_calls"]==12
    assert s["retries"]==s["replacements"]==0


@pytest.mark.parametrize("failure",["measurement_integrity_pass","cleanup_confirmed","stop_pass"])
def test_hard_fault_stops_without_extra_attempt(failure,tmp_path):
    def fake(job,attempt):
        r=run.synthetic(job,attempt);r[failure]=False;return r
    s=run.run_attempts(dict(schedule=plan.schedule()),tmp_path/"halt",fake)
    assert s["adapter_calls"]==1 and len(s["unattempted"])==11


def test_micro_trace_missing_or_wrong_window_is_not_accepted(tmp_path):
    episode=tmp_path/"episode-001";episode.mkdir()
    with (episode/"control_trace.csv").open("w") as f:
        w=csv.DictWriter(f,fieldnames=["governor_input_time_s","sim_time_s"]);w.writeheader();w.writerow(dict(governor_input_time_s=1.,sim_time_s=1.1))
    assert not run.cadence_trace_check(tmp_path,"reactive_20ms")["valid"]
    assert run.cadence_trace_check(tmp_path,"reactive_100ms")["valid"]
    e=environment();c=e.governor_cadence
    for i in range(5):
        e.ros.now=i*.02
        if i==0:c.begin(.4,0.,0.)
        else:c.boundary(e.ros.now,e.ros.now)
    rows=deepcopy(c.updates)
    for row in rows:
        for key in ("governor_input_time_s","imu_window_start_s","imu_window_end_s","imu_stamp_s","joint_stamp_s","governor_feedback_stamp_s"):
            row[key]+=1.
    def save():
        with (episode/"governor_update_trace.csv").open("w") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    save();assert run.cadence_trace_check(tmp_path,"reactive_20ms")["valid"]
    rows[1]["imu_window_start_s"]+=.08;save()
    assert not run.cadence_trace_check(tmp_path,"reactive_20ms")["valid"]


def test_statistics_keep_all3_contrasts_and_missing_does_not_become_success_mean():
    rows=[]
    for job in plan.schedule():
        scale={"full":1.,"reactive_100ms":.9,"reactive_20ms":.8}[job["arm"]]
        rows.append(dict(**job,metrics={k:scale for k in analysis.METRICS}))
    stats=analysis.estimate(rows)
    assert len(stats)==3
    a=stats["reactive_20ms_minus_reactive_100ms"]["post_slip"]["aggregate"]
    assert a["delta"]==pytest.approx(-.1)
    assert a["relative_benefit"]==pytest.approx(1-.8/.9)
    rows[0]["metrics"]["post_slip"]=None
    b=analysis.estimate(rows)["reactive_20ms_minus_full"]["post_slip"]["aggregate"]
    assert b["delta"] is None and b["delta_CI95"] is None


def test_preintervention_quadrature_support_not_silently_called_negative_control():
    t=np.arange(0.,.101,.02)
    s=dict(time=t,q=np.ones(len(t)),xy=np.column_stack((t,t*0)),
           joint_support_stamps=np.column_stack((t,t)))
    v=analysis.diagnostic_window(s,.01,.055)
    assert v["metric"]["slip_square_integral_s"]==pytest.approx(.045)
    assert v["latest_sensor_support_s"]==pytest.approx(.06)
    assert not v["all_support_precedes_intervention"]


def test_preparation_hashes_and_pending_release_do_not_authorize_simulation(tmp_path):
    bundle=tmp_path/"bundle"
    result=plan.prepare(bundle)
    assert not result["execution_authorized"] and not result["simulator_started"]
    assert result["maximum_attempts"]==12
    release=tmp_path/"release.json"
    release.write_text(json.dumps(dict(maximum_attempts=12,budget_released=False)))
    with pytest.raises(ValueError):run.require_release(bundle,release)
    path=bundle/"inputs/reactive_20ms.yaml"
    path.write_text(path.read_text()+"\n# drift\n")
    with pytest.raises(ValueError,match="input drift"):plan.validate(bundle)
