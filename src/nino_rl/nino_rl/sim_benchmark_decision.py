"""Read sealed results and qualify a proposed baseline algebra offline.

No actor loads, plant stepping, controller deployment, or physics/training release.
Shadow requests on old trajectories are NOT counterfactual outcomes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from nino_control.residual_velocity import FEATURES, SCALES

BENCHMARK_ID = 'nino_sim_static_gain_screen_v1_2026_11_06'
SOURCE_MANIFEST = '02832bf0e9d2bccf2e9361c56b61c9d634522b7321622764ce3842ea141ed9d9'


def repo():
    return Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def specification():
    p = read(repo() / 'src/nino_rl/config/sim_gain_benchmark_v1.json')
    if (p['benchmark_id'], p['single_factor'], p['gains_development'],
            p['source_stop_s'], p['horizon_s'], p['policy_dt_s'], p['common_bound_m_s'],
            p['observation_size'], p['history_frames'], p['action_size']) != (
            BENCHMARK_ID, 'fixed_common_reference_to_drive_gain_per_run', [.98, 1., 1.02],
            8., 14., .1, .005, 103, 5, 1):
        raise ValueError('Changed scientific design requires a versioned benchmark')
    if p['release'] != dict(physics_authorized=False, training_authorized=False,
            hardware_authorized=False, gazebo_launches_now=0, optimizer_updates_now=0, actor_loads_now=0):
        raise ValueError('Offline design cannot release physics, training or hardware')
    return p


def fingerprint():
    base = repo() / 'src/nino_rl'
    paths = [Path(__file__), base / 'config/sim_gain_benchmark_v1.json',
             base / 'test/test_sim_benchmark_decision.py']
    data = {str(p.relative_to(base)): sha(p) for p in paths}
    data['feature_implementation'] = sha(repo() / 'src/nino_control/nino_control/residual_velocity.py')
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def causal_gain_request(observation, geometry, candidate, *, bound=.005):
    """Proposed encoder-proxy baseline, pure function of the same causal103D.

    No injected gain, GT, pose, time-to-contact or future response argument.
    Fallback is a request of zero, not an override of gate/stop/fault ownership.
    """
    obs = np.asarray(observation, dtype=np.float64)
    if obs.shape != (103,) or not np.isfinite(obs).all() or np.max(np.abs(obs)) > 5.:
        raise ValueError('Finite bounded103D causal observation required')
    if obs[101] not in (0., 1.):
        raise ValueError('Explicit binary shared window required')
    if not math.isfinite(bound) or bound <= 0:
        raise ValueError('Positive finite common bound required')
    radii = [float(geometry[k]) for k in ('radius_l', 'radius_r')]
    if not all(math.isfinite(v) and v > 0 for v in radii):
        raise ValueError('Explicit positive nominal wheel radii required')
    if not obs[101]:
        return 0., dict(valid=False, reason='shared_window_closed')
    frames = obs[:100].reshape(5, 20)
    decode = lambda name: frames[:, FEATURES.index(name)] * SCALES[FEATURES.index(name)]
    references = decode('last_final_v_m_s')
    if (np.min(references) < candidate['minimum_reference_m_s'] or
            np.ptp(references) > candidate['maximum_reference_spread_m_s']):
        return 0., dict(valid=False, reason='reference_small_or_not_steady')
    measured = .5 * (decode('wheel_l_rad_s') * radii[0] + decode('wheel_r_rad_s') * radii[1])
    gain = float(np.median(measured / references))
    if not candidate['minimum_gain_estimate'] <= gain <= candidate['maximum_gain_estimate']:
        return 0., dict(valid=False, reason='proxy_gain_outside_declared_range')
    nominal = float(decode('baseline_v_m_s')[-1])
    scalar = float(np.clip((nominal / gain - nominal) / bound, -1., 1.))
    return scalar, dict(valid=True, reason='causal_encoder_proxy', gain_estimate=gain,
                        requested_common_m_s=scalar * bound, body_reference_verified=False)


def ideal_authority(p):
    """Exact static y=g*u algebra; explicitly not a Nino dynamics model."""
    nominal, bound = p['nominal_steady_m_s'], p['common_bound_m_s']
    rows = []
    for gain in p['gains_development']:
        delta = nominal / gain - nominal
        rows.append(dict(gain=gain,required_common_m_s=delta,
                         within_ideal_bound=abs(delta) <= bound,
                         achieved_static_speed_m_s=gain*(nominal+float(np.clip(delta,-bound,bound)))))
    return dict(model='ideal_static_y_equals_gain_times_reference_not_Nino_SysID',
                feasible_gain_interval=[nominal/(nominal+bound), nominal/(nominal-bound)],
                rows=rows,physical_feasibility_verified=False,learned_advantage_verified=False)


def summarize_trace(rows, geometry, p):
    if len(rows) != 140 or [r['step'] for r in rows] != list(range(140)):
        raise ValueError('Exactly140 sequential sealed decisions required')
    open_rows, closed_rows, shadow = [], [], []
    for row in rows:
        projection = row['plan_projection']
        obs = np.asarray(row['equal_observation'], dtype=np.float64)
        if bool(obs[101]) != projection['window_open']:
            raise ValueError('Causal shared-window evidence inconsistent')
        error = float(row['task']['velocity_error_m_s'])
        if not math.isfinite(error):
            raise ValueError('Nonfinite native velocity error')
        (open_rows if projection['window_open'] else closed_rows).append(row)
        request, audit = causal_gain_request(obs, geometry, p['candidate'], bound=p['common_bound_m_s'])
        shadow.append(dict(step=row['step'],request_scalar=request,**audit))
    cost = lambda rr: math.fsum(float(r['task']['velocity_error_m_s'])**2*p['policy_dt_s'] for r in rr)
    total = cost(rows)
    if total <= 0:
        raise ValueError('No nonzero native tracking cost to partition')
    active = [r['plan_projection']['decision_task_s'] for r in open_rows]
    return dict(condition=rows[0]['qualification_condition'],steps=len(rows),
        open_ticks=len(open_rows),closed_ticks=len(closed_rows),
        open_decision_first_s=min(active) if active else None,
        open_decision_last_s=max(active) if active else None,
        native_rmse_m_s=math.sqrt(total/(len(rows)*p['policy_dt_s'])),
        observed_open_cost_fraction=cost(open_rows)/total,
        observed_closed_cost_fraction=cost(closed_rows)/total,
        partition_is_not_counterfactual_or_benefit_bound=True,
        shadow_valid_ticks=sum(r['valid'] for r in shadow),
        shadow_is_not_new_controller_outcome=True),shadow


def analyze(output):
    from . import residual_ready_eval_only as evaluation
    from .residual_workflow import save
    p = specification()
    source_root = Path.home()/'nino_research/sim_ready_eval_only_v1'
    source = evaluation.validated_latest(source_root, check_runtime=False)
    if sha(source/'manifest.json') != SOURCE_MANIFEST:
        raise ValueError('Unexpected evaluation source')
    result = read(source/'evaluation_result.json')
    if result['comparison']['decision'] != 'no_go_expand_this_checkpoint_clear_known_stop':
        raise ValueError('Decision record input does not support closing this checkpoint')
    output = Path(output).expanduser().resolve()
    if source == output or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Derived artifact must be outside sealed raw and its ancestors')
    output.mkdir(parents=True, exist_ok=False)
    save(output/'specification.json',p)
    summaries=[];trace_pins={}
    for i in range(6):
        cell=source/f'eval_{i:02d}'
        rows=[json.loads(line) for line in (cell/'trace.jsonl').read_text().splitlines()]
        geometry=read(cell/'config.json')['config']['nominal_geometry']
        summary,shadow=summarize_trace(rows,geometry,p)
        expected=read(cell/'summary.json')['nominal_velocity_rmse_m_s']
        if not math.isclose(summary['native_rmse_m_s'],expected,abs_tol=1e-12,rel_tol=1e-9):
            raise ValueError('Native error partition does not reproduce frozen primary')
        summary['config_sha256']=sha(cell/'config.json')
        summaries.append(summary);trace_pins[str(cell/'trace.jsonl')]=sha(cell/'trace.jsonl')
        save(output/f'shadow_{i:02d}_not_outcome.json',shadow)
    report=dict(benchmark_id=BENCHMARK_ID,status='offline_decision_and_candidate_algebra_only',
        source_artifact=str(source),source_manifest_sha256=SOURCE_MANIFEST,trace_sha256=trace_pins,
        original_result_decision=result['comparison']['decision'],runs=summaries,
        ideal_authority=ideal_authority(p),decisions=p['decisions'],
        new_gazebo_launches=0,new_physics_steps=0,new_training_transitions=0,
        new_optimizer_updates=0,actor_loads=0,hardware_actions=0,
        proposed_baseline_qualification_launches=9,qualification_released=False,
        minimum_effect_proposed=p['proposed_relative_effect'],application_effect_accepted=None,
        real_data_cutoff='2026-11-02',benefit_verified=False)
    save(output/'decision.json',report)
    save(output/'manifest.json',dict(benchmark_id=BENCHMARK_ID,created_utc=datetime.now(timezone.utc).isoformat(),
        fingerprint=fingerprint(),files={f.name:sha(f) for f in output.iterdir() if f.is_file()}))
    return report


def verified_report(output):
    """Small read-only GUI check; heavy source/dependency audit is done by analyze."""
    output=Path(output);manifest=read(output/'manifest.json')
    if manifest['fingerprint'] != fingerprint():
        raise ValueError('Benchmark implementation/spec changed; report is historical')
    for name,value in manifest['files'].items():
        path=(output/name).resolve()
        if path.parent != output.resolve() or sha(path)!=value:
            raise ValueError('Derived benchmark artifact changed')
    r=read(output/'decision.json');source=Path(r['source_artifact'])
    if r['source_manifest_sha256'] != SOURCE_MANIFEST or sha(source/'manifest.json') != SOURCE_MANIFEST:
        raise ValueError('Source manifest changed')
    state=read(source.parent/'state.json')
    if (not state.get('runs') or state['latest'].get('sim-ready-eval-only')!=source.name
            or state['runs'][-1]['status']!='completed'):
        raise ValueError('Decision refers to a superseded or failed source')
    source_files=read(source/'manifest.json')['files']
    selected=['evaluation_result.json']+[f'eval_{i:02d}/{name}' for i in range(6)
                for name in ('config.json','summary.json','trace.jsonl')]
    for name in selected:
        if sha(source/name)!=source_files[name]:
            raise ValueError('Source decision input changed: '+name)
    for name,value in r['trace_sha256'].items():
        path=Path(name).resolve()
        if not path.is_relative_to(source.resolve()) or sha(path)!=value:
            raise ValueError('Source trace changed')
    return r


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report=analyze(args.output)
    print(json.dumps(dict(status=report['status'],output=str(args.output),physics=0,training=0),indent=2))


if __name__=='__main__':
    main()
