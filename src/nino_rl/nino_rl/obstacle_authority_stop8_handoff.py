"""Reviewed stop6 prefix3 to declared stop8 prefix6; transaction only, no physics."""
from copy import deepcopy
import fcntl
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
from . import obstacle_authority_draft as draft
from .obstacle_authority_handoff import atomic_write, encoded
from .obstacle_authority_runner import read, sha, require_release, preflight
from .residual_workflow import save

KIND='e2_reviewed_stop6_to_stop8_cell_v1'


def validate_software(release):
    path=Path(release['handoff_test_report'])
    if sha(path)!=release['handoff_test_report_sha256'] or sha(Path(__file__))!=release['handoff_source_sha256']:
        raise ValueError('Stop8 handoff software changed')
    suites=list(ET.parse(path).getroot().iter('testsuite'))
    if not suites or any(int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')):
        raise ValueError('Stop8 handoff tests not passed')
    classes={c.get('classname','').split('.')[-1] for s in suites for c in s.iter('testcase')}
    if 'test_obstacle_authority_stop8_handoff' not in classes:
        raise ValueError('Stop8 handoff test coverage missing')


def validate_parent_and_contract(release):
    path=Path(release['parent_cell_report'])
    if sha(path)!=release['parent_cell_report_sha256']:
        raise ValueError('Corrected stop6 result changed')
    data=read(path)
    if (data.get('status')!='first_cell_action_ranking_supported_no_benefit'
            or data.get('analysis_id')!='nino_e2_ambiguity_query_review_v2'
            or data.get('slots')!=['E2-01','E2-02','E2-03']
            or data.get('pairwise_comparable') is not True or data.get('useful_positive_authority_verified') is not True
            or data.get('benefit_verified') is not False or data.get('next_allocation')!=0
            or data.get('primary_metrics_unchanged') is not True
            or data.get('unsupported_authority_queries')!={'negative':0,'positive':0}):
        raise ValueError('Stop6 cell did not qualify for stop8')
    correction=Path(data['contract'])
    if sha(correction)!=data['contract_sha256']:
        raise ValueError('Reader correction contract changed')
    metadata=read(correction)
    for name,digest in metadata['sources'].items():
        source=(draft.ROOT/name).resolve()
        if not source.is_relative_to(draft.ROOT.resolve()) or sha(source)!=digest:
            raise ValueError('Frozen query-support reader changed')
    for key in ('reader_tests','regression_tests'):
        if sha(Path(metadata[key]))!=metadata[key+'_sha256']:
            raise ValueError('Reader correction test evidence changed')
    for key in ('query_support','ambiguities'):
        if sha(Path(data[key]))!=data[key+'_sha256']:
            raise ValueError('Stop6 query evidence changed')
    plan_path=Path(release['comparison_contract'])
    if sha(plan_path)!=release['comparison_contract_sha256']:
        raise ValueError('Stop8 comparison contract changed')
    plan=read(plan_path)
    if (plan.get('slots')!=draft.load()['proposed_attempts'][3:6]
            or plan.get('control')!='E2-05' or plan.get('stop_s')!=8.0
            or plan.get('next_allocation')!=0 or plan.get('correction_contract_sha256')!=data['contract_sha256']):
        raise ValueError('Only declared stop8 cell with frozen reader is supported')


def transfer(root,parent_release_path,new_release_path,receipt_directory):
    root=Path(root).expanduser().resolve();old_path=Path(parent_release_path);new_path=Path(new_release_path)
    out=Path(receipt_directory).expanduser().resolve()
    if not (root/'ledger.json').is_file():raise ValueError('Reviewed stop6 ledger required')
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old,new=require_release(old_path,root),require_release(new_path,root)
        validate_software(new);validate_parent_and_contract(new)
        if (old['allocated_attempts']!=3 or new['allocated_attempts']!=6
                or old['identity']!=new['identity'] or old['qualification_sha256']!=new['qualification_sha256']
                or new.get('continuation_kind')!=KIND or new.get('parent_release_sha256')!=sha(old_path)):
            raise ValueError('Only unchanged reviewed prefix3 to prefix6 is supported')
        state_path=root/'ledger.json';state=read(state_path)
        if new.get('parent_ledger_sha256')!=sha(state_path):raise ValueError('Reviewed parent ledger changed')
        attempts=state.get('attempts',[]);plan=draft.load()
        if (state.get('status')!='allocation_exhausted' or state.get('allocated_attempts')!=3
                or state.get('release_sha256')!=sha(old_path) or len(attempts)!=3
                or [a.get('slot') for a in attempts]!=plan['proposed_attempts'][:3]):
            raise ValueError('Stop6 prefix is not a closed reviewed allocation')
        if out.is_relative_to(root) or root.is_relative_to(out) or any((root/f'E2-0{i}').exists() for i in (4,5,6)):
            raise ValueError('Do not contain/edit study data or reuse a stop8 slot')
        preserved={}
        for claim in attempts:
            slot=claim['slot']['id'];target=root/slot
            summary,manifest=read(target/'summary.json'),read(target/'manifest.json');expected=sha(target/'summary.json')
            if (claim.get('status')!='measurement_pass' or claim.get('summary_sha256')!=expected
                    or claim.get('reviewed_summary_sha256')!=expected or summary.get('slot')!=claim['slot']
                    or summary.get('status')!='measurement_pass_pending_review'
                    or not summary.get('task_success') or not summary.get('stop_completed')
                    or manifest.get('status')!='measurement_pass'):
                raise ValueError('Prior slot review/task/stop evidence invalid: '+slot)
            for name,digest in manifest['files'].items():
                path=(target/name).resolve()
                if not path.is_relative_to(target.resolve()) or sha(path)!=digest:raise ValueError('Prior raw evidence changed: '+slot)
            preserved[slot]=dict(summary_sha256=expected,manifest_sha256=sha(target/'manifest.json'),original_files_verified=len(manifest['files']))
        readiness=preflight(root,plan);out.mkdir(parents=True,exist_ok=False);save(out/'ledger_before.json',state)
        updated=deepcopy(state);updated.update(status='ready',release_sha256=sha(new_path),allocated_attempts=6)
        updated.setdefault('handoffs',[]).append(dict(kind=KIND,parent_release_sha256=sha(old_path),
            parent_ledger_sha256=sha(state_path),new_release_sha256=sha(new_path),receipt=str(out/'receipt.json'),next_slot='E2-04'))
        assert updated['attempts']==attempts and updated['consumed_wall_s']==state['consumed_wall_s']
        pending=deepcopy(updated);pending['status']='handoff_pending_commit'
        receipt=dict(kind=KIND,status='committed_when_ledger_matches',
            ready_ledger_sha256=hashlib.sha256(encoded(updated)).hexdigest(),parent_ledger_sha256=sha(state_path),
            new_release_sha256=sha(new_path),consumed_attempts_preserved=3,additional_allocated_attempts=3,
            next_slot='E2-04',preserved_slots=preserved,controller_identity_unchanged=True,new_physics_steps=0,readiness=readiness)
        save(out/'ledger_after.json',updated);atomic_write(state_path,pending);save(out/'receipt.json',receipt);atomic_write(state_path,updated)
        if sha(state_path)!=receipt['ready_ledger_sha256']:raise RuntimeError('Stop8 handoff incomplete; no execution allowed')
        return receipt
