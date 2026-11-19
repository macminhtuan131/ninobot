import json

import pytest

from nino_rl import recovery_campaign_contract as contract
from nino_rl import recovery_runner as runner
from nino_rl.recovery_curriculum import FAMILIES
from nino_rl.recovery_training_contract import sha
from nino_rl.residual_workflow import save


def manifest(root):
    save(root/'manifest.json', {str(p.relative_to(root)): sha(p)
        for p in root.rglob('*') if p.is_file() and p.name != 'manifest.json'})


@pytest.fixture
def readiness(tmp_path, monkeypatch):
    prepared = tmp_path/'prepared'
    (prepared/'inputs').mkdir(parents=True)
    bank = dict(layouts=[dict(family=f, stage=0, split='development',
        id=f+'_fixture_s0', world_sha256='a'*64) for f in FAMILIES])
    save(prepared/'inputs/bank.json', bank)
    request = contract.CampaignRequest.parse(dict(prepared_root=str(prepared)))
    monkeypatch.setattr(runner, 'require_bank', lambda _: bank)
    monkeypatch.setattr(runner, 'sources', lambda: dict(current=True))
    root = tmp_path/'campaign'
    for layout in bank['layouts']:
        family = layout['family']
        probe = root/'readiness'/f'{family}_s0'
        raw = probe/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
        raw.parent.mkdir(parents=True)
        raw.write_text(''.join(json.dumps(dict(channel=channel, stamp_s=i*.01))+'\n'
            for i in range(11) for channel in ('imu', 'wheel', 'truth', 'drive')))
        save(probe/'episode_0_reset.json', dict(private_layout=layout,
            reset=dict(physical_sample=dict(stamp_s=0.))))
        (probe/'environment_trace.jsonl').write_text(json.dumps(dict(episode=0,
            physical_sample=dict(stamp_s=.1)))+'\n')
        qc = runner.raw_qc(probe)
        save(probe/'job.json', dict(kind=contract.CAMPAIGN_KIND, action='readiness-probe',
            status='completed', source_pins=dict(current=True), clean_closure=True))
        save(probe/'result.json', dict(family=family, stage=0, layout_id=layout['id'],
            world_sha256=layout['world_sha256'], bank_sha256=sha(prepared/'inputs/bank.json'),
            source_qc=qc, outcome=dict(measurement_valid=True, task_success=False,
                motion_quality_pass=False, all_obstacles_recovered=False,
                terminated=True, truncated=False, termination_reason='stall')))
        manifest(probe)
    return request, root


def change_outcome(root, **changes):
    probe = root/'readiness/clean_s0'
    result = json.loads((probe/'result.json').read_text())
    result['outcome'].update(changes)
    save(probe/'result.json', result)
    manifest(probe)


@pytest.mark.parametrize('reason', ['stall', 'path_violation', 'physical_envelope_failure',
    'recovery_timeout', 'motion_quality_violation', 'task_timeout'])
def test_valid_physical_failures_admit_training_without_claiming_success(readiness, reason):
    request, root = readiness
    change_outcome(root, termination_reason=reason)
    ready = contract.require_ready(request, root)
    assert set(ready.receipts) == set(FAMILIES)
    assert ready.layout('clean')['stage'] == 0
    with pytest.raises(ValueError):
        ready.layout('clean', 1)


@pytest.mark.parametrize('reason', ['drive_fault', 'owner_intervention',
    'reference_intervention', 'unclassified_failure', ''])
def test_faults_and_unclassified_outcomes_cannot_qualify_backend_readiness(readiness, reason):
    request, root = readiness
    change_outcome(root, termination_reason=reason)
    with pytest.raises(ValueError, match='readiness'):
        contract.require_ready(request, root)


def test_terminal_and_censor_flags_cannot_both_be_true(readiness):
    request, root = readiness
    change_outcome(root, terminated=True, truncated=True)
    with pytest.raises(ValueError, match='readiness'):
        contract.require_ready(request, root)


def test_empty_trace_cannot_remove_the_readiness_tail_support_check(readiness):
    request, root = readiness
    probe = root/'readiness/clean_s0'
    (probe/'environment_trace.jsonl').write_text('')
    qc = runner.raw_qc(probe)
    assert qc['episodes']['episode_0']['boundary_coverage_checked'] is False
    result = json.loads((probe/'result.json').read_text())
    result['source_qc'] = qc
    save(probe/'result.json', result)
    manifest(probe)
    with pytest.raises(ValueError, match='readiness'):
        contract.require_ready(request, root)


def test_source_qc_failure_remains_fatal(readiness):
    request, root = readiness
    probe = root/'readiness/clean_s0'
    raw = probe/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    rows = [row for row in rows if row['channel'] != 'wheel']
    raw.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    qc = runner.raw_qc(probe)
    assert qc['valid'] is False
    result = json.loads((probe/'result.json').read_text())
    result['source_qc'] = qc
    save(probe/'result.json', result)
    manifest(probe)
    with pytest.raises(ValueError, match='readiness'):
        contract.require_ready(request, root)


def test_nonfinite_critic_cannot_be_saved_as_a_qualified_checkpoint(tmp_path):
    from types import SimpleNamespace
    import gymnasium as gym
    import numpy as np
    import torch
    from stable_baselines3.common.vec_env import DummyVecEnv
    from nino_rl import recovery_campaign as campaign

    class ObservationFixture(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., (100,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return np.zeros(100, dtype=np.float32), {}

    request = contract.CampaignRequest.parse(dict(prepared_root=str(tmp_path/'prepared')))
    out = tmp_path/'campaign'
    out.mkdir()
    vec = DummyVecEnv([ObservationFixture])
    model = campaign.build_model(vec, request)
    identity = dict(kind=contract.CAMPAIGN_KIND, checkpoint_kind=contract.CHECKPOINT_KIND,
                    request=request.state())
    qc = dict(valid=True, episodes=dict(episode_0=dict(valid=True)))
    state = dict(transitions=0, launch_attempts=1, completed=[dict(task_success=False)], censored=[])
    environment = SimpleNamespace(phase='ready', audit_sources=lambda: qc, state=lambda: state)
    with torch.no_grad():
        next(model.critic.parameters()).flatten()[0] = float('nan')
    try:
        with pytest.raises(ValueError, match='[Nn]onfinite|finite'):
            campaign.write_checkpoint(model, out, request, identity, environment, 0,
                                      qualified=True, reason='adversarial_critic')
    finally:
        vec.close()
