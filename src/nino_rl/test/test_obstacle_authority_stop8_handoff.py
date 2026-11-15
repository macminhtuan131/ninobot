"""A stop8 allocation cannot refill or change the prior three attempts."""
import fcntl
import json
from pathlib import Path
import pytest
from nino_rl import obstacle_authority_stop8_handoff as handoff
from nino_rl import obstacle_authority_draft as draft
from nino_rl.obstacle_authority_runner import read, sha


def write(path, value): path.write_text(json.dumps(value))


@pytest.fixture
def case(tmp_path, monkeypatch):
    root=tmp_path/'study'; root.mkdir(); attempts=[]
    for slot in draft.load()['proposed_attempts'][:3]:
        target=root/slot['id']; target.mkdir()
        write(target/'summary.json',dict(status='measurement_pass_pending_review',slot=slot,task_success=True,stop_completed=True))
        (target/'raw.jsonl').write_text('original\n')
        write(target/'manifest.json',dict(status='measurement_pass',files={p.name:sha(p) for p in target.iterdir()}))
        attempts.append(dict(slot=slot,status='measurement_pass',summary_sha256=sha(target/'summary.json'),
            reviewed_summary_sha256=sha(target/'summary.json'),wall_s=51.))
    old=tmp_path/'parent.json'; write(old,dict(allocated_attempts=3,identity={'same':'controller'},qualification_sha256='q'))
    state=dict(status='allocation_exhausted',allocated_attempts=3,release_sha256=sha(old),attempts=attempts,consumed_wall_s=153.)
    write(root/'ledger.json',state)
    new=tmp_path/'next.json'; write(new,dict(allocated_attempts=6,identity={'same':'controller'},qualification_sha256='q',
        continuation_kind=handoff.KIND,parent_release_sha256=sha(old),parent_ledger_sha256=sha(root/'ledger.json')))
    monkeypatch.setattr(handoff,'require_release',lambda p,*_:read(p))
    monkeypatch.setattr(handoff,'validate_software',lambda *_:None)
    monkeypatch.setattr(handoff,'validate_parent_and_contract',lambda *_:None)
    monkeypatch.setattr(handoff,'preflight',lambda *_:dict(fixture_only=True))
    return root,old,new,tmp_path/'receipt',state


def test_handoff_preserves_three_slots_and_allocates_only_stop8(case):
    root,old,new,out,before=case
    files={str(p):sha(p) for p in root.glob('E2-*/*')}
    receipt=handoff.transfer(root,old,new,out); after=read(root/'ledger.json')
    assert after['allocated_attempts']==6 and after['status']=='ready'
    assert after['attempts']==before['attempts'] and after['consumed_wall_s']==153.
    assert {p:sha(Path(p)) for p in files}==files
    assert receipt['consumed_attempts_preserved']==3 and receipt['next_slot']=='E2-04'
    assert receipt['new_physics_steps']==0 and not (root/'E2-04').exists()
    with pytest.raises(ValueError): handoff.transfer(root,old,new,out.parent/'again')


@pytest.mark.parametrize('fault',['raw1','raw2','raw3','unreviewed','failed','identity','skip','ledger_hash','existing_stop8','receipt_in_study'])
def test_mismatch_or_refill_rejected_without_changing_ledger(case,fault):
    root,old,new,out,before=case
    if fault in ('raw1','raw2','raw3'): (root/{'raw1':'E2-01','raw2':'E2-02','raw3':'E2-03'}[fault]/'raw.jsonl').write_text('changed')
    elif fault in ('unreviewed','failed'):
        state=read(root/'ledger.json')
        if fault=='unreviewed': state['attempts'][1].pop('reviewed_summary_sha256')
        else: state['status']='closed_failed'
        write(root/'ledger.json',state)
        release=read(new); release['parent_ledger_sha256']=sha(root/'ledger.json'); write(new,release)
    elif fault=='existing_stop8': (root/'E2-04').mkdir()
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
    assert state['attempts']==before['attempts'] and state['consumed_wall_s']==153.


def test_handoff_needs_exclusive_lock(case):
    root,old,new,out,before=case
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): handoff.transfer(root,old,new,out)
    assert read(root/'ledger.json')==before


@pytest.mark.parametrize('fault',['good','test_hash','failed_test','source_hash','parent_hash',
                                'parent_status','reader_source','reader_tests','contract_hash','wrong_order'])
def test_stop6_and_reader_evidence_gate(tmp_path,monkeypatch,fault):
    plan=draft.load();monkeypatch.setattr(draft,'ROOT',tmp_path);monkeypatch.setattr(draft,'load',lambda:plan)
    xml=tmp_path/'tests.xml';xml.write_text('<testsuites><testsuite tests="1" failures="0"><testcase classname="test_obstacle_authority_stop8_handoff"/></testsuite></testsuites>')
    source=tmp_path/'reader.py';source.write_text('fixture reader')
    tests=tmp_path/'reader_tests.xml';tests.write_text('<testsuites/>')
    correction=tmp_path/'correction.json'
    write(correction,dict(sources={source.name:sha(source)},reader_tests=str(tests),reader_tests_sha256=sha(tests),
        regression_tests=str(tests),regression_tests_sha256=sha(tests)))
    support=tmp_path/'queries.json';write(support,{})
    ambiguity=tmp_path/'ambiguity.json';write(ambiguity,{})
    parent=tmp_path/'parent_report.json'
    data=dict(status='first_cell_action_ranking_supported_no_benefit',analysis_id='nino_e2_ambiguity_query_review_v2',
        slots=['E2-01','E2-02','E2-03'],pairwise_comparable=True,useful_positive_authority_verified=True,
        benefit_verified=False,next_allocation=0,primary_metrics_unchanged=True,
        unsupported_authority_queries={'negative':0,'positive':0},contract=str(correction),contract_sha256=sha(correction),
        query_support=str(support),query_support_sha256=sha(support),ambiguities=str(ambiguity),ambiguities_sha256=sha(ambiguity))
    write(parent,data)
    contract=tmp_path/'stop8.json';comparison=dict(slots=plan['proposed_attempts'][3:6],control='E2-05',stop_s=8.,
        next_allocation=0,correction_contract_sha256=sha(correction));write(contract,comparison)
    release=dict(handoff_test_report=str(xml),handoff_test_report_sha256=sha(xml),handoff_source_sha256=sha(Path(handoff.__file__)),
        parent_cell_report=str(parent),parent_cell_report_sha256=sha(parent),comparison_contract=str(contract),comparison_contract_sha256=sha(contract))
    if fault=='test_hash':xml.write_text('changed')
    elif fault=='failed_test':
        xml.write_text(xml.read_text().replace('failures="0"','failures="1"'));release['handoff_test_report_sha256']=sha(xml)
    elif fault=='source_hash':release['handoff_source_sha256']='wrong'
    elif fault=='parent_hash':parent.write_text('{}')
    elif fault=='parent_status':
        data['status']='unknown';write(parent,data);release['parent_cell_report_sha256']=sha(parent)
    elif fault=='reader_source':source.write_text('changed')
    elif fault=='reader_tests':tests.write_text('changed')
    elif fault=='contract_hash':contract.write_text('{}')
    elif fault=='wrong_order':
        comparison['slots']=list(reversed(comparison['slots']));write(contract,comparison);release['comparison_contract_sha256']=sha(contract)
    def validate():handoff.validate_software(release);handoff.validate_parent_and_contract(release)
    if fault=='good':validate()
    else:
        with pytest.raises(ValueError):validate()


