"""Observation-only acquisition recipes; no motor procedures or authority changes."""
from copy import deepcopy
import json
from pathlib import Path

SCENARIOS = {
    'stationary': ('Đứng yên / sensor baseline', 'sensor_inventory', False),
    'straight': ('Chạy thẳng / wheel response', 'real_sysid', True),
    'rotation': ('Quay tại chỗ / yaw response', 'real_sysid', True),
    'curve': ('Đường cong / coupled response', 'real_sysid', True),
    'stop_go': ('Tăng giảm tốc / transient', 'real_sysid', True),
    'heldout': ('Điều kiện giữ riêng / evaluation', 'real_evaluation', True),
}


def config_root():
    root = Path(__file__).resolve().parents[1]/'config'
    if not root.is_dir():
        from ament_index_python.packages import get_package_share_directory
        root = Path(get_package_share_directory('nino_pi'))/'config'
    return root


def collection_config(scenario, storage='mcap'):
    if scenario not in SCENARIOS or storage not in ('mcap', 'sqlite3'):
        raise ValueError('Unknown scenario/storage')
    source = 'real_collection_residual_diagnostic.json' if SCENARIOS[scenario][2] else 'stm32_usb_collection.json'
    config = json.loads((config_root()/source).read_text())
    config.pop('storage_preset_profile', None)
    config.update(profile_id='studio_observer_'+scenario+'_v1', duration_s=60, storage_id=storage)
    # Enable is an event channel, not a mandatory sample in an observation-only session.
    for row in config['topics']:
        if row['name'] == '/motor_enable':
            row['required'] = False
    names={row['name'] for row in config['topics']}
    for name,purpose in [('/nino/residual/shadow_trace','Existing ROS shadow JSON trace if running; requested/projected reference is not actuator readback'),
            ('/nino/control_state','Optional firmware GUI authority telemetry only if actually supported by flashed binary'),
            ('/battery_state','Optional reported power telemetry'),('/diagnostics','Optional reported driver/system faults')]:
        if name not in names:config['topics'].append(dict(name=name,required=False,purpose=purpose))
    return config


def validate_metadata(value):
    expected = {'scenario', 'robot_id', 'pose_caster_note', 'floor_load_note', 'operator', 'protocol_id',
                'body_reference', 'firmware_identity', 'controller_identity', 'conditions_confirmed', 'storage'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError('Missing/unknown Studio metadata fields')
    if value['scenario'] not in SCENARIOS or value['storage'] not in ('mcap', 'sqlite3'):
        raise ValueError('Invalid scenario/storage')
    for key in expected-{'scenario', 'conditions_confirmed', 'storage'}:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 2000:
            raise ValueError('Fill '+key+'; unknown is allowed for unmeasured evidence')
    if value['conditions_confirmed'] is not True:
        raise ValueError('Confirm observation conditions before recording')
    if SCENARIOS[value['scenario']][2] and value['protocol_id'].strip().lower() in ('unknown', 'chưa biết', 'none'):
        raise ValueError('Motion observation needs an existing reviewed protocol ID; choosing a scenario does not authorize motion')
    return deepcopy(value)
