from pathlib import Path
from types import SimpleNamespace
import sys
import json
import subprocess
import xml.etree.ElementTree as ET

import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl")]
from nino_rl.core import load_config
from nino_rl.evaluation import prepare_evaluation_config,benchmark_id
from nino_rl.routes import RouteSet
from nino_control.governor_core import GovernorSettings
from nino_rl.governor_adapter import frame_from_state,stamped_reference_valid
from nino_rl.governor_logger import finite_json


def test_profiles_share_physical_contract_and_are_not_training_configs():
    base=ROOT/"src/nino_rl/config"
    configs=[load_config(base/("factory_floor_governor_"+suffix+".yaml"))
             for suffix in ("pi_check","full","moderate","deep","pulse")]
    assert len({benchmark_id(c) for c in configs})==1
    for config in configs:
        GovernorSettings(**config["governor"]["parameters"])
        assert not config["research_map"]["training_allowed"]
        assert not config["research_map"]["optuna_allowed"]
        assert RouteSet(prepare_evaluation_config(config,baseline=True)).enabled
        assert config["reward_pose_source"]=="ground_truth"
    assert not load_config(base/"factory_floor_smoke.yaml").get("governor",{}).get("enabled",False)


def test_adapter_explicitly_uses_hardware_fields_only():
    class HardwareState(SimpleNamespace):
        def __getattr__(self,key):
            raise AssertionError("Unavailable/oracle field accessed: "+key)
    state=HardwareState(accel_x=0.,accel_y=0.,accel_z=9.80665,roll=0.,pitch=0.,
                        gyro_x=0.,gyro_y=0.,left_wheel_velocity=2.,right_wheel_velocity=2.)
    feedback=dict(left_target_rad_s=2.,right_target_rad_s=2.,executed_linear_m_s=.125)
    frame=frame_from_state(state,feedback,dict(duration=.1,square_integral=.4,peak=3.),True)
    assert frame.vertical_m_s2==pytest.approx(0.)
    assert frame.vertical_rms_m_s2==2. and frame.vertical_peak_m_s2==3.


def test_missing_or_nonfinite_data_remains_null_in_research_logs():
    row=finite_json(dict(impact=float("nan"),slip=float("inf"),contacts=[],failed=True))
    assert row==dict(impact=None,slip=None,contacts=[],failed=True)
    json.dumps(row,allow_nan=False)


def test_lockstep_reference_uses_stamped_fresh_measurements():
    state=SimpleNamespace(odom_stamp_s=10.,joint_stamp_s=10.,imu_stamp_s=9.98)
    assert stamped_reference_valid(state,10.,9.9,.1)
    assert not stamped_reference_valid(state,10.,9.0,.1)
    state.imu_stamp_s=9.
    assert not stamped_reference_valid(state,10.,9.9,.1)


def test_contact_sensors_reference_real_collisions_and_preview_is_optional(tmp_path):
    robot=ROOT/"src/nino_description/urdf/nino.urdf.xacro"
    urdf=subprocess.check_output(["xacro",str(robot),"contact_lab:=true","terrain_preview:=false"])
    path=tmp_path/"robot.urdf"
    path.write_bytes(urdf)
    sdf=ET.fromstring(subprocess.check_output(["gz","sdf","-p",str(path)]))
    sensors=sdf.findall("model/link/sensor[@type='contact']")
    assert len(sensors)==7
    for link in sdf.findall("model/link"):
        names={collision.get("name") for collision in link.findall("collision")}
        for sensor in link.findall("sensor[@type='contact']"):
            assert sensor.find("contact/collision").text in names
            assert sensor.find("contact/topic").text.startswith("/nino/contact_lab/")
    assert sdf.find("model/link/sensor[@name='terrain_preview_sensor']") is None
    assert sdf.find("model/plugin[@name='gz::sim::systems::OdometryPublisher']/dimensions").text=="3"
    ordinary=ET.fromstring(subprocess.check_output(["xacro",str(robot)]))
    assert ordinary.findall("gazebo/sensor[@type='contact']")==[]
    assert len(ordinary.findall("gazebo/sensor[@name='terrain_preview_sensor']"))==1
    candidate=ET.fromstring(subprocess.check_output(["xacro",str(robot),"caster_wheel_damping:=0.001"]))
    for side in ("left","right"):
        joint=f"joint[@name='caster_{side}_wheel_joint']/dynamics"
        assert float(ordinary.find(joint).get("damping"))==.01
        assert float(candidate.find(joint).get("damping"))==.001
        swivel=f"joint[@name='caster_{side}_swivel_joint']/dynamics"
        assert candidate.find(swivel).attrib==ordinary.find(swivel).attrib
