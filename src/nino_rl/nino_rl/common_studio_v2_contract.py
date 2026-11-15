"""Studio contract for isolated common103_v2 engine (100k replay, obstacle/DR, clean gate)."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil

from . import equal_information_v2 as controller
from . import td3_studio_contract as legacy

ENGINE = 'common103_v2'
CHECKPOINT_KIND = 'nino_common_studio_checkpoint_v2'
JOB_KIND = 'nino_common_studio_job_v2'
SCENARIOS = {key: spec['label'] for key, spec in controller.SCENARIO_SPECS.items()}
SMOKE_PROFILE = legacy.SMOKE_PROFILE
MAX_STEPS = 100_000
RESEARCH_BUFFER_SIZE = 100_000
DEFAULT_SEEDS = (11, 22, 33)


def profiles() -> dict:
    values = deepcopy(legacy.profiles())
    for name, profile in values.items():
        if name == SMOKE_PROFILE:
            profile['algorithm']['buffer_size'] = min(profile['algorithm']['buffer_size'], 2048)
        else:
            profile['algorithm']['buffer_size'] = RESEARCH_BUFFER_SIZE
    return values


def validate_request(value: dict) -> dict:
    raw = dict(value)
    raw.pop('scenario', None)
    scenario = value.get('scenario')
    if scenario not in SCENARIOS:
        raise ValueError(f'common103_v2 requires scenario in {sorted(SCENARIOS)}')
    # Validate shared scalar fields via legacy contract using clear_box placeholder,
    # then restore the v2 scenario (including box_c1_6mm_dr).
    checked = legacy.validate_request(dict(raw, scenario='clear_box'))
    checked['scenario'] = scenario
    if checked['timesteps'] > MAX_STEPS:
        raise ValueError(f'common103_v2 is bounded to {MAX_STEPS:,} additional transitions per job')
    if checked['mode'] == 'train' and checked['resume'] is None:
        warmup = profiles()[checked['profile']]['algorithm']['learning_starts']
        if checked['timesteps'] <= warmup:
            raise ValueError('Fresh training must exceed warmup; use smoke for pipeline check')
    return checked


def budget(request: dict) -> dict:
    launches = math.ceil(request['timesteps'] / 140) + 1
    evaluations = 6 if request['evaluate'] else 0
    checkpoints = 1 + (
        (request['timesteps'] - 1) // request['checkpoint_every'] if request['checkpoint_every'] else 0
    )
    capacity = profiles()[request['profile']]['algorithm']['buffer_size']
    replay_bytes = capacity * (103 * 2 + 1 + 3) * 4
    # Estimates, not upper bounds: include retained JSONL traces as well as raw.
    raw_bytes = launches * 40 * 1024 ** 2
    retained_bytes = (evaluations * 40 * 1024 ** 2
                      + checkpoints * (replay_bytes + 8 * 1024 ** 2)
                      + request['timesteps'] * 64 * 1024)
    estimate = raw_bytes + retained_bytes
    return dict(
        training_transitions=request['timesteps'],
        training_launches_max=launches,
        evaluation_launches=evaluations,
        evaluation_transitions=140 * evaluations,
        optimizer_updates_max=request['timesteps'],
        hardware_actions=0,
        retries=0,
        estimated_output_bytes=estimate,
        estimated_training_raw_bytes=raw_bytes,
        estimated_retained_bytes=retained_bytes,
        required_free_bytes=estimate + 1024 ** 3,
        disk_estimate_is_bound=False,
        reserve_bytes=1024 ** 3,
        stop_schedule_s=[6.0, 8.0],
        steps_per_episode=140,
    )


def require_disk(root: Path, request: dict) -> dict:
    path = Path(root).expanduser().resolve()
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    plan = budget(request)
    if free < plan['required_free_bytes']:
        raise ValueError(
            f"Disk budget: need about {plan['required_free_bytes'] / 1024 ** 3:.2f} GiB free, "
            f"have {free / 1024 ** 3:.2f} GiB. Post-job cleanup does not reduce peak disk within a job."
        )
    return dict(plan, free_bytes_at_start=free)


def campaign_budget(request: dict, seeds, *, auto_prune_raw: bool = False) -> dict:
    if type(auto_prune_raw) is not bool:
        raise ValueError('auto_prune_raw must be boolean')
    if (not isinstance(seeds, (list, tuple)) or len(seeds) < 3
            or any(type(seed) is not int or not 0 <= seed <= 2_147_483_647 for seed in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError('Campaign requires at least 3 distinct non-negative integer seeds')
    single = budget(dict(request, evaluate=True))
    n = len(seeds)
    retained = n * single['estimated_retained_bytes']
    raw = single['estimated_training_raw_bytes'] * (1 if auto_prune_raw else n)
    return dict(seed_count=n, seeds=list(seeds),
                training_transitions=n * request['timesteps'],
                training_launches_max=n * single['training_launches_max'],
                evaluation_launches=n * single['evaluation_launches'],
                wall_minutes_max=n * request['wall_minutes'],
                estimated_peak_bytes=retained + raw,
                required_free_bytes=retained + raw + single['reserve_bytes'],
                reserve_bytes=single['reserve_bytes'], disk_estimate_is_bound=False,
                auto_prune_raw=auto_prune_raw, hardware_actions=0)


def require_campaign_disk(root, request, seeds, *, auto_prune_raw=False):
    plan = campaign_budget(request, seeds, auto_prune_raw=auto_prune_raw)
    path = Path(root).expanduser().resolve()
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    if free < plan['required_free_bytes']:
        raise ValueError(f"Campaign disk budget: need about {plan['required_free_bytes']/1024**3:.2f} GiB; "
                         f"have {free/1024**3:.2f} GiB. Cleanup runs after each seed, not during it.")
    return dict(plan, free_bytes_at_start=free)


def identity(request: dict) -> dict:
    profile = profiles()[request['profile']]
    return dict(
        engine=ENGINE,
        controller=controller.identity(scenario=request['scenario']),
        scenario=request['scenario'],
        profile=request['profile'],
        effective_profile=profile,
        effective_profile_sha256=hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
        seed=request['seed'],
        baseline='frozen wheel PI Ki=0.10; drive-ready fresh episode',
        training_stop_schedule_s=[6.0, 8.0],
        normalization='inherited fixed physical scales',
        replay_action='requested scalar before shared window/projection; closed-gate penalty=0',
        hardware_authorized=False,
    )


def inspect_checkpoint(path, check_runtime: bool = False, verify_files: bool = True) -> dict:
    from .residual_workflow import runtime_versions

    p = Path(path).expanduser().resolve()
    if p.is_file():
        if p.name != 'model.zip':
            raise ValueError('Select model.zip or complete checkpoint directory')
        p = p.parent
    manifest = json.loads((p / 'manifest.json').read_text())
    if manifest.get('kind') != CHECKPOINT_KIND or manifest.get('status') != 'resumable':
        raise ValueError('Need common103_v2 Studio checkpoint; v1 and legacy checkpoints cannot cross-resume')
    required = {'model.zip', 'replay_buffer.pkl', 'checkpoint.json', 'resume_identity.json'}
    if not required.issubset(manifest.get('files', {})):
        raise ValueError('Incomplete common103_v2 checkpoint bundle')
    for name, sha in manifest['files'].items():
        file = (p / name).resolve()
        if not file.is_relative_to(p) or not file.is_file() or (verify_files and legacy.digest(file) != sha):
            raise ValueError('Checkpoint hash mismatch: ' + name)
    meta = json.loads((p / 'checkpoint.json').read_text())
    ident = json.loads((p / 'resume_identity.json').read_text())
    if meta['identity'] != ident or ident.get('engine') != ENGINE:
        raise ValueError('Checkpoint identity mismatch')
    if check_runtime and manifest.get('runtime') != runtime_versions():
        raise ValueError('Checkpoint/runtime versions differ')
    return dict(
        path=str(p),
        kind=ENGINE,
        scenario=ident['scenario'],
        profile=ident['profile'],
        seed=ident['seed'],
        global_steps=meta['global_steps'],
        optimizer_updates=meta['optimizer_updates'],
        replay_size=meta['replay_size'],
        identity=ident,
        files_verified=verify_files,
    )


def require_resume(request: dict) -> dict | None:
    if not request['resume']:
        return None
    info = inspect_checkpoint(request['resume'], check_runtime=True)
    if info['identity'] != identity(request):
        raise ValueError('Resume requires identical common103_v2 scenario, profile, seed, and ABI')
    from .common_training_studio_v2 import sources

    meta = json.loads((Path(info['path']) / 'checkpoint.json').read_text())
    if meta.get('engine_sources') != sources():
        from .studio_resume_migration import require_migration
        require_migration(Path(info['path']),meta,sources())
    return info

