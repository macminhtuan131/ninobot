"""Immutable four-family geometry plans. Mesh preparation is not contact proof."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import yaml

from .carved_floor import floor_model
from .recovery_contract import CONTRACT_ID, StartBudget
from .recovery_curriculum import FAMILIES
from .recovery_task import RecoveryBands
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import save
from . import unknown_step_plan

CONFIG = repo()/'src/nino_rl/config/recovery_v2.yaml'


def configuration(path=CONFIG):
    c = yaml.safe_load(Path(path).read_text())
    if (c['schema_version'] != 2 or c['contract_id'] != CONTRACT_ID or c['interval_s'] != .1
            or c['budget']['hardware_actions'] != 0 or c['budget']['automatic_retries'] != 0):
        raise ValueError('Unsupported recovery contract')
    StartBudget(**c['start_budget'])
    RecoveryBands(**c['recovery_bands'])
    if c['route_m'] != [[0., 0.], [4., 0.]]:
        raise ValueError('Initial Gazebo recovery release supports fixed 4 m east route only')
    return c


def sample_layout(config, family, seed, stage, split='development'):
    if family not in FAMILIES or split not in ('development', 'validation', 'test'):
        raise ValueError('Unknown family or split')
    if type(stage) is not int or not 0 <= stage <= config['curriculum']['maximum_stage']:
        raise ValueError('Invalid sampled stage')
    rng = np.random.default_rng(np.random.SeedSequence([seed, FAMILIES.index(family),
                                                       ('development', 'validation', 'test').index(split)]))
    initial = [0., 0., 0.]
    if family == 'clean':
        c = config['families']['clean']
        initial = [float(rng.uniform(-c['initial_xy_proposal_m'], c['initial_xy_proposal_m']))
                   for _ in range(2)] + [float(rng.uniform(-c['initial_yaw_proposal_rad'], c['initial_yaw_proposal_rad']))]
    obstacles = []
    count = 0 if family == 'clean' else stage+1
    depth = float(rng.uniform(*config['families']['pothole']['depth_m']))
    kinds = ['cable' if family == 'short_obstacle' else 'pothole'] * count
    if family == 'mixed':
        count = max(2, count)
        kinds = ['cable', 'pothole'] + ['cable']*(count-2)
        rng.shuffle(kinds)
    for index, kind in enumerate(kinds):
        x = float(np.linspace(.95, 3., count)[index] + rng.uniform(-.04, .04))
        if kind == 'cable':
            c = config['families']['short_obstacle']
            radius, angle = float(rng.uniform(*c['radius_m'])), float(rng.uniform(*c['angle_rad']))
            half_length = .55
            support = half_length*abs(math.sin(angle))+radius
            obstacle = dict(kind=kind, x=x, y=0., radius_m=radius, angle_rad=angle,
                            half_length_m=half_length, depth_m=None)
        else:
            c = config['families']['pothole']
            radius = float(rng.uniform(*c['radius_m']))
            support = radius
            obstacle = dict(kind=kind, x=x, y=float(rng.uniform(*c['lateral_m'])),
                            radius_m=radius, angle_rad=0., half_length_m=0., depth_m=depth)
        obstacles.append(dict(obstacle, id=f'item_{index}', near_m=x-support, far_m=x+support))
    payload = dict(contract_id=CONTRACT_ID, family=family, seed=seed, stage=stage, split=split,
                   initial_pose_xy_yaw=initial, obstacles=obstacles, floor_mu=1.,
                   physics_qualified=False, metadata_actor_input=False,
                   initial_pose_application='requested_spawn_then_independent_settled_start_gate')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return dict(payload, id=f'{family}_{split}_{seed}_s{stage}_{digest[:12]}')


def write_world(source, target, layout, cache):
    tree = ET.parse(source)
    world = tree.getroot().find('world')
    holes = [r for r in layout['obstacles'] if r['kind'] == 'pothole']
    meshes = []
    if holes:
        for floor in world.findall("model[@name='controlled_box_floor']"):
            world.remove(floor)
        config = dict(floor_bounds_xy_m=[-2., 8., -3.5, 3.5], mesh_spacing_m=.005,
                      flat_mesh_spacing_m=.08, floor_representation='continuous_mesh',
                      pothole_depth_m=holes[0]['depth_m'])
        sdf, meshes = floor_model([('pothole', r['x'], r['y'], r['radius_m']) for r in holes], config, cache)
        world.append(ET.fromstring(sdf).find('model'))
    cables = [r for r in layout['obstacles'] if r['kind'] == 'cable']
    if cables:
        model = ET.SubElement(world, 'model', name='recovery_rigid_obstacles')
        ET.SubElement(model, 'static').text = 'true'
        link = ET.SubElement(model, 'link', name='cables')
        for r in cables:
            for tag in ('collision', 'visual'):
                node = ET.SubElement(link, tag, name=r['id']+'_'+tag)
                ET.SubElement(node, 'pose').text = f"{r['x']} 0 {r['radius_m']} {math.pi/2} 0 {r['angle_rad']}"
                cylinder = ET.SubElement(ET.SubElement(node, 'geometry'), 'cylinder')
                ET.SubElement(cylinder, 'radius').text = str(r['radius_m'])
                ET.SubElement(cylinder, 'length').text = str(2*r['half_length_m'])
    tree.write(target, encoding='utf-8', xml_declaration=True)
    return meshes


def prepare(out, config_path=CONFIG):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    config = configuration(config_path)
    import xacro
    from .unknown_step_geometry import collision_envelope
    inherited_dir = out/'inherited_inputs'
    inherited_dir.mkdir()
    worlds = prepare_worlds(inherited_dir)
    urdf = inherited_dir/'reference_robot.urdf'
    urdf.write_text(xacro.process_file(str(repo()/'src/nino_description/urdf/nino.urdf.xacro'),
        mappings=dict(contact_lab='true', terrain_preview='false', caster_wheel_damping='0.001')).toprettyxml(indent='  '))
    envelope = collision_envelope(urdf, repo()/'src/nino_description')
    base_task = asdict(unknown_step_plan.task_settings(envelope, dict(bump_x_m=None)))
    source = worlds['clear_box']
    bank = []
    for split, seed in (('development', 1511), ('validation', 2511), ('test', 3511)):
        for family in FAMILIES:
            for stage in range(config['curriculum']['maximum_stage']+1):
                layout = sample_layout(config, family, seed+stage, stage, split)
                target = out/(layout['id']+'.sdf')
                meshes = write_world(source, target, layout, out/'meshes')
                task = deepcopy(base_task)
                task.update(route_m=config['route_m'], obstacle_near_m=None, obstacle_far_m=None,
                            maximum_cross_track_m=config['maximum_cross_track_m'],
                            maximum_seconds=config['horizon_s'], continuous_stop_s=config['continuous_stop_s'])
                bank.append(dict(layout, world=str(target),
                                 world_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                 meshes={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in meshes},
                                 task_settings=task))
    result = dict(config=config, config_sha256=hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
                  envelope=envelope, layouts=bank, physics_qualified=False,
                  hardware_authorized=False)
    save(out/'bank.json', result)
    return result
