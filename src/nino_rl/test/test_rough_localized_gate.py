"""Prevent PPO startup on unqualified or incomparable PI reports."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/nino_rl'))
from nino_rl.core import load_config
from nino_rl.evaluation import prepare_evaluation_config
spec=importlib.util.spec_from_file_location('rough_runner',ROOT/'src/nino_rl/scripts/run_rough_localized.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def evidence(tmp_path,monkeypatch):
    cfg=load_config(ROOT/'src/nino_rl/config/rough_turn_cloud_candidate.yaml')
    monkeypatch.setattr(runner,'EXPERIMENT',tmp_path)
    monkeypatch.setattr(runner,'verify',lambda: None)
    (tmp_path/'manifest.json').write_text(json.dumps({'config':cfg}))
    for route,seeds,speed in [('E1',[10000,10003,10006],1.),('N1',[10001,10004,10007],1.),
                             ('S1',[10002,10005,10008],1.),('E1',[10000,10003,10006],.65)]:
        directory=(tmp_path/'pi'/route/'run' if speed==1. else tmp_path/'slow_e1'/'run')
        directory.mkdir(parents=True)
        (directory/'summary.json').write_text(json.dumps({'complete':True,'evaluation_seeds':seeds,
            'controller':'path_pi_baseline','baseline_speed_scale':speed}))
        (directory/'config.yaml').write_text(yaml.safe_dump(prepare_evaluation_config(cfg,route=route,
            baseline=True,control_trace=True)))
        with (directory/'episodes.csv').open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=['success','truth_endpoint_error_m','odom_truth_position_error_m',
                'route_gates_passed','route_gates_total'])
            writer.writeheader()
            for index,seed in enumerate(seeds,1):
                writer.writerow({'success':True,'truth_endpoint_error_m':.15,
                    'odom_truth_position_error_m':.02,'route_gates_passed':9,'route_gates_total':9})
                trace=directory/f'episode-{index:03d}'/'control_trace.csv'
                trace.parent.mkdir()
                with trace.open('w') as output:
                    fields=['elapsed_s','raw_wheel_stamp_s','raw_wheel_x_m','raw_wheel_y_m',
                            'physical_speed_m_s','physical_goal_distance_m','speed_scale','physical_x_m','physical_y_m']
                    tr=csv.DictWriter(output,fieldnames=fields);tr.writeheader()
                    for i in range(3):
                        tr.writerow(dict(zip(fields,[i*.1,1+i*.1,i*.02,0.,.2,1.,1.,i*.02,0.])))
    return tmp_path


def test_comparable_physical_pi_passes(evidence):
    runner.physical_gate()
    assert json.loads((evidence/'pi_gate.json').read_text())['passed']


@pytest.mark.parametrize('field,value',[('truth_endpoint_error_m','0.21'),
    ('odom_truth_position_error_m','0.2'),('route_gates_passed','8'),('success','False')])
def test_physical_failure_or_localization_drift_blocks_training(evidence,field,value):
    path=evidence/'pi/S1/run/episodes.csv'
    rows=list(csv.DictReader(path.open()))
    rows[0][field]=value
    with path.open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    with pytest.raises(RuntimeError,match='gate failed'):runner.physical_gate()


def test_wrong_seeds_are_not_qualification(evidence):
    path=evidence/'pi/N1/run/summary.json'
    obj=json.loads(path.read_text());obj['evaluation_seeds']=[1,2,3];path.write_text(json.dumps(obj))
    with pytest.raises(RuntimeError,match='Incomplete PI'):runner.physical_gate()


def test_relaxed_physical_criteria_are_not_qualification(evidence):
    path=evidence/'pi/N1/run/config.yaml'
    obj=yaml.safe_load(path.read_text());obj['goal_tolerance_m']=.5;path.write_text(yaml.safe_dump(obj))
    with pytest.raises(RuntimeError,match='config differs'):runner.physical_gate()


def test_missing_slow_crest_validation_blocks_training(evidence):
    (evidence/'slow_e1/run/summary.json').unlink()
    with pytest.raises(RuntimeError,match='Missing PI validation for E1_slow'):
        runner.physical_gate()


def test_arrival_after_prolonged_physical_wheel_spin_is_not_ready(evidence):
    path=evidence/'pi/S1/run/episode-002/control_trace.csv'
    rows=list(csv.DictReader(path.open()))
    rows[1].update(elapsed_s='3',raw_wheel_stamp_s='4',raw_wheel_x_m='.6',physical_speed_m_s='0')
    rows[2].update(elapsed_s='3.1',raw_wheel_stamp_s='4.1',raw_wheel_x_m='.62',physical_speed_m_s='0')
    with path.open('w') as stream:
        tr=csv.DictWriter(stream,fieldnames=rows[0]);tr.writeheader();tr.writerows(rows)
    with pytest.raises(RuntimeError,match='gate failed'):runner.physical_gate()
    gate=json.loads((evidence/'pi_gate.json').read_text())
    assert gate['routes']['S1']['physical_arrival_passed']
    assert not gate['routes']['S1']['stall_passed']


def test_missing_physical_trace_cannot_pass(evidence):
    (evidence/'pi/E1/run/episode-001/control_trace.csv').unlink()
    with pytest.raises(RuntimeError,match='Missing physical control trace'):runner.physical_gate()


def test_sideways_physical_translation_is_not_a_stall(evidence):
    path=evidence/'pi/S1/run/episode-002/control_trace.csv'
    rows=list(csv.DictReader(path.open()))
    for i,row in enumerate(rows):
        row.update(elapsed_s=str(i*3),raw_wheel_stamp_s=str(1+i*3),raw_wheel_x_m=str(i*.6),
                   physical_speed_m_s='0',physical_x_m='0',physical_y_m=str(i*.6))
    with path.open('w') as stream:
        tr=csv.DictWriter(stream,fieldnames=rows[0]);tr.writeheader();tr.writerows(rows)
    assert runner.longest_commanded_stall(path)==0.
