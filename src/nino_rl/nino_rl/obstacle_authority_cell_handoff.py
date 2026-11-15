"""Extend only the reviewed first pair to its declared positive arm; no physics.

Kept separate from the frozen controller and earlier handoff provenance.
Never resets slots, changes consumed wall time, or launches a process.
"""
from copy import deepcopy
import fcntl
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from . import obstacle_authority_draft as draft
from .obstacle_authority_handoff import atomic_write, encoded
from .obstacle_authority_runner import read, sha, require_release, preflight
from .residual_workflow import save

KIND = 'e2_reviewed_first_pair_to_positive_v1'


def validate_software(release):
    report = Path(release['handoff_test_report'])
    if sha(report) != release['handoff_test_report_sha256'] or sha(Path(__file__)) != release['handoff_source_sha256']:
        raise ValueError('Positive handoff software evidence changed')
    suites = list(ET.parse(report).getroot().iter('testsuite'))
    if not suites or any(int(s.get(k, '0')) for s in suites for k in ('failures', 'errors', 'skipped')):
        raise ValueError('Positive handoff tests not passed')
    classes = {c.get('classname', '').split('.')[-1] for s in suites for c in s.iter('testcase')}
    if 'test_obstacle_authority_cell_handoff' not in classes:
        raise ValueError('Positive handoff test coverage missing')


def validate_pair(release):
    path = Path(release['parent_pair_report'])
    if sha(path) != release['parent_pair_report_sha256']:
        raise ValueError('Reviewed first-pair result changed')
    pair = read(path)
    if (pair.get('status') != 'first_pair_eligible_for_next_declared_condition_not_benefit'
            or pair.get('slots') != ['E2-01', 'E2-02'] or pair.get('pair_comparable') is not True
            or pair.get('useful_body_authority_verified') is not True
            or pair.get('benefit_verified') is not False or pair.get('next_allocation') != 0):
        raise ValueError('First pair did not qualify for the positive arm')
    contract = Path(release['comparison_contract'])
    if sha(contract) != release['comparison_contract_sha256']:
        raise ValueError('Positive comparison contract changed')
    plan = read(contract)
    if (plan.get('candidate') != 'E2-03' or plan.get('control') != 'E2-01'
            or plan.get('sign') != 1 or plan.get('next_allocation') != 0):
        raise ValueError('Contract must describe only the positive comparison, without a next allocation')


def transfer(root, parent_release_path, new_release_path, receipt_directory):
    root = Path(root).expanduser().resolve()
    old_path, new_path = Path(parent_release_path), Path(new_release_path)
    out = Path(receipt_directory).expanduser().resolve()
    if not (root / 'ledger.json').is_file():
        raise ValueError('Existing reviewed first-pair ledger required')
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old, new = require_release(old_path, root), require_release(new_path, root)
        validate_software(new); validate_pair(new)
        if (old['allocated_attempts'] != 2 or new['allocated_attempts'] != 3
                or old['identity'] != new['identity']
                or old['qualification_sha256'] != new['qualification_sha256']
                or new.get('continuation_kind') != KIND
                or new.get('parent_release_sha256') != sha(old_path)):
            raise ValueError('Only unchanged reviewed prefix2 to prefix3 is supported')
        state_path = root / 'ledger.json'; state = read(state_path)
        if new.get('parent_ledger_sha256') != sha(state_path):
            raise ValueError('Reviewed parent ledger changed')
        plan = draft.load(); attempts = state.get('attempts', [])
        if (state.get('status') != 'allocation_exhausted' or state.get('allocated_attempts') != 2
                or state.get('release_sha256') != sha(old_path) or len(attempts) != 2
                or [a.get('slot') for a in attempts] != plan['proposed_attempts'][:2]):
            raise ValueError('First-pair prefix is not a closed reviewed allocation')
        if out.is_relative_to(root) or root.is_relative_to(out) or (root / 'E2-03').exists():
            raise ValueError('Do not contain/edit study data or reuse a positive slot')
        preserved = {}
        for claim in attempts:
            slot = claim['slot']['id']; target = root / slot
            summary, manifest = read(target / 'summary.json'), read(target / 'manifest.json')
            expected = sha(target / 'summary.json')
            if (claim.get('status') != 'measurement_pass' or claim.get('summary_sha256') != expected
                    or claim.get('reviewed_summary_sha256') != expected
                    or summary.get('slot') != claim['slot']
                    or summary.get('status') != 'measurement_pass_pending_review'
                    or not summary.get('task_success') or not summary.get('stop_completed')
                    or manifest.get('status') != 'measurement_pass'):
                raise ValueError('Prior slot review/task/stop evidence invalid: ' + slot)
            for name, digest in manifest['files'].items():
                path = (target / name).resolve()
                if not path.is_relative_to(target.resolve()) or sha(path) != digest:
                    raise ValueError('Prior raw evidence changed: ' + slot)
            preserved[slot] = dict(summary_sha256=expected, manifest_sha256=sha(target / 'manifest.json'),
                                   original_files_verified=len(manifest['files']))
        readiness = preflight(root, plan)
        out.mkdir(parents=True, exist_ok=False)
        save(out / 'ledger_before.json', state)
        updated = deepcopy(state)
        updated.update(status='ready', release_sha256=sha(new_path), allocated_attempts=3)
        updated.setdefault('handoffs', []).append(dict(kind=KIND, parent_release_sha256=sha(old_path),
            parent_ledger_sha256=sha(state_path), new_release_sha256=sha(new_path),
            receipt=str(out / 'receipt.json'), next_slot='E2-03'))
        assert updated['attempts'] == attempts and updated['consumed_wall_s'] == state['consumed_wall_s']
        pending = deepcopy(updated); pending['status'] = 'handoff_pending_commit'
        receipt = dict(kind=KIND, status='committed_when_ledger_matches',
            ready_ledger_sha256=hashlib.sha256(encoded(updated)).hexdigest(),
            parent_ledger_sha256=sha(state_path), new_release_sha256=sha(new_path),
            consumed_attempts_preserved=2, additional_allocated_attempts=1, next_slot='E2-03',
            preserved_slots=preserved, controller_identity_unchanged=True, new_physics_steps=0,
            readiness=readiness)
        save(out / 'ledger_after.json', updated)
        atomic_write(state_path, pending)
        save(out / 'receipt.json', receipt)
        atomic_write(state_path, updated)
        if sha(state_path) != receipt['ready_ledger_sha256']:
            raise RuntimeError('Positive handoff incomplete; no execution allowed')
        return receipt
