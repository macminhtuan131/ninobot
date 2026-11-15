"""Explicit, exact-source migration for the startup/reset-only Studio repair.

Creates a derived checkpoint; never rewrites old model/replay or claims a new
task/checkpoint ABI. Not a generic bypass of source compatibility checks.
"""
import json
from pathlib import Path
import shutil
from .residual_workflow import save
from .td3_studio_contract import digest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'src/nino_rl/config').is_dir())
APPROVAL=ROOT/'src/nino_rl/config/studio_startup_reset_repair_2026_11_09.json'


def approved(parent,current):
    a=json.loads(APPROVAL.read_text())
    if (a.get('kind')!='studio_startup_reset_only_migration_v1'
            or parent!=a['parent_sources'] or current!=a['target_sources']
            or parent['controller']!=current['controller'] or parent['drive_ready']!=current['drive_ready']):
        raise ValueError('Checkpoint requires an exact approved startup/reset-only migration')
    base='src/nino_rl/nino_rl/'
    added={base+n for n in ('studio_startup_repair.py','studio_deferred_reset.py','studio_resume_migration.py')}
    changed={base+n for n in ('common_training_studio_v2.py','common_studio_v2_contract.py')}
    old,new=parent['files'],current['files']
    if (set(new)-set(old)!=added or set(old)-set(new)
            or {k for k in old if old[k]!=new[k]}!=changed):
        raise ValueError('Migration is restricted to the declared runtime-only file changes')
    return a


def require_migration(path,meta,current):
    approved(meta.get('engine_sources'),current)
    p=Path(path);manifest=json.loads((p/'manifest.json').read_text())
    if 'runtime_migration.json' not in manifest.get('files',{}):
        raise ValueError('Create a derived checkpoint migration before resuming under repaired sources')
    receipt=json.loads((p/'runtime_migration.json').read_text())
    if (receipt.get('approval_sha256')!=digest(APPROVAL)
            or receipt.get('source_engine')!=meta['engine_sources']
            or receipt.get('resume_engine')!=current
            or receipt.get('controller_identity_preserved') is not True):
        raise ValueError('Checkpoint runtime migration receipt does not match sources')


def migrate(source,destination):
    from . import common_studio_v2_contract as spec
    from .common_training_studio_v2 import sources
    info=spec.inspect_checkpoint(source,check_runtime=True,verify_files=True)
    source=Path(info['path']);target=Path(destination).expanduser().resolve()
    meta=json.loads((source/'checkpoint.json').read_text());current=sources()
    approved(meta['engine_sources'],current)
    if target.exists():raise ValueError('Never overwrite a checkpoint migration')
    manifest=json.loads((source/'manifest.json').read_text())
    target.mkdir(parents=True)
    for name in manifest['files']:shutil.copyfile(source/name,target/name)
    save(target/'runtime_migration.json',dict(kind='studio_startup_reset_only_migration_v1',
        source_checkpoint=str(source),source_manifest_sha256=digest(source/'manifest.json'),
        approval=str(APPROVAL),approval_sha256=digest(APPROVAL),
        source_engine=meta['engine_sources'],resume_engine=current,
        controller_identity_preserved=True,model_weights_optimizer_replay_unchanged=True,
        global_steps=info['global_steps'],no_training_performed=True,bit_exact_continuation=False))
    manifest['files']['runtime_migration.json']=digest(target/'runtime_migration.json')
    save(target/'manifest.json',manifest)
    assert spec.inspect_checkpoint(target,check_runtime=True)['global_steps']==info['global_steps']
    require_migration(target,meta,current)
    return target
