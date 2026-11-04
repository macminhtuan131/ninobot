"""World/metric/budget tests, no simulation processes."""
from copy import deepcopy
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import pytest
from nino_rl import residual_sim_pilot as p


def test_controlled_worlds_do_not_fill_original_depressions(tmp_path,monkeypatch):
    source=p.repo()/'src/nino_description/worlds/factory_floor_mixed.sdf'
    def prepared(out):
        dest=out/'world.sdf';dest.write_bytes(source.read_bytes());return {},dest
    monkeypatch.setattr(p,'prepare_factory',prepared)
    worlds=p.prepare_worlds(tmp_path)
    assert worlds['mixed_original_22mm'].read_bytes()==source.read_bytes()
    clear=ET.parse(worlds['clear_box']);small=ET.parse(worlds['box_c1_6mm'])
    assert clear.find('.//model[@name="factory_contact_floor"]') is None
    assert clear.find('.//model[@name="controlled_box_floor"]') is not None
    assert clear.find('.//model[@name="cable_bumps"]') is None
    assert small.find('.//collision[@name="C1_collision"]/geometry/cylinder/radius').text=='0.003'
    assert small.find('.//collision[@name="C2_collision"]') is None
    original=ET.parse(worlds['mixed_original_22mm'])
    assert original.find('.//collision[@name="C1_collision"]/geometry/cylinder/radius').text=='0.011'
    assert original.find('.//model[@name="controlled_box_floor"]') is None


def test_pilot_is_not_dependent_on_real_dataset_or_hardware_release():
    c=p.config()
    assert c['training']['allowed'] is False and c['hardware_authority']==0
    assert c['pilot']['training_transitions']==256 and c['pilot']['learner_seed']==7
    assert c['backend']['command_until_s']==8. and c['backend']['horizon_s']==10.
    assert c['actor']['history_frames']==5 and c['simulation_authority']==1.
    assert c['reference_limits']['residual_wheel_m_s']==.04
    assert c['pilot']['minimum_effect_accepted'] is None


def test_metric_keeps_physical_failure_and_does_not_call_progress_benefit():
    row=dict(truth_pose_m_rad=[.2,.01,0.],body_speed_m_s=.1,applied_target_rad_s=[2.,2.],
        feedback_wheel_rad_s=[1.,1.],final_ros_reference=[.2,0.],sensor_clock_s=1.,reward=-.5,
        terminated=True,truncated=False,
        reference_trace=dict(input_stamp_s=.9,original_baseline_body=[.2,0.],reference_modified=True,
            accepted_policy_delta_wheel_m_s=[0.,0.]))
    result=p.describe([row],[])
    assert result['physical_failure'] and not result['local_marker_reached']
    assert result['wheel_target_rmse_rad_s']==[1.,1.]
    assert result['local_marker_time_s'] is None and result['return_value']==-.5
