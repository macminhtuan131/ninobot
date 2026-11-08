"""TD3 sequential tuning hierarchy, E1-E3 experiment matrix, and deployment safety gates.

Offline validation and statistical comparison utilities only; never unlocks hardware authority
or starts training jobs implicitly.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

REQUIRED_METRICS = (
    'rms_v_m_s',
    'rms_omega_rad_s',
    'max_overshoot_m_s',
    'settling_time_s',
    'action_jerk_rms',
    'saturation_fraction',
    'safety_intervention_rate',
)

STAGE_ORDER = (
    'observation_action_contract',
    'dynamics_model_sysid',
    'reward_and_termination',
    'algorithm_hyperparameters',
)

DEPLOYMENT_GATE_IDS = (
    'offline_sim_and_replay_verified',
    'beats_tuned_classical_on_heldout',
    'pi_zero_authority_shadow_verified',
    'software_and_gui_fault_tests_passed',
    'hardware_interlocks_active',
    'operator_supervision_and_clear_zone',
    'instant_classical_fallback_verified',
)


def matrix_path() -> Path:
    local = Path(__file__).resolve().parents[1] / 'config' / 'td3_experiment_matrix_v1.yaml'
    if local.is_file():
        return local
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory('nino_rl')) / 'config' / 'td3_experiment_matrix_v1.yaml'


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def load_matrix(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else matrix_path()
    data = yaml.safe_load(target.read_text(encoding='utf-8'))
    validate_matrix(data)
    return data


def validate_matrix(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping) or data.get('schema_version') != 1:
        raise ValueError('Experiment matrix requires schema_version=1 mapping')
    if data.get('frozen_policy_rate_hz') != 10:
        raise ValueError('Policy rate must match frozen 10 Hz contract')
    if data.get('hardware_authority_default') != 0:
        raise ValueError('hardware_authority_default must remain 0')

    stages = data.get('tuning_stages')
    if not isinstance(stages, list) or [s.get('stage_id') for s in stages] != list(STAGE_ORDER):
        raise ValueError('tuning_stages must follow strict 4-stage sequential order')
    if [s.get('order') for s in stages] != [1, 2, 3, 4]:
        raise ValueError('tuning_stages order indices must be [1, 2, 3, 4]')

    bounds = data.get('hyperparameter_bounds')
    if not isinstance(bounds, Mapping):
        raise ValueError('Missing hyperparameter_bounds')
    for key in ('actor_lr', 'critic_lr', 'gamma', 'tau', 'target_policy_noise',
                'target_noise_clip', 'exploration_noise', 'batch_size',
                'buffer_size', 'learning_starts', 'policy_delay'):
        pair = bounds.get(key)
        if (not isinstance(pair, list) or len(pair) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pair)
                or pair[0] <= 0 or pair[0] > pair[1]):
            raise ValueError(f'Invalid hyperparameter bound for {key}')
    if int(bounds.get('min_seeds', 0)) < 3 or int(bounds.get('min_eval_episodes_per_seed', 0)) < 20:
        raise ValueError('Experiment matrix requires >=3 seeds and >=20 eval episodes/seed')

    metrics_cfg = data.get('physical_metrics', {})
    if tuple(metrics_cfg.get('required', ())) != REQUIRED_METRICS:
        raise ValueError('physical_metrics.required mismatch')
    if metrics_cfg.get('checkpoint_selection', {}).get('forbid_training_reward_only') is not True:
        raise ValueError('forbid_training_reward_only must be True')

    experiments = data.get('experiments')
    if not isinstance(experiments, Mapping) or set(experiments) != {'E1', 'E2', 'E3'}:
        raise ValueError('Experiment matrix must define E1, E2, and E3')
    for code, spec in experiments.items():
        if int(spec.get('min_seeds', 0)) < 3 or int(spec.get('episodes_per_seed', 0)) < 20:
            raise ValueError(f'{code} must require >=3 seeds and >=20 episodes/seed')
        if not spec.get('baseline_arm') or not spec.get('candidate_arms'):
            raise ValueError(f'{code} missing baseline_arm or candidate_arms')

    gates = data.get('deployment_safety_gates')
    if not isinstance(gates, list) or tuple(g.get('gate_id') for g in gates) != DEPLOYMENT_GATE_IDS:
        raise ValueError('deployment_safety_gates must match all 7 mandatory safety gates')
    if not all(g.get('mandatory') is True for g in gates):
        raise ValueError('All deployment safety gates must remain mandatory')

    return {
        'valid': True,
        'matrix_id': data['matrix_id'],
        'matrix_sha256': canonical_sha256(data),
        'stages': list(STAGE_ORDER),
        'experiments': sorted(experiments),
        'deployment_gates_count': len(gates),
        'hardware_authority': 0,
    }


def check_profile_within_bounds(profile: Mapping[str, Any], matrix: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Check whether a TD3 profile YAML falls inside the recommended search bounds."""
    spec = deepcopy(dict(matrix)) if matrix is not None else load_matrix()
    bounds = spec['hyperparameter_bounds']
    algo = profile.get('algorithm', {})
    eval_cfg = profile.get('evaluation', {})
    warnings: list[str] = []
    checked: dict[str, Any] = {}
    for key in ('actor_lr', 'critic_lr', 'gamma', 'tau', 'target_policy_noise',
                'target_noise_clip', 'exploration_noise', 'batch_size',
                'buffer_size', 'learning_starts', 'policy_delay'):
        if key not in algo:
            warnings.append(f'missing:{key}')
            continue
        lo, hi = bounds[key]
        val = algo[key]
        in_range = lo <= val <= hi
        checked[key] = {'value': val, 'bounds': [lo, hi], 'in_bounds': in_range}
        if not in_range:
            warnings.append(f'{key}={val} outside [{lo}, {hi}]')
    seeds = eval_cfg.get('seeds') if 'seeds' in eval_cfg else algo.get('seeds', [])
    if len(seeds) < bounds['min_seeds']:
        warnings.append(f'seeds count {len(seeds)} < {bounds["min_seeds"]}')
    if 'episodes_per_seed' in eval_cfg and int(eval_cfg['episodes_per_seed']) < bounds['min_eval_episodes_per_seed']:
        warnings.append(f'episodes_per_seed {eval_cfg["episodes_per_seed"]} < {bounds["min_eval_episodes_per_seed"]}')
    return {
        'profile_id': profile.get('profile_id', 'unknown'),
        'within_recommended_bounds': len(warnings) == 0,
        'warnings': warnings,
        'checked_parameters': checked,
    }


