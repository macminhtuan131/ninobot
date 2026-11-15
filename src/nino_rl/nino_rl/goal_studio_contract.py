"""Studio contract for goal100/1D; long jobs require an explicit GUI/CLI request."""
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil

from .common_studio_v2_contract import profiles as inherited_profiles
from .td3_studio_contract import digest

ENGINE = 'unknown_goal100_v1'
CHECKPOINT_KIND = 'nino_unknown_goal_checkpoint_v1'
SMOKE_PROFILE = 'nino_td3_smoke_h5_v1'
SCENARIOS = {'unknown_step_dev_bank_v1': 'Gờ không biết · goal 2m · dev clear / 0,65 / 1,05m'}
QUALIFICATION_ROOT = Path.home()/'nino_research/unknown_step_short_20261110_v1'


def profiles():
    p = inherited_profiles()
    return {k:deepcopy(p[k]) for k in (SMOKE_PROFILE, 'nino_td3_research_h5_v1')}


def validate_request(raw):
    r = dict(raw)
    expected = {'schema_version','mode','scenario','profile','timesteps','seed','checkpoint_every',
                'wall_minutes','evaluate','resume'}
    if set(r) != expected or r['schema_version'] != 1 or r['mode'] not in ('smoke','train'):
        raise ValueError('Versioned goal-task request required')
    if r['scenario'] not in SCENARIOS or r['profile'] not in profiles():
        raise ValueError('Goal task requires its own dev bank and h5 profile')
    for k,lo,hi in [('timesteps',1,20000),('seed',0,2_147_483_647),
                    ('checkpoint_every',0,20000),('wall_minutes',1,1440)]:
        if type(r[k]) is not int or not lo <= r[k] <= hi:
            raise ValueError('Invalid goal request field: '+k)
    if type(r['evaluate']) is not bool or r['resume'] is not None and not isinstance(r['resume'],str):
        raise ValueError('Explicit evaluation flag and optional checkpoint path required')
    if r['mode']=='smoke' and (r['timesteps']!=384 or r['profile']!=SMOKE_PROFILE or r['resume'] is not None):
        raise ValueError('Goal smoke is 384 fresh steps with the smoke profile')
    if (r['mode']=='train' and r['resume'] is None
            and r['timesteps']<=profiles()[r['profile']]['algorithm']['learning_starts']):
        raise ValueError('Fresh training must exceed warmup; smoke checks software separately')
    return r


def require_qualification():
    from .unknown_step_runner import sources, require_inputs
    root = QUALIFICATION_ROOT
    ledger = json.loads((root/'ledger.json').read_text())
    for name in ('smoke','evaluate'):
        stage = ledger['stages'][name]
        if stage['status']!='completed':
            raise ValueError('Goal task short '+name+' has not qualified')
        m = json.loads((Path(stage['path'])/'stage_manifest.json').read_text())
        if m['source_pins']!=sources():
            raise ValueError('Goal task Gazebo-qualified sources changed')
    bank = require_inputs(root)
    if len(bank['layouts'])!=5:
        raise ValueError('Frozen goal-task bank changed')
    return root


def budget(r):
    launches = math.ceil(r['timesteps']/100)+1
    evaluations = 6 if r['evaluate'] else 0
    saves = 1+(r['timesteps']-1)//r['checkpoint_every'] if r['checkpoint_every'] else 1
    replay = profiles()[r['profile']]['algorithm']['buffer_size']*204*4
    estimate = (launches+evaluations)*40*1024**2+r['timesteps']*64*1024+saves*(replay+8*1024**2)
    return dict(training_launches_max=launches, evaluation_launches=evaluations,
                estimated_output_bytes=estimate, required_free_bytes=estimate+1024**3,
                reserve_bytes=1024**3, estimate_is_upper_bound=False, hardware_actions=0)


def require_disk(root, r):
    p=Path(root).expanduser().resolve()
    while not p.exists():p=p.parent
    b=budget(r);free=shutil.disk_usage(p).free
    if free<b['required_free_bytes']:
        raise ValueError(f"Goal job disk estimate needs {b['required_free_bytes']/1024**3:.2f}GiB, has {free/1024**3:.2f}GiB")
    return dict(b,free_bytes=free)


def identity(r):
    from .unknown_step_runner import sources
    root=require_qualification()
    return dict(engine=ENGINE, profile=r['profile'], seed=r['seed'],
                scenario=r['scenario'], effective_profile=profiles()[r['profile']],
                bank_sha256=digest(root/'inputs/bank.json'), controller_sources=sources(),
                training_sources={p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('goal_training_studio.py')]},
                observation_size=100, action_size=1, planned_stop_features=False,
                hardware_authorized=False)


def inspect_checkpoint(path, verify_files=True, check_runtime=True):
    p=Path(path).expanduser().resolve();p=p.parent if p.is_file() else p
    m=json.loads((p/'manifest.json').read_text());c=json.loads((p/'checkpoint.json').read_text())
    ident=json.loads((p/'identity.json').read_text())
    if m.get('kind')!=CHECKPOINT_KIND or m.get('status')!='resumable':
        raise ValueError('Not a goal100 resumable checkpoint')
    if check_runtime:
        from .residual_workflow import runtime_versions
        if m.get('runtime')!=runtime_versions():raise ValueError('Goal checkpoint runtime differs')
    if verify_files and any(digest(p/n)!=h for n,h in m['files'].items()):
        raise ValueError('Goal checkpoint hash mismatch')
    return dict(path=str(p),engine=ENGINE,profile=ident['profile'],seed=ident['seed'],
                scenario=ident['scenario'],global_steps=c['global_steps'],
                optimizer_updates=c['optimizer_updates'],replay_size=c['replay_size'],identity=ident)
