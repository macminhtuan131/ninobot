"""Neutral data/claims survive explicit continuation; no physics in these fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import fcntl
import pytest
from nino_rl import obstacle_authority_handoff as handoff
from nino_rl import obstacle_authority_draft as draft
from nino_rl.obstacle_authority_runner import sha, read


def write(path, value):path.write_text(json.dumps(value))


@pytest.fixture
def case(tmp_path, monkeypatch):
    root=tmp_path/'study';root.mkdir();target=root/'E2-01';target.mkdir()
    slot=draft.load()['proposed_attempts'][0]
    summary=dict(status='measurement_pass_pending_review',slot=slot,task_success=True,stop_completed=True)
    write(target/'summary.json',summary);(target/'raw.jsonl').write_text('retained raw\n')
    write(target/'manifest.json',dict(status='measurement_pass',files={p.name:sha(p) for p in target.iterdir()}))
    old=tmp_path/'parent.json';write(old,dict(allocated_attempts=1,identity={'same':'controller'},qualification_sha256='q'))
    claim=dict(slot=slot,status='measurement_pass',summary_sha256=sha(target/'summary.json'),
               reviewed_summary_sha256=sha(target/'summary.json'),wall_s=51.)
    state=dict(status='allocation_exhausted',allocated_attempts=1,release_sha256=sha(old),
               attempts=[claim],consumed_wall_s=51.)
    write(root/'ledger.json',state)
    new=tmp_path/'continuation.json';write(new,dict(allocated_attempts=2,identity={'same':'controller'},
        qualification_sha256='q',continuation_kind=handoff.KIND,parent_release_sha256=sha(old),
        parent_ledger_sha256=sha(root/'ledger.json')))
    monkeypatch.setattr(handoff,'require_release',lambda p,*_:read(p))
    monkeypatch.setattr(handoff,'validate_tests',lambda *_:None)
    monkeypatch.setattr(handoff,'preflight',lambda *_:dict(fixture_only=True))
    return root,old,new,tmp_path/'receipt',state


def test_transfer_only_adds_candidate_and_keeps_neutral_bytes_and_consumption(case):
    root,old,new,out,before=case
    original={p.name:sha(p) for p in (root/'E2-01').iterdir()}
    receipt=handoff.transfer(root,old,new,out);after=read(root/'ledger.json')
    assert after['status']=='ready' and after['allocated_attempts']==2
    assert after['attempts']==before['attempts'] and after['consumed_wall_s']==51.
    assert after['release_sha256']==sha(new)
    assert {p.name:sha(p) for p in (root/'E2-01').iterdir()}==original
    assert sha(root/'ledger.json')==receipt['ready_ledger_sha256']
    assert receipt['new_physics_steps']==0 and not (root/'E2-02').exists()
    with pytest.raises(ValueError,match='ledger changed'):handoff.transfer(root,old,new,out.parent/'repeat')


@pytest.mark.parametrize('mutation',['raw','review','status','skip','identity','prior_hash','existing_slot'])
def test_transfer_rejects_refill_mismatch_and_changed_evidence_without_mutating(case,mutation):
    root,old,new,out,before=case
    if mutation=='raw':(root/'E2-01/raw.jsonl').write_text('changed')
    elif mutation in ('review','status'):
        state=read(root/'ledger.json')
        if mutation=='review':state['attempts'][0]['reviewed_summary_sha256']='wrong'
        else:state['status']='closed_failed'
        write(root/'ledger.json',state)
        release=read(new);release['parent_ledger_sha256']=sha(root/'ledger.json');write(new,release)
    elif mutation=='existing_slot':(root/'E2-02').mkdir()
    else:
        release=read(new)
        if mutation=='skip':release['allocated_attempts']=12
        elif mutation=='identity':release['identity']={}
        else:release['parent_ledger_sha256']='wrong'
        write(new,release)
    digest=sha(root/'ledger.json')
    with pytest.raises(ValueError):handoff.transfer(root,old,new,out)
    assert sha(root/'ledger.json')==digest and not out.exists()


def test_crash_before_ready_commit_leaves_pending_and_never_launches(case,monkeypatch):
    root,old,new,out,before=case
    real=handoff.atomic_write;calls=[]
    def failed(path,data):
        calls.append(data['status'])
        if len(calls)==2:raise OSError('injected disk failure before ready')
        return real(path,data)
    monkeypatch.setattr(handoff,'atomic_write',failed)
    with pytest.raises(OSError):handoff.transfer(root,old,new,out)
    state=read(root/'ledger.json')
    assert state['status']=='handoff_pending_commit'
    assert state['attempts']==before['attempts'] and state['consumed_wall_s']==51.
    assert not (root/'E2-02').exists()


def test_transfer_requires_exclusive_idle_ledger(case):
    root,old,new,out,before=case
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):handoff.transfer(root,old,new,out)
    assert read(root/'ledger.json')==before and not out.exists()


@pytest.mark.parametrize('mutation',['good','xml_changed','failed_test','source_changed'])
def test_real_handoff_software_evidence_validation(tmp_path,mutation):
    xml=tmp_path/'tests.xml'
    xml.write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="test_obstacle_authority_handoff"/></testsuite></testsuites>')
    release=dict(handoff_test_report=str(xml),handoff_test_report_sha256=sha(xml),
                 handoff_source_sha256=sha(Path(handoff.__file__)))
    if mutation=='xml_changed':xml.write_text('changed')
    elif mutation=='failed_test':
        xml.write_text(xml.read_text().replace('failures="0"','failures="1"'))
        release['handoff_test_report_sha256']=sha(xml)
    elif mutation=='source_changed':release['handoff_source_sha256']='wrong'
    if mutation=='good':handoff.validate_tests(release)
    else:
        with pytest.raises(ValueError):handoff.validate_tests(release)
