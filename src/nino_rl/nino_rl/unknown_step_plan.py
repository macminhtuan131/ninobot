"""Prepare a versioned hidden-layout bank and short engineering protocol offline."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from . import equal_information_v2 as inherited
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import save
from .unknown_step_geometry import collision_envelope, sha
from .unknown_step_runtime import CONTRACT_ID, TaskSettings, RewardSettings

PROTOCOL = repo()/'src/nino_rl/config/unknown_step_short_integration_v1.json'


def protocol():
    p = json.loads(PROTOCOL.read_text())
    if (p['control_interval_s'] != .1 or p['budget']['smoke_training_transitions'] != 384
            or p['budget']['maximum_launches'] != 8 or p['budget']['long_training_allowed']
            or p['bank']['metadata_actor_input'] or p['budget']['hardware_actions']):
        raise ValueError('Changed scope requires a new bounded protocol')
    groups = [p['bank'][k] for k in ('development', 'validation_reserved_not_run', 'test_reserved_not_run')]
    ids = [v['id'] for group in groups for v in group]
    positions = [v['bump_x_m'] for group in groups for v in group if v['bump_x_m'] is not None]
    if len(ids) != len(set(ids)) or len(positions) != len(set(positions)):
        raise ValueError('Layout IDs/positions overlap between split banks')
    return p


def configuration():
    p = protocol()
    c, g, task, condition = inherited.configuration(6., 'box_c1_6mm')
    c['purpose'] = CONTRACT_ID
    c['backend'].update(scenario_id=CONTRACT_ID, horizon_s=p['horizon_s'],
                        command_until_s=p['horizon_s'], max_episodes=1)
    c['task'].update(command_until_s=p['horizon_s'], horizon_s=p['horizon_s'])
    g.update(baseline_id=CONTRACT_ID+'_follower', path_points_m=p['route_m'],
             goal_tolerance_m=p['goal_tolerance_m'])
    task.update(protocol_id=CONTRACT_ID, command_until_s=p['horizon_s'],
                horizon_s=p['horizon_s'], warmup_s=p['source_warmup_s'])
    condition.update(scenario=CONTRACT_ID)
    return c, g, task, condition


def task_settings(envelope, layout):
    p = protocol()
    x, radius = layout['bump_x_m'], p['bank']['bump_radius_m']
    return TaskSettings(route_m=tuple(map(tuple, p['route_m'])),
        envelope_m=tuple(map(tuple, envelope['corners_m'])), envelope_identity=envelope['sha256'],
        obstacle_near_m=None if x is None else x-radius,
        obstacle_far_m=None if x is None else x+radius, clearance_m=p['clearance_m'],
        interval_s=.1, maximum_source_age_s=p['maximum_source_age_s'], maximum_seconds=p['horizon_s'],
        goal_tolerance_m=p['goal_tolerance_m'], goal_heading_tolerance_rad=p['goal_heading_tolerance_rad'],
        maximum_cross_track_m=p['maximum_cross_track_m'], continuous_stop_s=p['continuous_stop_s'],
        stop_body_speed_m_s=.01, stop_yaw_rad_s=.05, stop_wheel_rad_s=.15,
        stop_reference_m_s=1e-6, stall_window_s=p['stall_window_s'], stall_progress_m=p['stall_progress_m'],
        maximum_tilt_rad=.7, minimum_body_z_m=-.15)


def prepare(out):
    import xacro
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    p = protocol()
    worlds = prepare_worlds(out)
    expanded = xacro.process_file(str(repo()/'src/nino_description/urdf/nino.urdf.xacro'),
        mappings=dict(contact_lab='true', terrain_preview='false', caster_wheel_damping='0.001')).toprettyxml(indent='  ')
    urdf = out/'reference_robot.urdf'
    urdf.write_text(expanded)
    envelope = collision_envelope(urdf, repo()/'src/nino_description')
    save(out/'collision_envelope.json', envelope)
    bank = []
    for split in ('development', 'validation_reserved_not_run', 'test_reserved_not_run'):
        for layout in p['bank'][split]:
            target = out/(layout['id']+'.sdf')
            source = worlds['clear_box' if layout['bump_x_m'] is None else 'box_c1_6mm']
            tree = ET.parse(source)
            if layout['bump_x_m'] is not None:
                for kind in ('collision', 'visual'):
                    node = tree.find(f".//{kind}[@name='C1_{kind}']")
                    node.find('pose').text = f"{layout['bump_x_m']} 0 {p['bank']['bump_radius_m']} 1.57079632679 0 0"
            tree.write(target, encoding='utf-8', xml_declaration=True)
            settings = task_settings(envelope, layout)
            if (layout['bump_x_m'] is not None
                    and envelope['bounds_m'][1][0] >= settings.obstacle_near_m-p['clearance_m']):
                raise ValueError('Robot does not start entirely before hidden obstacle')
            bank.append(dict(**layout, split=split, world=str(target), world_sha256=sha(target),
                             task_settings=asdict(settings)))
    save(out/'protocol.json', p)
    save(out/'configuration.json', dict(zip(('config', 'guidance', 'task', 'condition'), configuration())))
    save(out/'bank.json', dict(protocol_sha256=sha(PROTOCOL), envelope=envelope,
                               layouts=bank, actor_preview=False,
                               reserved_bank_is_generalization_evidence=False))
    save(out/'reward_settings.json', asdict(RewardSettings(**p['reward'])))
    return dict(protocol=p, envelope=envelope, layouts=bank)
