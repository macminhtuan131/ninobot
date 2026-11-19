from copy import deepcopy
import json
from pathlib import Path

import pytest

from nino_rl import recovery_runner as runner
from nino_rl import recovery_training as training
from nino_rl.recovery_training_contract import (CHECKPOINT_KIND, RecoverySmokeRequest,
    inspect_recovery_checkpoint, require_live_qualification, sha, training_identity)
from nino_rl.residual_workflow import save
from test_recovery_training import make_env, qualified


FAMILIES = ('clean', 'short_obstacle', 'pothole', 'mixed', 'slope')


def request(tmp_path, **changes):
    raw = dict(schema_version=2, mode='all-families-live-smoke',
               prepared_root=str(tmp_path/'prepared'), families=list(FAMILIES))
    raw.update(changes)
    return RecoverySmokeRequest.parse(raw)


def fixture_identity(req):
    return dict(checkpoint_kind=CHECKPOINT_KIND, test_fixture=True,
        smoke_protocol=req.protocol.identity(), budget=req.protocol.budget(),
        families=list(req.families))


def rewrite_manifest(path):
    save(path/'manifest.json', {str(p.relative_to(path)): sha(p) for p in path.rglob('*')
                               if p.is_file() and p != path/'manifest.json'})


def test_schema_two_selects_named_finite_budget_and_preserves_schema_one_state(tmp_path):
    req = request(tmp_path)
    assert (req.transitions, req.maximum_launches, req.episode_transition_limit) == (640, 6, 128)
    assert req.profile == 'nino_td3_smoke_h5_v1'
    assert req.protocol.identity() == dict(schema_version=2, mode='all-families-live-smoke',
                                          name='nino_recovery_all_families_smoke_v1')
    assert RecoverySmokeRequest.parse(req.state()) == req
    legacy = RecoverySmokeRequest.parse(dict(prepared_root=str(tmp_path), families=['clean']))
    assert (legacy.schema_version, legacy.mode, legacy.transitions, legacy.maximum_launches) == (
        1, 'live-smoke', 384, 4)
    assert 'smoke_protocol' not in legacy.state()
    assert RecoverySmokeRequest.parse(legacy.state()) == legacy


@pytest.mark.parametrize('change', [dict(schema_version=3), dict(schema_version=True),
    dict(mode='live-smoke'), dict(mode='research'), dict(transitions=384),
    dict(transitions=641), dict(maximum_launches=4), dict(maximum_launches=7),
    dict(episode_transition_limit=129), dict(families=list(FAMILIES[:-1])),
    dict(families=list(FAMILIES)+['clean']), dict(profile='nino_td3_research_h5_v1')])
def test_schema_two_rejects_mixed_versions_open_budgets_and_partial_families(tmp_path, change):
    with pytest.raises(ValueError):
        request(tmp_path, **change)


def optimizer_fixture(tmp_path, monkeypatch, **faults):
    req = request(tmp_path)
    bank = qualified(tmp_path, FAMILIES)
    out = tmp_path/'learn'
    env, backend = make_env(out, req, bank, **faults)
    monkeypatch.setattr(training, 'RecoveryBankEnv', lambda *_: env)
    monkeypatch.setattr(runner, 'require_components', lambda root, family: None)
    return req, env, backend, out, fixture_identity(req)


def test_all_five_families_store_640_rows_and_checkpoint_keeps_named_identity(tmp_path, monkeypatch):
    req, env, backend, out, identity = optimizer_fixture(tmp_path, monkeypatch)
    result = training._learn(out, req, env.qualified, identity)
    assert result['status'] == 'completed' and result['stop_reason'] == 'transition_budget'
    assert result['global_transitions'] == result['replay_rows_verified'] == 640
    assert result['launch_attempts'] == result['administrative_censors'] == 5
    assert [row['family'] for row in env.assignments] == list(FAMILIES)
    assert result['family_transitions'] == dict.fromkeys(FAMILIES, 128)
    assert result['family_coverage_pass'] is True
    assert result['critic_updates'] > 0 and result['actor_updates'] > 0
    assert result['learned_benefit_verified'] is False
    inspected = inspect_recovery_checkpoint(result['checkpoint'], expected_identity=identity,
                                             require_resumable=True)
    assert inspected['checkpoint']['smoke_protocol'] == req.protocol.identity()
    assert inspected['state']['transitions'] == 640
    assert inspected['state']['launch_attempts'] == 5
    assert backend.events[-1] == ('close', 4)
    restored, _ = make_env(tmp_path/'spent', req, env.qualified)
    restored.restore(inspected['state'])
    with pytest.raises(ValueError, match='budget'):
        restored.reset()


