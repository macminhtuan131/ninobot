"""Unit tests for isolated common103_v2 engine, gated-zero Critic reward, and multi-seed [11, 22, 33]."""
from __future__ import annotations

import json
import os
from pathlib import Path
import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from nino_rl import common_studio_contract as v1_spec
from nino_rl import common_studio_v2_contract as v2_spec
from nino_rl import common_training_studio_v2 as v2_studio
from nino_rl import equal_information_v2 as v2_ctrl
from nino_rl import prestop_authority_draft as draft
from nino_rl import residual_equal_information as offline_fixture
from nino_rl import training_studio_api_v2 as api_v2


def test_frozen_v1_and_draft_hashes_remain_untouched():
    # Verify all 8 workspace files pinned in prestop_tail_authority_draft_v1.json remain byte-identical
    raw = json.loads(
        (Path(__file__).resolve().parents[1] / 'config/prestop_tail_authority_draft_v1.json').read_text()
    )
    import hashlib

    repo_root = Path(__file__).resolve().parents[3]
    checked = 0
    for path_str, expected_sha in raw['frozen_inputs'].items():
        p = Path(path_str)
        if p.is_relative_to(repo_root):
            assert hashlib.sha256(p.read_bytes()).hexdigest() == expected_sha, f'Frozen file modified: {p}'
            checked += 1
    assert checked >= 8
    assert v1_spec.MAX_STEPS == 20_000
    assert v1_spec.profiles()['nino_td3_research_h5_v1']['algorithm']['buffer_size'] == 32_768
    _ = draft.DRAFT_ID


def test_v2_raises_buffer_to_100k_and_max_steps_to_100k_with_obstacle_scenarios():
    profiles = v2_spec.profiles()
    assert profiles['nino_td3_research_h5_v1']['algorithm']['buffer_size'] >= 100_000
    assert profiles['nino_td3_smoke_h5_v1']['algorithm']['buffer_size'] == 2048
    assert v2_spec.MAX_STEPS == 100_000
    assert {'box_c1_6mm', 'box_c1_6mm_dr', 'clear_box'} <= set(v2_spec.SCENARIOS)

    for scenario in ('box_c1_6mm', 'box_c1_6mm_dr', 'clear_box'):
        req = api_v2.validate_request(
            dict(
                schema_version=2,
                engine='common103_v2',
                mode='train',
                scenario=scenario,
                profile='nino_td3_research_h5_v1',
                timesteps=50_000,
                seed=11,
                checkpoint_every=10_000,
                wall_minutes=480,
                evaluate=True,
                resume=None,
                multi_seeds=[11, 22, 33],
                auto_prune_raw=True,
            )
        )
        assert req['engine'] == 'common103_v2'
        assert req['scenario'] == scenario
        assert req['timesteps'] == 50_000
        assert req['multi_seeds'] == [11, 22, 33]


def test_closed_window_gates_out_action_penalties_for_clean_critic_signal():
    c, _, task, bc = v2_ctrl.configuration(6.0, scenario='box_c1_6mm')
    c['backend'].update(wheel_gain=[1.0, 1.0], motor_lag_s=[0.16, 0.16], imu_noise_std=0.0)
    env = v2_ctrl.environment(c, offline_fixture.fixture_backend(c, 6.0), task, bc, scenario='box_c1_6mm')
    closed_count = open_count = 0
    prev_row = None
    epoch = None
    abi = v2_ctrl.identity('box_c1_6mm')['abi_sha256']
    try:
        env.reset(seed=701)
        for step in range(140):
            # Alternate noisy +/-1.0 actions even when gate is closed
            noisy_action = np.array([1.0 if step % 2 == 0 else -1.0], dtype=np.float32)
            _, reward, term, trunc, info = env.step(noisy_action)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc), **info)
            epoch = epoch if epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            v2_ctrl.verify_transition_v2(row, prev_row, epoch, abi, 'box_c1_6mm', strict_task=False)
            prev_row = row
            if info['plan_projection']['window_open']:
                open_count += 1
                assert info['reward_terms']['action_size'] < 0.0
            else:
                closed_count += 1
                assert info['reward_terms']['action_size'] == 0.0
                assert info['reward_terms']['action_change'] == 0.0
                assert info['controller_proposal'] == [0.0, 0.0]
    finally:
        env.close()
    assert open_count > 0 and closed_count > 0


def test_classical_request_maintains_exact_physical_compensation_across_scenarios():
    obs_open = np.zeros(103, dtype=np.float32)
    obs_open[101] = 1.0
    obs_closed = np.zeros(103, dtype=np.float32)

    req_obs = v2_ctrl.classical_request(obs_open, scenario='box_c1_6mm')
    req_clear = v2_ctrl.classical_request(obs_open, scenario='clear_box')
    assert float(req_obs[0]) * 0.02 == pytest.approx(0.005)
    assert float(req_clear[0]) * 0.005 == pytest.approx(0.005)
    assert float(v2_ctrl.classical_request(obs_closed, scenario='box_c1_6mm')[0]) == 0.0


