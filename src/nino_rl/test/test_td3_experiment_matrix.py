"""Tests for TD3 sequential tuning hierarchy, E1-E3 experiment matrix, checkpoint selection, and 7 safety gates."""
from copy import deepcopy
import pytest

from nino_rl.residual_experiment import source_fingerprint
from nino_rl.td3_config import load_profiles
from nino_rl.td3_experiment_matrix import (
    DEPLOYMENT_GATE_IDS,
    check_profile_within_bounds,
    compare_experiment_arms,
    evaluate_deployment_gates,
    evaluate_tuning_readiness,
    load_matrix,
    select_best_checkpoint,
    summarize_experiment_arm,
    validate_matrix,
)

SEALED_SOURCE_FINGERPRINT = 'f1a97c385059bcdc8da2de4c7992e2ff79ff0db12734d2049246bab072a18907'


def _sample_metrics(rms_v=0.040, rms_w=0.080, overshoot=0.015, settle=0.9, jerk=0.25, sat=0.02, safety=0.0):
    return {
        'rms_v_m_s': rms_v,
        'rms_omega_rad_s': rms_w,
        'max_overshoot_m_s': overshoot,
        'settling_time_s': settle,
        'action_jerk_rms': jerk,
        'saturation_fraction': sat,
        'safety_intervention_rate': safety,
    }


def test_source_fingerprint_remains_sealed():
    assert source_fingerprint() == SEALED_SOURCE_FINGERPRINT


def test_matrix_schema_and_catalog_profiles_within_bounds():
    matrix = load_matrix()
    report = validate_matrix(matrix)
    assert report['valid'] is True
    assert report['experiments'] == ['E1', 'E2', 'E3']
    assert report['deployment_gates_count'] == 7
    assert report['hardware_authority'] == 0

    profiles = load_profiles()
    for pid in ('nino_td3_research_h5_v1', 'nino_td3_research_h8_v1', 'nino_td3_research_h1_v1'):
        bounds_report = check_profile_within_bounds(profiles[pid], matrix)
        assert bounds_report['within_recommended_bounds'] is True, bounds_report['warnings']
    smoke_bounds = check_profile_within_bounds(profiles['nino_td3_smoke_h5_v1'], matrix)
    assert smoke_bounds['within_recommended_bounds'] is False
    assert any('seeds count' in w for w in smoke_bounds['warnings'])

    bad = deepcopy(matrix)
    bad['hardware_authority_default'] = 1
    with pytest.raises(ValueError, match='hardware_authority_default'):
        validate_matrix(bad)

    bad_seeds = deepcopy(matrix)
    bad_seeds['experiments']['E1']['min_seeds'] = 2
    with pytest.raises(ValueError, match='E1'):
        validate_matrix(bad_seeds)


def test_sequential_tuning_blocks_hyperparameters_until_contract_sysid_and_reward_verified():
    initial = evaluate_tuning_readiness({})
    assert initial['active_stage'] == 'observation_action_contract'
    assert initial['hyperparameter_tuning_allowed'] is False
    assert initial['stage_statuses']['algorithm_hyperparameters'] == 'BLOCKED_BY_PREREQUISITES'

    # Claiming stage 4 without stage 2 still keeps stage 4 blocked.
    skipped = evaluate_tuning_readiness({
        'observation_action_contract': True,
        'dynamics_model_sysid': False,
        'reward_and_termination': True,
        'algorithm_hyperparameters': True,
    })
    assert skipped['active_stage'] == 'dynamics_model_sysid'
    assert skipped['hyperparameter_tuning_allowed'] is False
    assert skipped['stage_statuses']['algorithm_hyperparameters'] == 'BLOCKED_BY_PREREQUISITES'

    unlocked = evaluate_tuning_readiness({
        'observation_action_contract': True,
        'dynamics_model_sysid': True,
        'reward_and_termination': True,
    })
    assert unlocked['active_stage'] == 'algorithm_hyperparameters'
    assert unlocked['hyperparameter_tuning_allowed'] is True


def test_checkpoint_selection_forbids_training_reward_only_and_rejects_unsafe():
    with pytest.raises(ValueError, match='training_reward alone is forbidden'):
        select_best_checkpoint([{'checkpoint_id': 'step_10000', 'training_reward': 999.0}])

    decision = select_best_checkpoint([
        {'checkpoint_id': 'high_reward_unsafe', 'training_reward': 500.0,
         'heldout_metrics': _sample_metrics(rms_v=0.020, safety=0.05)},
        {'checkpoint_id': 'ckpt_20k', 'training_reward': 120.0,
         'heldout_metrics': _sample_metrics(rms_v=0.042, rms_w=0.080, jerk=0.30)},
        {'checkpoint_id': 'ckpt_30k', 'training_reward': 95.0,
         'heldout_metrics': _sample_metrics(rms_v=0.031, rms_w=0.072, jerk=0.22)},
    ])
    assert decision['status'] == 'SELECTED_BY_HELDOUT_PHYSICAL_METRICS'
    assert decision['selected']['checkpoint_id'] == 'ckpt_30k'
    assert decision['rejected'][0]['checkpoint_id'] == 'high_reward_unsafe'


def test_multi_seed_horizontal_comparison_and_regressions():
    classical = [
        {'seed': 11, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.050, rms_w=0.090, overshoot=0.015, jerk=0.20)},
        {'seed': 22, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.052, rms_w=0.092, overshoot=0.016, jerk=0.21)},
        {'seed': 33, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.048, rms_w=0.088, overshoot=0.014, jerk=0.19)},
    ]
    with pytest.raises(ValueError, match='independent seeds'):
        summarize_experiment_arm(classical[:2])

    good_td3 = [
        {'seed': 11, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.041, rms_w=0.082, overshoot=0.018, jerk=0.21)},
        {'seed': 22, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.042, rms_w=0.084, overshoot=0.019, jerk=0.22)},
        {'seed': 33, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.040, rms_w=0.080, overshoot=0.017, jerk=0.20)},
    ]
    win = compare_experiment_arms(classical, good_td3)
    assert win['verdict'] == 'CANDIDATE_PASSES_HORIZONTAL_GATE'
    assert win['regressions'] == []

    jerky_td3 = [
        {'seed': 11, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.040, rms_w=0.082, overshoot=0.018, jerk=0.45)},
        {'seed': 22, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.041, rms_w=0.083, overshoot=0.018, jerk=0.46)},
        {'seed': 33, 'episodes': 20, 'metrics': _sample_metrics(rms_v=0.039, rms_w=0.081, overshoot=0.018, jerk=0.44)},
    ]
    hold = compare_experiment_arms(classical, jerky_td3)
    assert hold['verdict'] == 'HOLD_BASELINE_RETAINED'
    assert any('jerk_ratio_exceeded' in r for r in hold['regressions'])


def test_deployment_safety_gates_block_until_all_seven_pass_and_keep_zero_authority():
    partial = {gid: True for gid in DEPLOYMENT_GATE_IDS[:-1]}
    blocked = evaluate_deployment_gates(partial)
    assert blocked['verdict'] == 'BLOCKED'
    assert blocked['blocking_gates'] == [DEPLOYMENT_GATE_IDS[-1]]
    assert blocked['hardware_authority'] == 0

    all_ok = {gid: True for gid in DEPLOYMENT_GATE_IDS}
    ready = evaluate_deployment_gates(all_ok)
    assert ready['all_gates_passed'] is True
    assert ready['verdict'] == 'ELIGIBLE_FOR_HUMAN_SUPERVISED_RELEASE_REVIEW'
    assert ready['hardware_authority'] == 0
