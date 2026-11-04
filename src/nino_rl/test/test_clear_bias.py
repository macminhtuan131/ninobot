"""Frozen-checkpoint lineage and finite bias interpretation; no Gazebo."""
from copy import deepcopy
import json
import pytest
from nino_rl import residual_clear_bias as bias


def test_budget_never_releases_training_or_changes_v2():
    p = bias.protocol()
    assert p['order']==['B0','TD3_h5','TD3_h5','B0']
    assert p['maximum_transitions']==560 and p['training_transitions']==0 and p['hardware_actions']==0
    assert p['checkpoint_task_fingerprint']==bias.v2.fingerprint()


def test_interpretation_requires_same_sign_in_both_runs():
    p = bias.protocol()
    baseline = [dict(mean_accepted_yaw_rad_s=0.)]*2
    two = lambda a,b: dict(B0=baseline,TD3_h5=[dict(mean_accepted_yaw_rad_s=a),dict(mean_accepted_yaw_rad_s=b)])
    result = bias.interpret(two(-.04,-.05),p)
    assert result['clear_floor_reference_bias_observed'] and not result['benefit_verified']
    assert not bias.interpret(two(-.04,.05),p)['clear_floor_reference_bias_observed']
    assert not bias.interpret(two(0.,0.),p)['clear_floor_reference_bias_observed']


def test_metrics_preserve_signed_reference_and_body_separately():
    rows=[]
    for i in range(140):
        rows.append(dict(task=dict(elapsed_s=(i+1)*.1),policy_proposal=[-.8,-.4],
            reference_trace=dict(body_reference=[.17,-.08]),final_ros_reference=[.17,-.07],
            body_yaw_rad_s=-.06,truth_pose_m_rad=[1.,-.1,-.2]))
    r=bias.bias_metrics(rows,dict(task_success=True),bias.protocol())
    assert r['mean_accepted_yaw_rad_s']==pytest.approx(-.08)
    assert r['mean_final_yaw_reference_rad_s']==pytest.approx(-.07)
    assert r['mean_gt_yaw_rate_rad_s']==pytest.approx(-.06) and r['bias_window_covered']
    incomplete=bias.bias_metrics(rows[:40],dict(task_success=False),bias.protocol())
    assert not incomplete['bias_window_covered']


def test_checkpoint_rejects_changed_manifest_or_current_latest(tmp_path,monkeypatch):
    path=tmp_path/'train';path.mkdir();(path/'manifest.json').write_text('{}')
    (path/'task_checkpoint.json').write_text(json.dumps(dict(task_fingerprint=bias.v2.fingerprint())))
    p=bias.protocol();p['checkpoint']=str(path)
    monkeypatch.setattr(bias.v2,'validated_latest',lambda *a,**k:path)
    with pytest.raises(ValueError,match='manifest changed'):bias.checkpoint(p)
    p['checkpoint_manifest_sha256']=bias.v2.dependency_record(path)['manifest_sha256']
    assert bias.checkpoint(p)==path
    monkeypatch.setattr(bias.v2,'validated_latest',lambda *a,**k:tmp_path/'another')
    with pytest.raises(ValueError,match='explicitly frozen'):bias.checkpoint(p)


def test_existing_ledger_cannot_consume_another_batch(tmp_path,monkeypatch):
    monkeypatch.setattr(bias.Path,'home',lambda:tmp_path)
    root=tmp_path/'batch';root.mkdir();(root/'state.json').write_text('{}')
    monkeypatch.setattr(bias,'evaluate',lambda *args:pytest.fail('No second simulation batch allowed'))
    with pytest.raises(ValueError,match='already recorded'):bias.run(root)
    assert list(root.iterdir())==[root/'.job.lock',root/'state.json'] or set(p.name for p in root.iterdir())=={'.job.lock','state.json'}
