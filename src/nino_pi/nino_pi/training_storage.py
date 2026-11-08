"""Retention for sealed, completed common103 simulation jobs only.

Never edit the original manifest: it records the original acquisition. A separate
receipt explains intentional removal; the remaining job is NOT a full raw archive.
No imports of ROS, Gazebo or ML, and no changes to checkpoint/engine identities.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil

RECEIPT = 'storage_retention.json'
POLICY = 'completed_common103_training_raw_v1'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


@contextmanager
def simulation_lock():
    path = Path.home() / 'nino_research/.factory_sim.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Simulation worker is active; cleanup deferred') from exc
        yield


def safe_file(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe manifest path: ' + name)
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError('Symlink is not eligible for cleanup: ' + name)
    if not path.is_file():
        raise ValueError('Missing retained/input file: ' + name)
    return path


def verify(root, name, hashes):
    path = safe_file(root, name)
    if name not in hashes or digest(path) != hashes[name]:
        raise ValueError('Hash mismatch: ' + name)
    return path


def _plan(root, drop_checkpoint_steps):
    manifest_path = safe_file(root, 'manifest.json')
    manifest = read(manifest_path)
    if (manifest.get('kind') != 'nino_common_studio_job_v1'
            or manifest.get('status') != 'completed'
            or manifest.get('hardware_actions') != 0):
        raise ValueError('Only completed common103 simulation jobs are eligible')
    hashes = manifest['files']
    job = read(verify(root, 'job.json', hashes))
    if (job.get('status') != 'completed' or job.get('hardware_actions') != 0
            or job.get('request', {}).get('mode') not in ('train', 'smoke')):
        raise ValueError('Job is not a completed simulation training/smoke job')
    result = read(verify(root, 'training_result.json', hashes))
    for name in ('environment_trace.jsonl', 'training_trace.jsonl'):
        verify(root, name, hashes)
    # Verify every checkpoint bundle before removing anything. Files in each
    # bundle must also match the sealed job manifest, including the bundle manifest.
    checkpoints, drop = [], []
    for path in sorted((root / 'checkpoints').iterdir()):
        if path.name.startswith('.'):
            raise ValueError('Unfinished checkpoint present: ' + path.name)
        relative = str(path.relative_to(root))
        cp_manifest = read(verify(root, relative + '/manifest.json', hashes))
        required = {'model.zip', 'replay_buffer.pkl', 'checkpoint.json', 'resume_identity.json'}
        if (cp_manifest.get('kind') != 'nino_common_studio_checkpoint_v1'
                or cp_manifest.get('status') != 'resumable'
                or not required.issubset(cp_manifest.get('files', {}))):
            raise ValueError('Incomplete checkpoint: ' + relative)
        for name, sha in cp_manifest['files'].items():
            file = verify(root, relative + '/' + name, hashes)
            if digest(file) != sha:
                raise ValueError('Checkpoint manifest mismatch: ' + str(file))
        meta = read(path / 'checkpoint.json')
        if meta.get('global_steps') in drop_checkpoint_steps:
            if meta.get('reason') != 'periodic' or path == Path(result['checkpoint']).resolve():
                raise ValueError('Cannot prune a final/result checkpoint')
            drop.append(path)
        else:
            checkpoints.append(dict(path=str(path), global_steps=meta['global_steps']))
    if not checkpoints:
        raise ValueError('No retained checkpoint bundle')
    if {read(p / 'checkpoint.json')['global_steps'] for p in drop} != drop_checkpoint_steps:
        raise ValueError('Requested periodic checkpoint step not found')
    folders = sorted(p for p in (root / 'episodes').iterdir()
                     if re.fullmatch(r'episode_[0-9]+', p.name))
    folders += drop
    files = []
    for folder in folders:
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Unsafe episode/checkpoint folder: ' + str(folder))
        for path in sorted(folder.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlink in removal tree: ' + str(path))
            if path.is_file():
                name = str(path.relative_to(root))
                if name not in hashes:
                    raise ValueError('Unsealed file in removal tree: ' + name)
                stat = path.stat()
                files.append(dict(path=name, bytes=stat.st_size,
                                  original_manifest_sha256=hashes[name],
                                  stat=[stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]))
    return dict(schema_version=1, policy=POLICY, job=str(root),
                original_manifest_sha256=digest(manifest_path),
                original_hashes_scope='Recorded sealed manifest hashes, not a fresh hash of deleted raw files',
                retained_checkpoints=checkpoints, removed_files=files,
                removed_episode_count=len(folders) - len(drop),
                dropped_checkpoint_steps=sorted(drop_checkpoint_steps),
                planned_bytes=sum(f['bytes'] for f in files),
                preserved=['checkpoints not explicitly dropped', 'evaluation/', 'tensorboard/',
                           'environment_trace.jsonl', 'training_trace.jsonl',
                           'episode reset metadata', 'episodes/lifecycle.json', 'job/result/config/manifest'],
                limitation='Training episode raw measurements removed intentionally; full original job manifest no longer verifies. Retained traces support dashboard/offline summaries, not raw re-audit.'), folders


def prune_completed_job(directory, *, apply=False, drop_checkpoint_steps=()):
    """Dry-run by default. All checkpoints retained unless explicit periodic steps.

    Runs after a job, never during training. Failures/cancelled jobs and real bags
    are ineligible. Holds the same exclusive lock as the common simulation engine.
    """
    source = Path(directory).expanduser()
    if source.is_symlink():
        raise ValueError('Job symlink is not eligible')
    root = source.resolve(strict=True)
    if any(type(v) is not int or v <= 0 for v in drop_checkpoint_steps):
        raise ValueError('Checkpoint steps must be positive integers')
    with simulation_lock():
        receipt = root / RECEIPT
        if receipt.exists():
            previous = read(receipt)
            if (previous.get('policy') != POLICY or previous.get('status') != 'completed'
                    or previous.get('original_manifest_sha256') != digest(root / 'manifest.json')):
                raise ValueError('Existing retention receipt needs review; no further deletion')
            return dict(previous, already_pruned=True)
        plan, folders = _plan(root, set(drop_checkpoint_steps))
        if not apply:
            return dict(plan, status='preview')
        plan.update(status='pruning', started_utc=datetime.now(timezone.utc).isoformat(),
                    free_before_bytes=shutil.disk_usage(root).free, removed_file_count=0)
        save(receipt, plan)  # Record the complete inventory before the first unlink.
        removed_bytes = 0
        try:
            for item in plan['removed_files']:
                path = safe_file(root, item['path'])
                stat = path.stat()
                if [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns] != item['stat']:
                    raise ValueError('File changed during cleanup: ' + item['path'])
                path.unlink()
                plan['removed_file_count'] += 1
                removed_bytes += item['bytes']
            for folder in folders:
                for sub in sorted(folder.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                    if sub.is_dir():
                        sub.rmdir()
                folder.rmdir()
            plan['status'] = 'completed'
        except BaseException as exc:
            plan.update(status='interrupted', error=str(exc))
            raise
        finally:
            plan.update(removed_bytes=removed_bytes, free_after_bytes=shutil.disk_usage(root).free,
                        finished_utc=datetime.now(timezone.utc).isoformat())
            save(receipt, plan)
        return plan


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--drop-periodic-step', type=int, action='append', default=[])
    args = parser.parse_args()
    result = prune_completed_job(args.job, apply=args.apply, drop_checkpoint_steps=args.drop_periodic_step)
    print(json.dumps({k: v for k, v in result.items() if k != 'removed_files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