def evaluate_tuning_readiness(stage_verified: Mapping[str, bool]) -> dict[str, Any]:
    """Enforce sequential tuning order: contract -> dynamics -> reward -> hyperparameters."""
    statuses: dict[str, str] = {}
    prerequisites_ok = True
    active_stage: str | None = None
    for stage_id in STAGE_ORDER:
        verified = stage_verified.get(stage_id) is True
        if verified and prerequisites_ok:
            statuses[stage_id] = 'VERIFIED'
        elif prerequisites_ok:
            statuses[stage_id] = 'ACTIVE_NEXT'
            if active_stage is None:
                active_stage = stage_id
            prerequisites_ok = False
        else:
            statuses[stage_id] = 'BLOCKED_BY_PREREQUISITES'
    return {
        'stage_statuses': statuses,
        'active_stage': active_stage or 'completed_all_stages',
        'hyperparameter_tuning_allowed': statuses['algorithm_hyperparameters'] in ('ACTIVE_NEXT', 'VERIFIED'),
    }


def select_best_checkpoint(
    candidates: Sequence[Mapping[str, Any]],
    omega_weight: float = 0.25,
    max_safety_intervention_rate: float = 0.0,
) -> dict[str, Any]:
    """Select checkpoint strictly by held-out physical metrics, never training reward alone."""
    if not candidates:
        raise ValueError('At least one checkpoint candidate is required')
    eligible: list[tuple[float, dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for raw in candidates:
        cid = str(raw.get('checkpoint_id', '')).strip()
        if not cid:
            raise ValueError('Each checkpoint candidate requires checkpoint_id')
        metrics = raw.get('heldout_metrics')
        if not isinstance(metrics, Mapping):
            raise ValueError(
                f'Checkpoint {cid} missing heldout_metrics; selecting by training_reward alone is forbidden'
            )
        missing = [m for m in REQUIRED_METRICS if m not in metrics]
        if missing:
            raise ValueError(f'Checkpoint {cid} missing physical metrics: {missing}')
        for m in REQUIRED_METRICS:
            val = metrics[m]
            if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val) or val < 0:
                raise ValueError(f'Checkpoint {cid} has invalid metric {m}={val!r}')
        if metrics['safety_intervention_rate'] > max_safety_intervention_rate:
            rejected.append({'checkpoint_id': cid, 'reason': 'safety_intervention_rate_exceeded'})
            continue
        score = float(metrics['rms_v_m_s']) + omega_weight * float(metrics['rms_omega_rad_s'])
        eligible.append((score, {'checkpoint_id': cid, 'composite_tracking_error': score, 'metrics': dict(metrics)}))
    if not eligible:
        return {'selected': None, 'status': 'NO_SAFE_CHECKPOINT', 'rejected': rejected}
    eligible.sort(key=lambda item: (item[0], item[1]['metrics']['action_jerk_rms'], item[1]['checkpoint_id']))
    return {
        'selected': eligible[0][1],
        'status': 'SELECTED_BY_HELDOUT_PHYSICAL_METRICS',
        'rejected': rejected,
        'ranked_count': len(eligible),
    }


def summarize_experiment_arm(seed_runs: Sequence[Mapping[str, Any]], min_seeds: int = 3, min_episodes: int = 20) -> dict[str, Any]:
    """Aggregate per-seed held-out evaluation runs with cross-seed mean, sample std, and 95% CI."""
    if len(seed_runs) < min_seeds:
        raise ValueError(f'Requires at least {min_seeds} independent seeds; got {len(seed_runs)}')
    seen_seeds: set[int] = set()
    for run in seed_runs:
        seed = run.get('seed')
        episodes = run.get('episodes', 0)
        if not isinstance(seed, int) or isinstance(seed, bool) or seed in seen_seeds:
            raise ValueError(f'Invalid or duplicate seed: {seed!r}')
        if not isinstance(episodes, int) or episodes < min_episodes:
            raise ValueError(f'Seed {seed} has {episodes} episodes; requires >= {min_episodes}')
        seen_seeds.add(seed)
        metrics = run.get('metrics', {})
        for key in REQUIRED_METRICS:
            val = metrics.get(key)
            if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val) or val < 0:
                raise ValueError(f'Seed {seed} invalid metric {key}={val!r}')

    n = len(seed_runs)
    summary: dict[str, dict[str, float]] = {}
    for key in REQUIRED_METRICS:
        vals = [float(r['metrics'][key]) for r in seed_runs]
        mean = sum(vals) / n
        variance = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
        std = math.sqrt(variance)
        ci95 = 1.96 * std / math.sqrt(n)
        summary[key] = {'mean': mean, 'std': std, 'ci95_half_width': ci95, 'min': min(vals), 'max': max(vals)}
    return {'seed_count': n, 'seeds': sorted(seen_seeds), 'metrics': summary}


