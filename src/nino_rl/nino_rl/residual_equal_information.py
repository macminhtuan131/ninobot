"""Finite offline qualification for a103D/1D common-only TD3/classical contract.

Synthetic reduced-order traces and checkpoint/replay roundtrip only. This job
never calls learn(), optimizer.step(), Gazebo, ROS, SSH or hardware interfaces.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
from . import equal_information_contract as contract
from .residual_workflow import emit, json_value, latest, runtime_versions, save
from .residual_experiment import source_fingerprint

ACTION = 'sim-equal-contract'
PARENT_ROOT = Path.home() / 'nino_research/sim_stop_transfer_v1'


def parent(check_runtime=True):
    out = contract.parent.validated_latest(PARENT_ROOT, check_runtime=check_runtime)
    result = json.loads((out / 'evaluation_result.json').read_text())
    if not result['descriptive_transfer_signal'] or result['evaluation_transitions'] != 840:
        raise ValueError('Stop-transfer prerequisite has no closed descriptive signal')
    return out


def zero_initialize_scalar(model):
    import torch
    from torch import nn
    if model.num_timesteps or model._n_updates or getattr(model, 'nino_scalar_zero_initialized', False) or model.actor.optimizer.state or model.critic.optimizer.state:
        raise ValueError('Only a fresh untrained scalar model can be zero-initialized')
    layers = list(model.actor.mu.children())
    if not isinstance(layers[-1], nn.Tanh) or not isinstance(layers[-2], nn.Linear) or layers[-2].out_features != 1:
        raise ValueError('New scalar1D head required; no conversion of V3 two-output heads')
    with torch.no_grad():
        layers[-2].weight.zero_()
        layers[-2].bias.zero_()
        model.actor_target.load_state_dict(model.actor.state_dict())
    model.nino_scalar_zero_initialized = True


def inspection_model():
    """A small untrained object to qualify the ABI; not a research training profile."""
    import gymnasium as gym
    from stable_baselines3 import TD3
    class NoCollection(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., (103,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
        def reset(self, **kwargs):
            raise RuntimeError('Offline inspection model cannot collect training transitions')
        def step(self, action):
            raise RuntimeError('Offline inspection model cannot step a plant')
    model = TD3('MlpPolicy', NoCollection(), seed=7, policy_kwargs=dict(net_arch=[32, 32]),
                learning_starts=10000, buffer_size=512, batch_size=32, device='cpu')
    zero_initialize_scalar(model)
    model.nino_equal_information_identity = contract.identity()
    model.nino_purpose = 'offline_untrained_inspection_only'
    return model


def fixture_backend(config, source_stop_s):
    from .velocity_backend import VelocityBackend
    class OfflineFixture(VelocityBackend):
        kind = 'equal_information_synthetic_software_fixture'
        def reference(self):
            t = self.time
            return (self.speed if .5 - 1e-8 <= t < source_stop_s - 1e-8 else 0., 0.)
        def advance_reference(self, *args):
            view, labels, term, trunc, info = super().advance_reference(*args)
            info.update(body_speed_norm_m_s=abs(info['body_speed_m_s']),
                estimator_audit=dict(pose=info['truth_pose_m_rad'],
                    evidence='Synthetic evaluation label only, no guidance/actor input or estimator validation'),
                fixture_only=True, physical_benefit_evaluation=False)
            return view, labels, term, trunc, info
    return OfflineFixture(config)


def qualify(out):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.buffers import ReplayBuffer
    torch.set_num_threads(1)
    p = contract.protocol()
    save(out / 'dependencies.json', contract.guided.dependency_record(parent()))
    ident = contract.identity()
    save(out / 'identity.json', ident)
    model = inspection_model()
    before = {name: {k: v.detach().clone() for k, v in getattr(model, name).state_dict().items()}
              for name in ('actor', 'actor_target', 'critic', 'critic_target')}
    samples = np.random.default_rng(97).uniform(-5, 5, (32, 103)).astype(np.float32)
    assert not np.any(model.predict(samples, deterministic=True)[0])
    replay = ReplayBuffer(512, model.observation_space, model.action_space, device='cpu', handle_timeout_termination=True)
    replay_rows = []
    summaries = []
    for stop in p['development_source_stops_s']:
        for arm in p['offline_fixture_arms']:
            c, _, task, condition = contract.configuration(stop)
            c['backend'].update(kind='equal_information_synthetic_software_fixture', imu_noise_std=0.)
            env = contract.environment(c, fixture_backend(c, stop), task, condition)
            path = out / (arm + '_stop' + str(int(stop)) + '.jsonl')
            active = 0
            blocked_nonzero = 0
            rows = []
            try:
                obs, reset = env.reset(seed=701)
                for i in range(p['offline_fixture_steps_per_run']):
                    if arm == 'B0':
                        request = np.zeros(1, np.float32)
                    elif arm == 'Classical_scheduled':
                        request = contract.classical_request(obs)
                    else:
                        request = np.array([(-1., 0., 1.)[i % 3]], np.float32)
                    next_obs, reward, term, trunc, info = env.step(request)
                    row = dict(step=i, source_stop_s=stop, arm=arm, reward=reward, done=bool(term or trunc),
                               terminated=term, truncated=trunc, **info)
                    row['TimeLimit.truncated'] = bool(trunc and not term)
                    rows.append(row)
                    with path.open('a') as stream:
                        stream.write(json.dumps(row, allow_nan=False, default=json_value) + '\n')
                    audit = info['plan_projection']
                    active += int(audit['window_open'])
                    blocked_nonzero += int(not audit['window_open'] and request[0] != 0.)
                    if not audit['window_open']:
                        assert info['controller_proposal'] == [0., 0.]
                    assert info['controller_proposal'][1] == 0.
                    assert max(abs(v) for v in info['controller_proposal']) <= .125
                    if arm == 'Proposal_probe':
                        replay.add(obs, next_obs, request, np.array([reward]), np.array([term or trunc]), [row])
                        replay_rows.append(row)
                    obs = next_obs
                    if term or trunc:
                        break
            finally:
                env.close()
            if len(rows) != 140 or not rows[-1]['terminated'] or rows[-1]['truncated']:
                raise ValueError('Fixture task terminal must be fixed-deadline, not timeout bootstrap')
            # This synthetic source changes exactly at decision0.5s. Historical
            # Gazebo views first exposed motion one tick later; no fabricated
            # delay is added here to force matching active counts across backends.
            expected_active = 31 if stop == 6. else 51
            if active != expected_active:
                raise ValueError('Shared steady/withdrawal window differs from frozen rule')
            if arm == 'Proposal_probe' and not blocked_nonzero:
                raise ValueError('Fixture must retain nonzero requested actions during closed window')
            summaries.append(dict(arm=arm, source_stop_s=stop, fixture_steps=len(rows), open_window_ticks=active,
                                  closed_window_nonzero_requests=blocked_nonzero,
                                  nominal_scorer_parity=True, physical_metrics_not_evaluated=True))
            emit(ACTION, f'Offline fixture {len(summaries)}/6 · {arm} stop{stop:g}s', len(summaries) / 8)
    replay_audit = contract.audit_replay(replay, replay_rows)
    import pickle
    with (out / 'synthetic_replay_do_not_train.pkl').open('wb') as stream:
        pickle.dump(replay, stream)
    with (out / 'synthetic_replay_do_not_train.pkl').open('rb') as stream:
        contract.audit_replay(pickle.load(stream), replay_rows)
    model.save(out / 'inspection_model_untrained.zip')
    loaded = TD3.load(out / 'inspection_model_untrained.zip', device='cpu')
    contract.require_identity(loaded.nino_equal_information_identity, ident)
    np.testing.assert_array_equal(model.predict(samples, deterministic=True)[0], loaded.predict(samples, deterministic=True)[0])
    for name, parameters in before.items():
        for key, value in parameters.items():
            assert torch.equal(value, getattr(model, name).state_dict()[key])
            assert torch.equal(value, getattr(loaded, name).state_dict()[key])
    assert model.num_timesteps == loaded.num_timesteps == 0
    assert model._n_updates == loaded._n_updates == 0
    assert not model.actor.optimizer.state and not model.critic.optimizer.state
    assert not loaded.actor.optimizer.state and not loaded.critic.optimizer.state
    result = dict(contract_id=contract.CONTRACT_ID, abi_sha256=ident['abi_sha256'], observation_size=103, action_size=1,
        evidence_level='offline_synthetic_software_qualification_only',
        fixture_runs=summaries, synthetic_fixture_transitions=sum(r['fixture_steps'] for r in summaries),
        replay=replay_audit, requested_vs_windowed_vs_accepted_separate=True,
        zero_head_and_target_verified=True, save_load_model_targets_critics_verified=True,
        optimizer_states_empty=True, learned_parameters_unchanged=True,
        training_transitions=0, optimizer_updates=0, gazebo_runs=0, physics_steps=0, hardware_actions=0,
        old_checkpoint_compatible=False, training_released=False, benefit_verified=False,
        minimum_worthwhile_effect=None, release_blockers=[
            'remaining_gap_hypothesis_not_demonstrated', 'minimum_worthwhile_effect_unaccepted',
            'training_seed_timestep_budget_unallocated', 'independent_test_conditions_and_budget_unsealed',
            'new_wrapper_not_yet_qualified_in_Gazebo'],
        conclusion='103D/1D contract and software dataflow qualified, no optimizer/physical or learned benefit evidence')
    save(out / 'qualification.json', result)
    return result


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if json.loads((out / 'manifest.json').read_text()).get('equal_information_fingerprint') != contract.fingerprint():
        raise ValueError('Equal-information source/config changed; historical artifact')
    contract.require_identity(json.loads((out / 'identity.json').read_text()))
    if json.loads((out / 'dependencies.json').read_text()) != contract.guided.dependency_record(parent(check_runtime)):
        raise ValueError('Frozen stop-transfer dependency changed')
    return out


def run(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.job.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'state.json').exists():
            raise ValueError('Offline equal-information batch already consumed; retain failure, no retry')
        p = contract.protocol()
        parent()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION)
        out.mkdir()
        ledger = dict(schema_version=1, latest={}, runs=[dict(action=ACTION, path=out.name, status='running', error=None)])
        save(root / 'state.json', ledger)
        save(out / 'protocol.json', p)
        current, started, status, error, result = contract.fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):
            raise TimeoutError('Offline qualification wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(p['wall_deadline_s'])
        try:
            result = qualify(out)
            if contract.fingerprint() != current:
                raise ValueError('Source changed during offline qualification')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic() - started,
                                      hardware_actions=0, physics_steps=0, optimizer_updates=0))
            save(out / 'manifest.json', dict(action=ACTION, status=status, equal_information_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.name != 'manifest.json'}))
            ledger['runs'][0].update(status=status, error=error)
            if status == 'completed':
                ledger['latest'][ACTION] = out.name
            save(root / 'state.json', ledger)
            emit(ACTION, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Equal-information qualification failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
