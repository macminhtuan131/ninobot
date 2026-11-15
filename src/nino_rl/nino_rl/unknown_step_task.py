"""Unknown-step task specification and feature-boundary fixture, no runtime.

The path/goal can be known. Obstacle map, contact labels and simulator truth
must stay outside the deployable controller packet. No training is released.
"""
import hashlib
import json
import math
from pathlib import Path
from nino_control.residual_velocity import FEATURES

PROTOCOL_ID='nino_unknown_step_traversal_tracking_task_v1_2026_11_09'
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'src/nino_rl/config').is_dir())
PATH=ROOT/'src/nino_rl/config/unknown_step_traversal_tracking_task_v1.json'


def load(path=PATH):
    p=json.loads(Path(path).read_text())
    expected=dict(physics_allowed=False,allocated_attempts=0,training_allowed=False,
                  optimizer_updates=0,hardware_actions=0,runtime_implemented=False)
    if (p.get('protocol_id')!=PROTOCOL_ID or p.get('status')!='task_selected_runtime_not_implemented'
            or p.get('release')!=expected or p['objective'].get('user_selected') is not True
            or p['objective'].get('priority')!=['physical_traversal_and_arrival','path_tracking','completion_time']
            or p['controller_information'].get('obstacle_preview') is not False
            or p['controller_information'].get('privileged_contact_trigger') is not False
            or p['controller_information'].get('feature_names')!=list(FEATURES)
            or p['numeric_acceptance'].get('accepted') is not False):
        raise ValueError('Unknown-step task cannot enable preview/oracle or release execution')
    unsigned={k:v for k,v in p.items() if k!='spec_sha256'}
    if hashlib.sha256(json.dumps(unsigned,sort_keys=True,allow_nan=False).encode()).hexdigest()!=p['spec_sha256']:
        raise ValueError('Unknown-step task specification changed')
    for name,digest in p['frozen_inputs'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Unknown-step task input changed: '+name)
    return p


def controller_features(features):
    """Exact named boundary only, not proof of provenance or absence of shortcuts.

    Runtime still needs a source audit and metadata perturbation tests. This
    guard rejects accidental extra channels instead of silently dropping them.
    """
    if set(features)!=set(FEATURES):
        raise ValueError('Only the declared proprioception/command features are allowed')
    values=[]
    for key in FEATURES:
        value=features[key]
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError('Finite numeric controller feature required: '+key)
        values.append(float(value))
    return tuple(values)
