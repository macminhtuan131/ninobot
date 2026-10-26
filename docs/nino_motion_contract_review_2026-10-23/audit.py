"""Offline motion-contract extraction and synthetic IMU feature example.

Never initializes ROS, imports launch files, calls a controller or changes
runtime config. Output belongs to this review, not to a simulation batch.
"""
import ast
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/nino_rl')]
from nino_rl.control_v2 import ImuWindow
import yaml


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_yaml(relative):
    return yaml.safe_load((ROOT/relative).read_text())


def main():
    output=Path(__file__).parent
    core_path='src/nino_control/nino_control/governor_core.py'
    wrapper_path='src/nino_control/nino_control/speed_governor.py'
    core_ast=ast.parse((ROOT/core_path).read_text())
    settings=next(n for n in core_ast.body if isinstance(n,ast.ClassDef) and n.name=='GovernorSettings')
    defaults={n.target.id:ast.literal_eval(n.value) for n in settings.body if isinstance(n,ast.AnnAssign)}
    hardware=read_yaml('src/nino_control/config/speed_governor.yaml')['nino_speed_governor']['ros__parameters']
    wrapper_resolved={k:hardware.get(k,v) for k,v in defaults.items()}
    frozen_dir='docs/governor_isolated_cadence_contract_v7_2026-10-23'
    frozen=read_yaml(frozen_dir+'/inputs/reactive_20ms.yaml')
    frozen_resolved={k:frozen['governor']['parameters'].get(k,v) for k,v in defaults.items()}
    differences={k:dict(wrapper_candidate=wrapper_resolved[k],frozen_inline=frozen_resolved[k])
                 for k in defaults if wrapper_resolved[k]!=frozen_resolved[k]}
    control=read_yaml('src/nino_pi/config/control.yaml')
    gate=control['nino_command_gate']['ros__parameters']
    smoother=control['velocity_smoother']['ros__parameters']
    wrapper_ast=ast.parse((ROOT/wrapper_path).read_text())
    node_class=next(n for n in wrapper_ast.body if isinstance(n,ast.ClassDef) and n.name=='SpeedGovernor')
    functions={n.name:n for n in node_class.body if isinstance(n,ast.FunctionDef)}
    required=next(ast.literal_eval(n.value) for n in ast.walk(functions['on_feedback'])
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='required' for t in n.targets))

    # At t=100ms, a 20ms impulse already consumed at a prior wrapper tick
    # remains inside a trailing100ms window. This checks feature semantics,
    # not trigger decisions, real noise or physical controller performance.
    samples=[(ms/1000.,10. if ms==20 else 0.) for ms in (0,20,40,60,80,100)]
    window=ImuWindow()
    for stamp,value in samples:window.add(stamp,value)
    measured=window.measure(0.,.1)
    new=[v for t,v in samples if t>.04]  # last wrapper use at40ms
    feature_example=dict(kind='synthetic_feature_replay_not_robot_data',samples=samples,
        decision_s=.1,wrapper_last_imu_used_s=.04,
        wrapper_since_last_used_rms=math.sqrt(sum(v*v for v in new)/len(new)),
        wrapper_since_last_used_peak=max(map(abs,new)),
        production_ImuWindow_100ms=measured,
        production_100ms_rms=math.sqrt(measured['square_integral']/measured['duration']),
        qualification='Demonstrates unequal summary features only; no core update or trigger outcome evaluated.')

    protocol=json.loads((ROOT/frozen_dir/'protocol.json').read_text())
    manifest=json.loads((ROOT/frozen_dir/'prepared_manifest.json').read_text())
    assert sha(ROOT/frozen_dir/'protocol.json')==manifest['protocol_sha256']
    assert all(sha(ROOT/p)==h for p,h in protocol['execution_dependency_sha256'].items())
    files=[core_path,wrapper_path,'src/nino_control/nino_control/effort_drive.py',
        'src/nino_control/config/speed_governor.yaml','src/nino_control/config/effort_drive.yaml',
        'src/nino_control/config/controllers.yaml','src/nino_pi/launch/command_stack.launch.py',
        'src/nino_pi/launch/navigation.launch.py','src/nino_pi/launch/teleop.launch.py',
        'src/nino_pi/nino_pi/command_gate.py','src/nino_pi/nino_pi/selection.py',
        'src/nino_pi/config/control.yaml','src/nino_pi/config/navigation.yaml',
        'src/nino_pi/config/real_collection.json','src/nino_pi/config/real_collection_qos.yaml',
        'src/nino_pi/config/real_session.template.json','src/nino_rl/nino_rl/governor_cadence.py',
        'src/nino_rl/nino_rl/governor_adapter.py','src/nino_rl/nino_rl/control_v2.py',
        frozen_dir+'/inputs/reactive_20ms.yaml',frozen_dir+'/inputs/reactive_100ms.yaml']
    result=dict(mode='offline_source_contract_review',date='2026-10-23',
        simulation_launches=0,ros_nodes_started=0,hardware_access=False,controller_updates=0,
        runtime_config_changes=False,release_created=False,thresholds_accepted=False,
        core_defaults=defaults,wrapper_core_settings_candidate=wrapper_resolved,
        frozen_inline_core_settings=frozen_resolved,core_setting_differences=differences,
        candidate_wrapper_launch_limits=dict(max_forward_m_s=gate['max_forward'],
            max_reverse_m_s=gate['max_reverse'],max_yaw_rad_s=gate['max_yaw'],
            max_linear_acceleration_m_s2=smoother['max_accel'][0],
            max_linear_deceleration_m_s2=abs(smoother['max_decel'][0]),
            max_yaw_acceleration_rad_s2=min(abs(smoother['max_accel'][2]),abs(smoother['max_decel'][2]))),
        wrapper_required_feedback_fields=list(required),
        wrapper_method_lines={k:dict(start=v.lineno,end=v.end_lineno) for k,v in functions.items()},
        feature_example=feature_example,
        baseline_config=control,
        nominal_reference_math=dict(baseline_forward_limit_m_s=gate['max_forward'],
            wheel_target_at_nominal_radius_rad_s=gate['max_forward']/defaults['wheel_radius_m'],
            ideal_reference_deceleration_time_s=gate['max_forward']/abs(smoother['max_decel'][0]),
            qualification='Config arithmetic only; not a measured motor speed or stopping bound.'),
        v7_protocol_sha256=manifest['protocol_sha256'],
        v7_execution_dependencies_unchanged=len(protocol['execution_dependency_sha256']),
        input_sha256={p:sha(ROOT/p) for p in files},script_sha256=sha(__file__),
        qualification='Source/YAML projection, not resolved installed ROS parameters or verified hardware state.')
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('mode','core_setting_differences',
        'candidate_wrapper_launch_limits','feature_example','v7_execution_dependencies_unchanged')},indent=2))


if __name__=='__main__':main()
