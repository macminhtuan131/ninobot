"""Explicit, audited neutral-to-first-candidate allocation transfer; no physics.

This coordinator is separate from the frozen controller identity. It may only
extend a reviewed one-slot neutral prefix to the next declared slot. It never
resets attempts, changes consumed time, edits a rollout, or launches a process.
"""
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from . import obstacle_authority_draft as draft
from .obstacle_authority_runner import read, sha, require_release, preflight
from .residual_workflow import save

KIND = "e2_reviewed_neutral_to_first_candidate_v1"


def encoded(data):
    return (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def atomic_write(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix=".e2_handoff_", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded(data)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def validate_tests(release):
    path = Path(release['handoff_test_report'])
    if sha(path) != release['handoff_test_report_sha256']:
        raise ValueError('Handoff test evidence changed')
    tree = ET.parse(path).getroot(); suites = list(tree.iter('testsuite'))
    if not suites or any(int(s.get(k, '0')) for s in suites for k in ('failures', 'errors', 'skipped')):
        raise ValueError('Handoff tests not passed')
    if not any(c.get('classname', '').endswith('test_obstacle_authority_handoff') for c in tree.iter('testcase')):
        raise ValueError('Handoff test coverage missing')
    if sha(Path(__file__)) != release['handoff_source_sha256']:
        raise ValueError('Handoff source changed')


def transfer(root, parent_release_path, new_release_path, receipt_directory):
    import hashlib
    root = Path(root).expanduser().resolve()
    parent_release_path, new_release_path = Path(parent_release_path), Path(new_release_path)
    receipt_directory = Path(receipt_directory).expanduser().resolve()
    if not root.is_dir() or not (root / 'ledger.json').is_file():
        raise ValueError('Existing reviewed E2 ledger required')
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_release = require_release(parent_release_path, root)
        new_release = require_release(new_release_path, root)
        validate_tests(new_release)
        if (old_release['allocated_attempts'] != 1 or new_release['allocated_attempts'] != 2
                or old_release['identity'] != new_release['identity']
                or old_release['qualification_sha256'] != new_release['qualification_sha256']
                or new_release.get('continuation_kind') != KIND
                or new_release.get('parent_release_sha256') != sha(parent_release_path)):
            raise ValueError('Only unchanged neutral1 to declared prefix2 continuation is supported')
        state_path = root / 'ledger.json'; state = read(state_path)
        if new_release.get('parent_ledger_sha256') != sha(state_path):
            raise ValueError('Reviewed parent ledger changed')
        plan = draft.load(); attempts = state.get('attempts', [])
        if (state.get('status') != 'allocation_exhausted' or state.get('allocated_attempts') != 1
                or state.get('release_sha256') != sha(parent_release_path) or len(attempts) != 1
                or attempts[0].get('slot') != plan['proposed_attempts'][0]
                or attempts[0].get('status') != 'measurement_pass'):
            raise ValueError('Neutral prefix is not a reviewed closed one-slot allocation')
        target = root / 'E2-01'
        if (target / 'summary.json').resolve().is_relative_to(receipt_directory):
            raise ValueError('Receipt cannot contain or replace the baseline')
        if receipt_directory.is_relative_to(target.resolve()) or (root / 'E2-02').exists():
            raise ValueError('Do not edit baseline or reuse an existing candidate slot')
        summary = read(target / 'summary.json'); manifest = read(target / 'manifest.json')
        expected = attempts[0].get('summary_sha256')
        if (expected != sha(target / 'summary.json') or attempts[0].get('reviewed_summary_sha256') != expected
                or summary.get('status') != 'measurement_pass_pending_review'
                or summary.get('slot') != plan['proposed_attempts'][0] or not summary.get('task_success')
                or not summary.get('stop_completed') or manifest.get('status') != 'measurement_pass'):
            raise ValueError('Neutral review/task/stop evidence invalid')
        for name, digest in manifest['files'].items():
            path = (target / name).resolve()
            if not path.is_relative_to(target.resolve()) or sha(path) != digest:
                raise ValueError('Neutral raw evidence changed')
        readiness = preflight(root, plan)
        receipt_directory.mkdir(parents=True, exist_ok=False)
        save(receipt_directory / 'ledger_before.json', state)
        updated = deepcopy(state)
        updated.update(status='ready', release_sha256=sha(new_release_path), allocated_attempts=2)
        updated.setdefault('handoffs', []).append(dict(kind=KIND, parent_release_sha256=sha(parent_release_path),
            parent_ledger_sha256=sha(state_path), new_release_sha256=sha(new_release_path),
            receipt=str(receipt_directory / 'receipt.json'), next_slot='E2-02'))
        assert updated['attempts'] == state['attempts'] and updated['consumed_wall_s'] == state['consumed_wall_s']
        pending = deepcopy(updated); pending['status'] = 'handoff_pending_commit'
        receipt = dict(kind=KIND, status='committed_when_ledger_matches',
            parent_ledger_sha256=sha(state_path), new_release_sha256=sha(new_release_path),
            ready_ledger_sha256=hashlib.sha256(encoded(updated)).hexdigest(),
            consumed_attempts_preserved=1, additional_allocated_attempts=1, next_slot='E2-02',
            neutral_manifest_sha256=sha(target / 'manifest.json'),
            neutral_summary_sha256=expected, verified_neutral_files=len(manifest['files']),
            controller_identity_unchanged=True, new_physics_steps=0, readiness=readiness)
        save(receipt_directory / 'ledger_after.json', updated)
        # A crash during the transfer leaves a blocked pending state, never a refill.
        atomic_write(state_path, pending)
        save(receipt_directory / 'receipt.json', receipt)
        atomic_write(state_path, updated)
        if sha(state_path) != receipt['ready_ledger_sha256']:
            raise RuntimeError('Handoff incomplete; no execution allowed')
        return receipt
