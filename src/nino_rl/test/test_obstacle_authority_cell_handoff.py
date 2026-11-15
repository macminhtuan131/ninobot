"""A positive-arm allocation cannot refill or change the prior two attempts."""
import fcntl
import json
from pathlib import Path
import pytest
from nino_rl import obstacle_authority_cell_handoff as handoff
from nino_rl import obstacle_authority_draft as draft
from nino_rl.obstacle_authority_runner import read, sha


def write(path, value): path.write_text(json.dumps(value))


@pytest.fixture
def case(tmp_path, monkeypatch):
    root=tmp_path/'study'; root.mkdir(); attempts=[]
    for slot in draft.load()['proposed_attempts'][:2]:
        target=root/slot['id']; target.mkdir()
        write(target/'summary.json',dict(status='measurement_pass_pending_review',slot=slot,task_success=True,stop_completed=True))
        (target/'raw.jsonl').write_text('original\n')
        write(target/'manifest.json',dict(status='measurement_pass',files={p.name:sha(p) for p in target.iterdir()}))
        attempts.append(dict(slot=slot,status='measurement_pass',summary_sha256=sha(target/'summary.json'),
            reviewed_summary_sha256=sha(target/'summary.json'),wall_s=51.))
    old=tmp_path/'parent.json'; write(old,dict(allocated_attempts=2,identity={'same':'controller'},qualification_sha256='q'))
    state=dict(status='allocation_exhausted',allocated_attempts=2,release_sha256=sha(old),attempts=attempts,consumed_wall_s=102.)
    write(root/'ledger.json',state)
    new=tmp_path/'next.json'; write(new,dict(allocated_attempts=3,identity={'same':'controller'},qualification_sha256='q',
        continuation_kind=handoff.KIND,parent_release_sha256=sha(old),parent_ledger_sha256=sha(root/'ledger.json')))
    monkeypatch.setattr(handoff,'require_release',lambda p,*_:read(p))
    monkeypatch.setattr(handoff,'validate_software',lambda *_:None)
    monkeypatch.setattr(handoff,'validate_pair',lambda *_:None)
    monkeypatch.setattr(handoff,'preflight',lambda *_:dict(fixture_only=True))
    return root,old,new,tmp_path/'receipt',state


def test_handoff_preserves_two_slots_and_allocates_only_positive(case):
    root,old,new,out,before=case
    files={str(p):sha(p) for p in root.glob('E2-*/*')}
    receipt=handoff.transfer(root,old,new,out); after=read(root/'ledger.json')
    assert after['allocated_attempts']==3 and after['status']=='ready'
    assert after['attempts']==before['attempts'] and after['consumed_wall_s']==102.
    assert {p:sha(Path(p)) for p in files}==files
    assert receipt['consumed_attempts_preserved']==2 and receipt['next_slot']=='E2-03'
    assert receipt['new_physics_steps']==0 and not (root/'E2-03').exists()
    with pytest.raises(ValueError): handoff.transfer(root,old,new,out.parent/'again')


@pytest.mark.parametrize('fault',['raw1','raw2','unreviewed','failed','identity','skip','ledger_hash','existing_positive','receipt_in_study'])
def test_mismatch_or_refill_rejected_without_changing_ledger(case,fault):
    root,old,new,out,before=case
    if fault in ('raw1','raw2'): (root/('E2-01' if fault=='raw1' else 'E2-02')/'raw.jsonl').write_text('changed')
    elif fault in ('unreviewed','failed'):
        state=read(root/'ledger.json')
        if fault=='unreviewed': state['attempts'][1].pop('reviewed_summary_sha256')
        else: state['status']='closed_failed'
        write(root/'ledger.json',state)
        release=read(new); release['parent_ledger_sha256']=sha(root/'ledger.json'); write(new,release)
    elif fault=='existing_positive': (root/'E2-03').mkdir()
    elif fault=='receipt_in_study': out=root/'receipt'
    else:
        release=read(new)
        if fault=='identity': release['identity']={}
        elif fault=='skip': release['allocated_attempts']=4
        else: release['parent_ledger_sha256']='changed'
        write(new,release)
    digest=sha(root/'ledger.json')
    with pytest.raises(ValueError): handoff.transfer(root,old,new,out)
    assert sha(root/'ledger.json')==digest and not out.exists()


def test_crash_blocks_execution_and_keeps_consumption(case,monkeypatch):
    root,old,new,out,before=case; original=handoff.atomic_write; calls=[]
    def fail(path,data):
        calls.append(data['status'])
        if len(calls)==2: raise OSError('injected before ready')
        original(path,data)
    monkeypatch.setattr(handoff,'atomic_write',fail)
    with pytest.raises(OSError): handoff.transfer(root,old,new,out)
    state=read(root/'ledger.json')
    assert state['status']=='handoff_pending_commit'
    assert state['attempts']==before['attempts'] and state['consumed_wall_s']==102.


def test_handoff_needs_exclusive_lock(case):
    root,old,new,out,before=case
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): handoff.transfer(root,old,new,out)
    assert read(root/'ledger.json')==before


@pytest.mark.parametrize('fault',['good','test_hash','test_failure','source_hash','pair_hash','pair_no_go','contract_hash','contract_wrong_sign'])
def test_evidence_gates(tmp_path,fault):
    xml=tmp_path/'tests.xml'; xml.write_text('<testsuites><testsuite tests="1" failures="0"><testcase classname="test_obstacle_authority_cell_handoff"/></testsuite></testsuites>')
    pair=tmp_path/'pair.json'; contract=tmp_path/'contract.json'
    result=dict(status='first_pair_eligible_for_next_declared_condition_not_benefit',slots=['E2-01','E2-02'],
                pair_comparable=True,useful_body_authority_verified=True,benefit_verified=False,next_allocation=0)
    write(pair,result); plan=dict(candidate='E2-03',control='E2-01',sign=1,next_allocation=0); write(contract,plan)
    release=dict(handoff_test_report=str(xml),handoff_test_report_sha256=sha(xml),handoff_source_sha256=sha(Path(handoff.__file__)),
                 parent_pair_report=str(pair),parent_pair_report_sha256=sha(pair),comparison_contract=str(contract),comparison_contract_sha256=sha(contract))
    if fault=='test_hash': xml.write_text('changed')
    elif fault=='test_failure':
        xml.write_text(xml.read_text().replace('failures="0"','failures="1"')); release['handoff_test_report_sha256']=sha(xml)
    elif fault=='source_hash': release['handoff_source_sha256']='wrong'
    elif fault=='pair_hash': pair.write_text('{}')
    elif fault=='pair_no_go':
        result['pair_comparable']=False; write(pair,result); release['parent_pair_report_sha256']=sha(pair)
    elif fault=='contract_hash': contract.write_text('{}')
    elif fault=='contract_wrong_sign':
        plan['sign']=-1; write(contract,plan); release['comparison_contract_sha256']=sha(contract)
    def validate(): handoff.validate_software(release); handoff.validate_pair(release)
    if fault=='good': validate()
    else:
        with pytest.raises(ValueError): validate()