def compare_experiment_arms(
    baseline_runs: Sequence[Mapping[str, Any]],
    candidate_runs: Sequence[Mapping[str, Any]],
    *,
    max_jerk_ratio: float = 1.15,
    max_overshoot_delta_m_s: float = 0.02,
    min_relative_rms_gain: float = 0.03,
) -> dict[str, Any]:
    """Horizontal physical comparison between baseline (e.g. Classical) and candidate TD3 arm."""
    base = summarize_experiment_arm(baseline_runs)
    cand = summarize_experiment_arm(candidate_runs)
    b_v = base['metrics']['rms_v_m_s']['mean']
    c_v = cand['metrics']['rms_v_m_s']['mean']
    b_w = base['metrics']['rms_omega_rad_s']['mean']
    c_w = cand['metrics']['rms_omega_rad_s']['mean']
    rel_v_gain = (b_v - c_v) / max(b_v, 1e-9)
    rel_w_gain = (b_w - c_w) / max(b_w, 1e-9)
    jerk_ratio = cand['metrics']['action_jerk_rms']['mean'] / max(base['metrics']['action_jerk_rms']['mean'], 1e-9)
    overshoot_delta = cand['metrics']['max_overshoot_m_s']['mean'] - base['metrics']['max_overshoot_m_s']['mean']
    safety_clean = cand['metrics']['safety_intervention_rate']['mean'] <= base['metrics']['safety_intervention_rate']['mean'] and cand['metrics']['safety_intervention_rate']['max'] == 0.0

    regressions: list[str] = []
    if rel_v_gain < min_relative_rms_gain:
        regressions.append(f'linear_rms_gain_below_threshold:{rel_v_gain:.4f}')
    if c_w > b_w * 1.02:
        regressions.append(f'angular_rms_regression:{c_w:.4f}>{b_w:.4f}')
    if jerk_ratio > max_jerk_ratio:
        regressions.append(f'jerk_ratio_exceeded:{jerk_ratio:.3f}')
    if overshoot_delta > max_overshoot_delta_m_s:
        regressions.append(f'overshoot_delta_exceeded:{overshoot_delta:.4f}')
    if not safety_clean:
        regressions.append('safety_intervention_nonzero_or_worse')

    verdict = 'CANDIDATE_PASSES_HORIZONTAL_GATE' if not regressions else 'HOLD_BASELINE_RETAINED'
    return {
        'verdict': verdict,
        'relative_linear_rms_gain': rel_v_gain,
        'relative_angular_rms_gain': rel_w_gain,
        'jerk_ratio_vs_baseline': jerk_ratio,
        'overshoot_delta_m_s': overshoot_delta,
        'safety_clean': safety_clean,
        'regressions': regressions,
        'baseline': base,
        'candidate': cand,
    }