def test_multi_seed_summary_selects_checkpoint_by_physical_metrics_and_compares_arms():
    def _make_seed_result(seed: int, td3_vrmse: float, cls_vrmse: float, reward_fake: float):
        def _ep(arm: str, stop: float, v_err: float):
            return dict(
                arm=arm,
                source_stop_s=stop,
                training_return_ignored=reward_fake,
                physical_metrics=dict(
                    rms_v_m_s=v_err,
                    rms_omega_rad_s=0.002,
                    max_overshoot_m_s=0.004,
                    settling_time_s=1.2,
                    action_jerk_rms=0.05,
                    saturation_fraction=0.0,
                    safety_intervention_rate=0.0,
                ),
            )

        return dict(
            seed=seed,
            global_steps=50_000,
            checkpoint=f'/tmp/seed_{seed}/checkpoints/step_50000_final',
            evaluation=[
                _ep('Classical_scheduled', 6.0, cls_vrmse),
                _ep('Classical_scheduled', 8.0, cls_vrmse),
                _ep('TD3', 6.0, td3_vrmse),
                _ep('TD3', 8.0, td3_vrmse),
            ],
        )

    # Seed 22 has lowest physical rms_v_m_s (0.0061) despite lower training reward
    seed_results = [
        _make_seed_result(11, td3_vrmse=0.0068, cls_vrmse=0.0085, reward_fake=999.0),
        _make_seed_result(22, td3_vrmse=0.0061, cls_vrmse=0.0084, reward_fake=-10.0),
        _make_seed_result(33, td3_vrmse=0.0065, cls_vrmse=0.0086, reward_fake=50.0),
    ]
    summary = v2_studio.summarize_multi_seed_results(seed_results, min_eval_episodes=2)
    assert summary['seeds'] == [11, 22, 33]
    assert summary['checkpoint_selection']['selected']['checkpoint_id'] == 'seed_22_step_50000'
    assert summary['arm_comparison']['verdict'] == 'EXPLORATORY_ONLY_INDEPENDENT_TEST_REQUIRED'
    assert summary['checkpoint_selection']['status'] == 'DEVELOPMENT_NOMINATION_ONLY'
    assert summary['benefit_verified'] is False
    assert summary['arm_comparison']['relative_linear_rms_gain'] > 0.20


def test_gui_and_storage_support_common103_v2_and_multiseed(tmp_path, monkeypatch):
    from PyQt5 import QtWidgets as Q
    from nino_pi import training_storage as storage
    from nino_pi.td3_training_panel import TD3TrainingPanel

    monkeypatch.setattr(v2_spec, 'require_disk', lambda *a: {})
    monkeypatch.setattr(v2_spec, 'require_campaign_disk', lambda *a, **kw: {})
    q = Q.QApplication.instance() or Q.QApplication([])
    panel = TD3TrainingPanel(root=tmp_path, observe_external=False)
    try:
        panel.engine.setCurrentIndex(panel.engine.findData('common103_v2'))
        panel.scenario.setCurrentIndex(panel.scenario.findData('box_c1_6mm_dr'))
        panel.timesteps.setValue(50_000)
        panel.multi_seed.setChecked(True)
        req = panel.request('train')
        assert req['engine'] == 'common103_v2'
        assert req['scenario'] == 'box_c1_6mm_dr'
        assert req['timesteps'] == 50_000
        assert req['multi_seeds'] == [11, 22, 33]
    finally:
        panel.close()
        q.processEvents()

    # Verify storage retention also accepts nino_common_studio_job_v2
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    job_dir = tmp_path / 'v2_job'
    cp_dir = job_dir / 'checkpoints/step_50000_final'
    cp_dir.mkdir(parents=True)
    for name in ('model.zip', 'replay_buffer.pkl', 'resume_identity.json'):
        (cp_dir / name).write_text('{}')
    (cp_dir / 'checkpoint.json').write_text(json.dumps(dict(global_steps=50000, reason='final')))
    (cp_dir / 'manifest.json').write_text(
        json.dumps(
            dict(
                kind='nino_common_studio_checkpoint_v2',
                status='resumable',
                files={p.name: storage.digest(p) for p in cp_dir.iterdir()},
            )
        )
    )
    (job_dir / 'job.json').write_text(json.dumps(dict(status='completed', hardware_actions=0, request=dict(mode='train'))))
    (job_dir / 'training_result.json').write_text(json.dumps(dict(checkpoint=str(cp_dir))))
    (job_dir / 'environment_trace.jsonl').write_text('')
    (job_dir / 'training_trace.jsonl').write_text('')
    ep_raw = job_dir / 'episodes/episode_0/backend'
    ep_raw.mkdir(parents=True)
    (ep_raw / 'raw.jsonl').write_text('{"raw":true}\n')
    (job_dir / 'manifest.json').write_text(
        json.dumps(
            dict(
                kind='nino_common_studio_job_v2',
                status='completed',
                hardware_actions=0,
                files={str(p.relative_to(job_dir)): storage.digest(p) for p in job_dir.rglob('*') if p.is_file()},
            )
        )
    )
    receipt = storage.prune_completed_job(job_dir, apply=True)
    assert receipt['status'] == 'completed' and receipt['removed_episode_count'] == 1
