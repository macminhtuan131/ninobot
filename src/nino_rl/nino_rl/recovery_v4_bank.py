"""Finite reproducible train/tune/heldout terrain bank. Geometry is not contact proof."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from . import recovery_bank as prior
from . import recovery_runner as runner
from .recovery_v4_environment import CONTRACT_ID
from .recovery_v4_runtime import CONFIG
from .recovery_v4_contract import load_config, identity
from .residual_workflow import save
from .recovery_training_contract import sha, read_json

FAMILIES = ('clean', 'short_obstacle')
SPLITS = dict(train=(151100, 8), tune=(251100, 2), heldout=(351100, 2))


def prepare(root):
    import xacro
    from .residual_factory_workflow import repo
    from .residual_sim_pilot import prepare_worlds
    from .unknown_step_geometry import collision_envelope
    from . import unknown_step_plan
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = root/'inputs'
    inputs.mkdir()
    config = prior.configuration()
    v4 = load_config(CONFIG)
    inherited = inputs/'inherited'
    inherited.mkdir()
    worlds = prepare_worlds(inherited)
    urdf = inherited/'reference_robot.urdf'
    urdf.write_text(xacro.process_file(str(repo()/'src/nino_description/urdf/nino.urdf.xacro'),
        mappings=dict(contact_lab='true', terrain_preview='false', caster_wheel_damping='0.001')).toprettyxml())
    envelope = collision_envelope(urdf, repo()/'src/nino_description')
    base = asdict(unknown_step_plan.task_settings(envelope, dict(bump_x_m=None)))
    rows = []
    for split, (start, count) in SPLITS.items():
        for family_index, family in enumerate(FAMILIES):
            for index in range(count):
                seed = start+family_index*1000+index
                layout = prior.sample_layout(config, family, seed, 0, 'development')
                layout.update(contract_id=CONTRACT_ID, split=split)
                rng = np.random.default_rng(seed)
                for obstacle in layout['obstacles']:
                    width = (obstacle['far_m']-obstacle['near_m'])/2
                    obstacle['x'] = float(rng.uniform(.8, 2.8))
                    obstacle.update(near_m=obstacle['x']-width, far_m=obstacle['x']+width)
                digest = hashlib.sha256(json.dumps(layout, sort_keys=True).encode()).hexdigest()
                layout['id'] = f'{family}_{split}_{seed}_{digest[:12]}'
                target = inputs/(layout['id']+'.sdf')
                meshes = prior.write_world(worlds['clear_box'], target, layout, inputs/'meshes',
                    scheduling=config['simulation_scheduling'])
                task = deepcopy(base)
                task.update(route_m=config['route_m'], obstacle_near_m=None, obstacle_far_m=None,
                    maximum_cross_track_m=config['maximum_cross_track_m'], maximum_seconds=config['horizon_s'],
                    continuous_stop_s=config['continuous_stop_s'])
                rows.append(dict(layout, world=str(target), world_sha256=sha(target),
                    meshes={str(p): sha(p) for p in meshes}, task_settings=task))
    result = dict(kind='nino_recovery_v4_bank', contract_id=CONTRACT_ID, config=config,
        envelope=envelope, layouts=rows, v4_config=asdict(v4), software_identity=identity(v4),
        source_pins=runner.sources(), hardware_authorized=False, physics_qualified=False,
        sampling='uniform_finite_train_bank_without_replacement_per_cycle', splits=SPLITS)
    save(inputs/'bank.json', result)
    return result


def require_bank(root):
    root = Path(root).resolve()
    bank = read_json(root/'inputs/bank.json')
    if (bank.get('kind') != 'nino_recovery_v4_bank' or bank.get('contract_id') != CONTRACT_ID
            or bank.get('source_pins') != runner.sources()
            or bank.get('software_identity') != identity(load_config(CONFIG))):
        raise ValueError('V4 prepared source/config identity changed; prepare a new immutable bank')
    seen = set()
    for row in bank['layouts']:
        if (row['split'] not in SPLITS or row['family'] not in FAMILIES or row['id'] in seen
                or row['world_sha256'] != sha(row['world'])
                or any(sha(path) != digest for path, digest in row['meshes'].items())):
            raise ValueError('V4 layout identity or split changed')
        seen.add(row['id'])
    expected = sum(n for _, n in SPLITS.values())*len(FAMILIES)
    if len(seen) != expected:
        raise ValueError('Incomplete v4 train/tune/heldout bank')
    return bank


def sample_layout(bank, family, split, seed, cursor):
    rows = sorted((r for r in bank['layouts'] if r['family'] == family and r['split'] == split), key=lambda r:r['id'])
    if not rows or cursor < 0:
        raise ValueError('Unknown split/family or negative schedule cursor')
    cycle, index = divmod(cursor, len(rows))
    order = np.random.default_rng(np.random.SeedSequence([seed, cycle])).permutation(len(rows))
    return rows[int(order[index])]