def evaluate_deployment_gates(gate_states: Mapping[str, bool]) -> dict[str, Any]:
    """Evaluate the 7 mandatory Section-8 deployment safety gates.

    Even when all 7 gates are satisfied, hardware_authority remains 0 until explicit human release.
    """
    blocking = [gid for gid in DEPLOYMENT_GATE_IDS if gate_states.get(gid) is not True]
    passed = [gid for gid in DEPLOYMENT_GATE_IDS if gate_states.get(gid) is True]
    return {
        'verdict': 'ELIGIBLE_FOR_HUMAN_SUPERVISED_RELEASE_REVIEW' if not blocking else 'BLOCKED',
        'all_gates_passed': len(blocking) == 0,
        'passed_gates': passed,
        'blocking_gates': blocking,
        'hardware_authority': 0,
        'note': 'Software check only; never enables motor authority automatically.',
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p_val = sub.add_parser('validate', help='Validate TD3 experiment and safety matrix YAML')
    p_val.add_argument('--matrix', default=None)
    p_prof = sub.add_parser('check-profile', help='Check a TD3 profile against matrix bounds')
    p_prof.add_argument('profile_id')
    args = parser.parse_args(argv)
    if args.cmd == 'validate':
        data = load_matrix(args.matrix)
        print(json.dumps(validate_matrix(data), ensure_ascii=False, indent=2))
        return 0
    from .td3_config import load_profiles
    profiles = load_profiles()
    if args.profile_id not in profiles:
        raise SystemExit(f'Unknown profile: {args.profile_id}')
    print(json.dumps(check_profile_within_bounds(profiles[args.profile_id]), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