def test_all_family_launch_exhaustion_stops_at_six_without_seventh_reset(tmp_path, monkeypatch):
    req, env, backend, out, identity = optimizer_fixture(tmp_path, monkeypatch, terminal_at=3)
    result = training._learn(out, req, env.qualified, identity)
    assert result['status'] == 'budget_exhausted'
    assert result['stop_reason'] == 'launch_budget_exhausted'
    assert result['global_transitions'] == result['replay_rows_verified'] == 18
    assert result['launch_attempts'] == result['physical_completed_episodes'] == 6
    assert result['family_coverage_pass'] is True
    assert result['family_transitions'] == dict(clean=6, short_obstacle=3, pothole=3, mixed=3, slope=3)
    assert len([event for event in backend.events if event[0] == 'launch']) == 6
    assert backend.events[-1] == ('close', 5)


@pytest.mark.parametrize('fault', ['mode', 'schema', 'name', 'metadata', 'budget', 'families',
                                  'remove_protocol', 'transitions', 'launches'])
def test_checkpoint_rejects_protocol_confusion_and_out_of_budget_counters(tmp_path, monkeypatch, fault):
    req, env, _, out, identity = optimizer_fixture(tmp_path, monkeypatch, terminal_at=1)
    result = training._learn(out, req, env.qualified, identity)
    path = Path(result['checkpoint'])
    value = deepcopy(identity)
    metadata = json.loads((path/'checkpoint.json').read_text())
    state = json.loads((path/'job_state.json').read_text())
    if fault == 'mode':
        value['smoke_protocol']['mode'] = 'live-smoke'
    elif fault == 'schema':
        value['smoke_protocol']['schema_version'] = 3
    elif fault == 'name':
        value['smoke_protocol']['name'] = 'unknown'
    elif fault == 'metadata':
        metadata['smoke_protocol']['mode'] = 'live-smoke'
    elif fault == 'budget':
        value['budget']['maximum_launches'] = 7
    elif fault == 'families':
        value['families'] = ['clean']
    elif fault == 'remove_protocol':
        value.pop('smoke_protocol')
        metadata.pop('smoke_protocol')
    else:
        state['transitions' if fault == 'transitions' else 'launch_attempts'] = (
            641 if fault == 'transitions' else 7)
    save(path/'identity.json', value)
    save(path/'checkpoint.json', metadata)
    save(path/'job_state.json', state)
    rewrite_manifest(path)
    with pytest.raises(ValueError):
        inspect_recovery_checkpoint(path)


def test_all_family_qualification_requires_five_current_baselines(tmp_path, monkeypatch):
    req = request(tmp_path)
    bank = qualified(tmp_path, FAMILIES)
    inputs = req.prepared_root/'inputs'
    inputs.mkdir(parents=True)
    save(inputs/'bank.json', bank.bank)
    save(inputs/'source_pins.json', dict(current=True))
    monkeypatch.setattr(runner, 'require_bank', lambda _: bank.bank)
    monkeypatch.setattr(runner, 'sources', lambda: dict(current=True))
    checked_components = []
    monkeypatch.setattr(runner, 'require_components',
                        lambda root, family: checked_components.append(family))
    for family in FAMILIES:
        root = req.prepared_root/f'baseline_{family}_s0'
        raw = root/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
        raw.parent.mkdir(parents=True)
        raw.write_text(''.join(json.dumps(dict(channel=channel, stamp_s=n*.01))+'\n'
            for n in range(11) for channel in ('imu', 'wheel', 'truth', 'drive')))
        layout = bank.layout(family, 0)
        save(root/'episode_0_reset.json', dict(reset=dict(physical_sample=dict(stamp_s=0.)),
                                             private_layout=layout))
        (root/'environment_trace.jsonl').write_text(json.dumps(dict(episode=0,
            physical_sample=dict(stamp_s=.1)))+'\n')
        qc = runner.raw_qc(root)
        save(root/'source_qc.json', qc)
        save(root/'job.json', dict(status='completed', action='baseline', family=family, stage=0,
                                  source_pins=dict(current=True)))
        save(root/'result.json', dict(family=family, stage=0, classical_baseline_only=True,
            optimizer_updates=0, physical_gate_pass=True, bank_sha256=sha(inputs/'bank.json'),
            world_sha256=layout['world_sha256'], layout_id=layout['id'], source_qc=qc,
            outcome=dict(measurement_valid=True, task_success=True, motion_quality_pass=True,
                         all_obstacles_recovered=True, terminated=True, truncated=False)))
        rewrite_manifest(root)
    ready = require_live_qualification(req)
    assert set(ready.baselines) == {(f, 0) for f in FAMILIES}
    assert checked_components == ['mixed']
    slope = req.prepared_root/'baseline_slope_s0'
    result = json.loads((slope/'result.json').read_text())
    result['outcome']['task_success'] = False
    save(slope/'result.json', result)
    rewrite_manifest(slope)
    with pytest.raises(ValueError, match='unqualified'):
        require_live_qualification(req)


def test_training_identity_records_v2_campaign_without_changing_optimizer_profile(tmp_path):
    req = request(tmp_path)
    identity = training_identity(req, qualified(tmp_path, FAMILIES))
    assert identity['smoke_protocol'] == req.protocol.identity()
    assert identity['budget'] == req.protocol.budget()
    assert identity['profile_id'] == 'nino_td3_smoke_h5_v1'
    assert set(identity['baselines']) == {f+'_s0' for f in FAMILIES}
