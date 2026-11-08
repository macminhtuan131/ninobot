"""Prepared evaluator correction; no CLI/job or additional physics release.

The frozen3072-step learner artifact is retained. This module corrects the
factory/namespace integration failure for a future evaluation-only protocol.
No learner updates, checkpoint selection, or replay resume are performed here.
"""
import hashlib
import numpy as np
from . import residual_reliable_td3 as frozen
from .reliable_episode import EpisodeLifecycle

configuration = frozen.configuration
protocol = frozen.protocol
contract = frozen.contract
baseline = frozen.baseline
timing = frozen.timing
qualified = frozen.qualified
feasibility = frozen.feasibility
require_identity = frozen.require_identity
save = frozen.save
append = frozen.append
emit = frozen.emit
ACTION = 'sim-reliable-evaluation-prepared'
EVALUATION_JOB_RELEASED = False

def actor_snapshot(actor):
    """Inference must leave learned/target parameters and update counters alone."""
    import torch
    digest = hashlib.sha256()
    for name, tensor in sorted(actor.policy.state_dict().items()):
        if not torch.isfinite(tensor).all():
            raise ValueError('Nonfinite evaluation policy')
        digest.update(name.encode());digest.update(tensor.detach().cpu().numpy().tobytes())
    return dict(policy_sha256=digest.hexdigest(), num_timesteps=actor.num_timesteps,
                critic_updates=actor._n_updates)


def evaluate_rollout(out, condition, world, checkpoints, *, evaluation_config=None,
                     evaluation_protocol=None, action_name=ACTION, verify_actor_unchanged=False):
    out.mkdir()
    c, g, task, backend_condition = evaluation_config or configuration(condition['source_stop_s'])
    p = evaluation_protocol or protocol()
    for name, value in [('config', c), ('guidance', g), ('task', task)]:
        save(out / (name + '.json'), value)
    actor = None
    if condition['arm'] == 'TD3':
        from stable_baselines3 import TD3
        actor = TD3.load(checkpoints[condition['seed']] / 'model.zip', device='cpu')
        require_identity(actor.nino_reliable_identity)
    actor_before = actor_snapshot(actor) if actor is not None and verify_actor_unchanged else None
    save(out / 'actor_before.json', actor_before)
    backend = EpisodeLifecycle(c, out / 'episodes', world, g, task, backend_condition, p)
    env = contract.environment(c, backend, task, backend_condition)
    rows, epoch = [], None
    error = None
    try:
        obs, info = env.reset(seed=701)
        save(out / 'reset.json', info)
        # Reject a wrong backend before any control interval, rather than after
        # stepping physics and constructing a trace with a missing namespace.
        namespace = backend.namespace
        if not namespace or backend.current is None:
            raise ValueError('Fresh lifecycle namespace required before evaluation step')
        for step in range(140):
            action = actor.predict(obs, deterministic=True)[0] if actor is not None else (
                contract.classical_request(obs) if condition['arm'] == 'Classical_scheduled' else np.zeros(1, np.float32))
            append(out / 'control_attempts.jsonl', dict(step=step, requested=np.asarray(action).tolist(), namespace=namespace))
            obs, reward, term, trunc, info = env.step(action)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc), **info,
                       qualification_condition=condition, episode_namespace=namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            append(out / 'trace.jsonl', row)
            epoch = epoch if epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            qualified.verify_transition(row, rows[-1] if rows else None, epoch, p['abi_sha256'])
            feasibility(row, p['native_boundary_support_s'])
            rows.append(row)
            if (step + 1) % 35 == 0:
                emit(action_name, out.name + f' {step + 1}/140')
            if term or trunc:
                break
    except BaseException as exc:
        error = exc
        save(out / 'rollout_failure.json', dict(error=repr(exc), valid_rows=len(rows), remaining_slots_closed=True))
        raise
    finally:
        try:
            env.close()
        except BaseException as exc:
            save(out / 'cleanup_failure.json', dict(error=repr(exc), original_error=repr(error) if error else None))
            if error is None:
                raise
    target = backend.directory / backend.namespace
    result = baseline.summarize(rows, target)
    diagnostic = timing.timestamp_diagnostic(target, rows)
    actor_after = actor_snapshot(actor) if actor_before is not None else None
    if actor_after != actor_before:
        raise ValueError('Evaluation modified actor/targets or learner counters')
    result.update(evaluation_condition=condition, timestamp_diagnostic=diagnostic,
                  maximum_native_boundary_support_age_s=max(max(r['source_lags_s'].values()) for r in rows),
                  actor_before=actor_before, actor_after=actor_after, optimizer_updates_in_job=0,
                  actor_inference_calls=len(rows) if actor is not None else 0)
    save(out / 'summary.json', result)
    if len(rows) != 140 or not result['functional_proposal_pass'] or not diagnostic['valid']:
        raise ValueError('Evaluation task/measurement failure; remaining slots closed')
    return result

