"""Mask semantics and finite orchestration, with no physics or optimizer."""
from pathlib import Path
import json
import numpy as np
import pytest
from nino_rl import residual_axis_ablation as ablation


def test_common_only_masks_differential_without_mutating_actor_output():
    original=np.array([.3,-.2],np.float32)
    raw,controlled=ablation.select_proposal('TD3_common_only',lambda obs:original,None)
    np.testing.assert_array_equal(original,[np.float32(.3),np.float32(-.2)])
    np.testing.assert_array_equal(raw,original)
    np.testing.assert_array_equal(controlled,[np.float32(.3),0.])
    controlled[0]=0.
    assert raw[0]==original[0]


def test_b0_never_calls_actor_and_full_keeps_both_channels():
    def forbidden(obs):raise AssertionError('B0 must not invoke policy')
    raw,controlled=ablation.select_proposal('B0',forbidden,None)
    assert raw is None and not any(controlled)
    raw,controlled=ablation.select_proposal('TD3_full',lambda obs:[-.1,.4],None)
    np.testing.assert_array_equal(raw,controlled)
    for invalid in ([np.nan,0.],[2.,0.],[0.]):
        with pytest.raises(ValueError):ablation.select_proposal('TD3_full',lambda obs:invalid,None)


def test_hard_failure_closes_screen_no_retry_or_complete_result(tmp_path,monkeypatch):
    monkeypatch.setattr(ablation,'checkpoint',lambda:tmp_path)
    monkeypatch.setattr(ablation.learner,'dependency_record',lambda path:{})
    monkeypatch.setattr(ablation,'PortableActor',lambda *args:None)
    monkeypatch.setattr(ablation,'prepare_worlds',lambda out:{'clear_box':'world'})
    calls=[]
    def rollout(*args):
        calls.append(1)
        return dict(physical_failure=True,guidance_faults=0,steps=20)
    monkeypatch.setattr(ablation,'rollout',rollout)
    with pytest.raises(RuntimeError,match='no retry'):ablation.evaluate(tmp_path)
    assert len(calls)==1 and (tmp_path/'evaluation_progress.json').exists()
    assert not (tmp_path/'evaluation_result.json').exists()


def test_fixed_budget_and_closed_root_cannot_reopen(tmp_path,monkeypatch):
    p=ablation.protocol()
    assert len(p['order'])==6 and p['maximum_transitions']==840
    assert p['training_transitions']==p['optimizer_updates']==p['hardware_actions']==0
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'isolated_home'))
    (tmp_path/'state.json').write_text(json.dumps({'runs':[]}))
    with pytest.raises(ValueError,match='already consumed'):ablation.run(tmp_path)


def test_different_checkpoint_cannot_be_substituted(tmp_path,monkeypatch):
    path=tmp_path/'other_checkpoint';path.mkdir()
    monkeypatch.setattr(ablation.learner,'validated_latest',lambda *args,**kwargs:path)
    with pytest.raises(ValueError,match='Frozen checkpoint manifest mismatch'):ablation.checkpoint()
