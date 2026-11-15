from copy import deepcopy
import json
import pytest
from nino_rl import studio_resume_migration as migration


def approved_fixture(tmp_path,monkeypatch):
    base='src/nino_rl/nino_rl/'
    parent=dict(controller='same_ABI',drive_ready='same_motor',files={
        base+'common_training_studio_v2.py':'old_engine',base+'common_studio_v2_contract.py':'old_contract',
        'unchanged.py':'same'})
    target=deepcopy(parent)
    target['files'][base+'common_training_studio_v2.py']='new_engine'
    target['files'][base+'common_studio_v2_contract.py']='new_contract'
    for name in ('studio_startup_repair.py','studio_deferred_reset.py','studio_resume_migration.py'):
        target['files'][base+name]='new_helper'
    a=tmp_path/'approval.json';a.write_text(json.dumps(dict(kind='studio_startup_reset_only_migration_v1',parent_sources=parent,target_sources=target)))
    monkeypatch.setattr(migration,'APPROVAL',a)
    return parent,target


def test_exact_approved_source_pair_only(tmp_path,monkeypatch):
    parent,current=approved_fixture(tmp_path,monkeypatch)
    assert migration.approved(parent,current)
    bad=deepcopy(current);bad['files']['unchanged.py']='different'
    with pytest.raises(ValueError):migration.approved(parent,bad)
    bad=deepcopy(current);bad['controller']='new_ABI'
    with pytest.raises(ValueError):migration.approved(parent,bad)


def test_unmigrated_checkpoint_stays_blocked(tmp_path,monkeypatch):
    parent,current=approved_fixture(tmp_path,monkeypatch)
    (tmp_path/'manifest.json').write_text(json.dumps(dict(files={})))
    with pytest.raises(ValueError,match='derived checkpoint'):migration.require_migration(tmp_path,dict(engine_sources=parent),current)


def test_receipt_cannot_bypass_different_runtime_or_approval(tmp_path,monkeypatch):
    parent,current=approved_fixture(tmp_path,monkeypatch)
    (tmp_path/'manifest.json').write_text(json.dumps(dict(files={'runtime_migration.json':'fixture'})))
    (tmp_path/'runtime_migration.json').write_text(json.dumps(dict(approval_sha256='wrong',source_engine=parent,resume_engine=current,controller_identity_preserved=True)))
    with pytest.raises(ValueError,match='receipt'):migration.require_migration(tmp_path,dict(engine_sources=parent),current)
