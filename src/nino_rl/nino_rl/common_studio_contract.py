"""Budgeted Studio child of frozen common103D/1D; no legacy checkpoint conversion."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil
from . import equal_information_contract as controller
from . import td3_studio_contract as legacy

ENGINE = 'common103_v1'
CHECKPOINT_KIND = 'nino_common_studio_checkpoint_v1'
SCENARIOS = {'clear_box': 'Sàn sạch · common103D/1D · source stop luân phiên 6/8 s'}
SMOKE_PROFILE = legacy.SMOKE_PROFILE
MAX_STEPS = 20000


def profiles():
    values = deepcopy(legacy.profiles())
    # Separate effective profile identity; never edit the frozen catalog.
    for profile in values.values():
        profile['algorithm']['buffer_size'] = min(profile['algorithm']['buffer_size'], 32768)
    return values


def validate_request(value):
    request = legacy.validate_request(value)
    if request['scenario'] not in SCENARIOS:
        raise ValueError('common103 pilot supports clear_box only; no obstacle release')
    if request['timesteps'] > MAX_STEPS:
        raise ValueError('common103 v1 is bounded to 20,000 additional transitions per job')
    if request['mode'] == 'train' and request['resume'] is None:
        warmup = profiles()[request['profile']]['algorithm']['learning_starts']
        if request['timesteps'] <= warmup:
            raise ValueError('Fresh training must exceed warmup; use smoke for integration')
    return request


def budget(request):
    """SB3 can auto-reset after an exact terminal even at the final budget step."""
    launches = math.ceil(request['timesteps'] / 140) + 1
    evaluations = 6 if request['evaluate'] else 0
    checkpoints = 1 + ((request['timesteps'] - 1) // request['checkpoint_every'] if request['checkpoint_every'] else 0)
    capacity = profiles()[request['profile']]['algorithm']['buffer_size']
    replay_bytes = capacity * (103 * 2 + 1 + 3) * 4
    # Observed historical raw episodes ~31 MiB; provision 40 MiB, plus 1 GiB reserve.
    estimate = (launches + evaluations) * 40 * 1024**2 + checkpoints * (replay_bytes + 8*1024**2)
    return dict(training_transitions=request['timesteps'], training_launches_max=launches,
        evaluation_launches=evaluations, evaluation_transitions=140*evaluations,
        optimizer_updates_max=request['timesteps'], hardware_actions=0, retries=0,
        estimated_output_bytes=estimate, required_free_bytes=estimate + 1024**3,
        disk_estimate_is_bound=False, reserve_bytes=1024**3,
        stop_schedule_s=[6., 8.], steps_per_episode=140)


def require_disk(root, request):
    path = Path(root).expanduser().resolve()
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    plan = budget(request)
    if free < plan['required_free_bytes']:
        raise ValueError(f"Disk budget: need about {plan['required_free_bytes']/1024**3:.2f} GiB free, "
                         f"have {free/1024**3:.2f} GiB. Choose another output disk; no automatic deletion.")
    return dict(plan, free_bytes_at_start=free)


def identity(request):
    profile = profiles()[request['profile']]
    return dict(engine=ENGINE, controller=controller.identity(), scenario=request['scenario'],
        profile=request['profile'], effective_profile=profile,
        effective_profile_sha256=hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
        seed=request['seed'], baseline='frozen wheel PI Ki=0.10; drive-ready fresh episode',
        training_stop_schedule_s=[6., 8.], normalization='inherited fixed physical scales',
        replay_action='requested scalar before shared window/projection', hardware_authorized=False)


def inspect_checkpoint(path, check_runtime=False, verify_files=True):
    from .residual_workflow import runtime_versions
    p = Path(path).expanduser().resolve()
    if p.is_file():
        if p.name != 'model.zip':
            raise ValueError('Select model.zip or complete checkpoint directory')
        p = p.parent
    manifest = json.loads((p/'manifest.json').read_text())
    if manifest.get('kind') != CHECKPOINT_KIND or manifest.get('status') != 'resumable':
        raise ValueError('Need common103 Studio bundle; legacy100D/2D and closed A/C are not resumable here')
    required = {'model.zip', 'replay_buffer.pkl', 'checkpoint.json', 'resume_identity.json'}
    if not required.issubset(manifest.get('files', {})):
        raise ValueError('Incomplete checkpoint bundle')
    for name, sha in manifest['files'].items():
        file = (p/name).resolve()
        if not file.is_relative_to(p) or not file.is_file() or verify_files and legacy.digest(file) != sha:
            raise ValueError('Checkpoint hash mismatch: '+name)
    meta = json.loads((p/'checkpoint.json').read_text())
    ident = json.loads((p/'resume_identity.json').read_text())
    if meta['identity'] != ident or ident.get('engine') != ENGINE:
        raise ValueError('Checkpoint identity mismatch')
    if check_runtime and manifest.get('runtime') != runtime_versions():
        raise ValueError('Checkpoint/runtime versions differ')
    return dict(path=str(p), kind=ENGINE, scenario=ident['scenario'], profile=ident['profile'],
        seed=ident['seed'], global_steps=meta['global_steps'], optimizer_updates=meta['optimizer_updates'],
        replay_size=meta['replay_size'], identity=ident, files_verified=verify_files)


def require_resume(request):
    if not request['resume']:
        return None
    info = inspect_checkpoint(request['resume'], check_runtime=True)
    if info['identity'] != identity(request):
        raise ValueError('Resume requires same common controller, effective profile, seed and source schedule')
    from .common_training_studio import sources
    meta = json.loads((Path(info['path'])/'checkpoint.json').read_text())
    if meta.get('engine_sources') != sources():
        raise ValueError('Resume engine sources changed; new protocol or original engine required')
    return info
