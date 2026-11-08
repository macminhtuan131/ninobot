"""Finite guided classical contact screen; frozen V3 parent, zero learning."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time
import numpy as np
from .core import load_config
from . import residual_guided_baseline as v3
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_experiment import source_fingerprint
from .residual_workflow import save, emit, json_value, latest, runtime_versions

ACTION = 'sim-guided-contact'
BASELINE_ROOT = Path.home()/'nino_research/sim_guided_baseline_v3'

def protocol():
    p = load_config(repo()/'src/nino_rl/config/residual_guided_contact_v1.yaml')
    expected = [('clear_box', 0), ('box_c1_6mm', 0), ('box_c1_6mm', 1), ('clear_box', 1)]
    actual = [(r['scenario'], r['repeat']) for r in p['order']]
    if actual != expected or any(r['arm']!='guided' or r['path_bearing_deg']!=0. for r in p['order']):
        raise ValueError('Contact screen conditions require a new versioned protocol')
    if (p['maximum_transitions'], p['training_transitions'], p['hardware_actions'], p['steps_per_rollout']) != (560, 0, 0, 140):
        raise ValueError('Contact screen fixed budget mismatch')
    parent = v3.protocol()
    for key in ['horizon_s', 'command_until_s', 'warmup_s', 'path_length_m', 'initial_pose_m_rad', 'estimator', 'functional_proposals']:
        if p[key] != parent[key]:
            raise ValueError('Contact screen changed frozen V3 setting '+key)
    if p['stop_on_functional_gate_failure'] is not True:
        raise ValueError('Do not continue after a functional gate failure')
    return p

def fingerprint():
    paths = [Path(__file__), repo()/'src/nino_rl/config/residual_guided_contact_v1.yaml',
             repo()/'src/nino_rl/scripts/residual_guided_contact.sh']
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=files, frozen_v3_parent=v3.fingerprint()), sort_keys=True).encode()).hexdigest()

def dependency():
    path = v3.validated_latest(BASELINE_ROOT)
    if not json.loads((path/'evaluation_result.json').read_text())['baseline_functional_candidate']:
        raise ValueError('Guided clear-floor baseline has not passed its proposed gate')
    return dict(path=str(path), manifest_sha256=hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest())

def rollout(out, p, condition, world):
    out.mkdir()
    c, g = v3.configuration(condition, p)
    c['backend']['scenario_id'] = condition['scenario']+'_guided_contact_v1'
    save(out/'config.json', c); save(out/'guidance_config.json', g)
    backend = v3.GuidedBackend(c, out/'backend', world, g, p, condition)
    env = v3.environment(c, backend, p, condition)
    rows = []
    try:
        _, reset = env.reset(seed=701); save(out/'reset.json', reset)
        for step in range(p['steps_per_rollout']):
            _, reward, term, trunc, info = env.step(np.zeros(2, dtype=np.float32))
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, **info)
            rows.append(row)
            with (out/'trace.jsonl').open('a') as stream:
                stream.write(json.dumps(row, default=json_value, allow_nan=False)+'\n')
            if (step+1)%35 == 0:
                emit(ACTION, out.name+' '+str(step+1)+'/140')
            if term or trunc:
                break
    finally:
        env.close()
    summary = v3.summarize(rows, out)
    save(out/'summary.json', summary)
    return summary

def evaluate(out, p):
    worlds = prepare_worlds(out)
    runs = []
    for index, condition in enumerate(p['order']):
        emit(ACTION, str(index+1)+'/4 · '+condition['scenario'], index/4)
        name = condition['scenario']+'_'+str(condition['repeat'])
        r = rollout(out/name, p, condition, worlds[condition['scenario']])
        runs.append(r); save(out/'evaluation_progress.json', runs)
        if r['physical_failure'] or r['guidance_faults'] or r['steps'] != 140:
            raise RuntimeError('Source/guidance/physics failure; retain job, no retry')
        if not r['functional_proposal_pass']:
            break
    complete = len(runs) == 4
    passed = complete and all(r['functional_proposal_pass'] for r in runs)
    result = dict(protocol_id=p['protocol_id'], runs=runs, planned_runs=4, completed_runs=len(runs),
        closed_unused_slots=4-len(runs), baseline_functional_candidate=bool(passed),
        closure_reason='planned_screen_complete' if complete else 'functional_gate_failure_remaining_slots_closed',
        evaluation_transitions=sum(r['steps'] for r in runs), training_transitions=0, optimizer_updates=0,
        actor_loaded=False, truth_used_for_guidance=False, guidance_connected_to_gazebo=True,
        hardware_authorized=False, calibrated_to_hardware=False, benefit_verified=False,
        conclusion='Classical baseline contact diagnostic; not learning benefit, loaded-contact proof or hardware validation.')
    save(out/'evaluation_result.json', result)
    return result

def validated_latest(root, check_runtime=True):
    path = latest(root, ACTION, check_runtime=check_runtime)
    if json.loads((path/'manifest.json').read_text()).get('contact_fingerprint') != fingerprint():
        raise ValueError('Contact screen source/protocol changed; artifact historical')
    saved = json.loads((path/'dependencies.json').read_text())
    parent = v3.validated_latest(BASELINE_ROOT, check_runtime=check_runtime)
    if saved != dict(path=str(parent), manifest_sha256=hashlib.sha256((parent/'manifest.json').read_bytes()).hexdigest()):
        raise ValueError('Guided clear baseline dependency changed')
    return path

def run(root):
    root = Path(root).expanduser().resolve(); root.mkdir(parents=True, exist_ok=True)
    shared = Path.home()/'nino_research/.factory_sim.lock'; shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root/'.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'state.json').exists():
            raise ValueError('Contact screen batch already closed; do not reuse slots')
        p, dep = protocol(), dependency()
        out = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION); out.mkdir()
        save(out/'protocol.json', p); save(out/'dependencies.json', dep)
        current, start, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):
            raise TimeoutError('Contact screen finite wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout); signal.alarm(p['wall_deadline_s'])
        emit(ACTION, 'Start guided zero-residual contact screen', 0., directory=str(out))
        try:
            result = evaluate(out, p)
            if fingerprint() != current:
                raise ValueError('Contact screen sources changed during run')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc); raise
        finally:
            signal.alarm(0); signal.signal(signal.SIGALRM, previous)
            save(out/'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic()-start, hardware_actions=0))
            save(out/'manifest.json', dict(action=ACTION, status=status, contact_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest()
                       for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            save(root/'state.json', dict(schema_version=1, latest={ACTION:out.name} if status=='completed' else {},
                runs=[dict(action=ACTION, path=out.name, status=status, error=error)]))
            emit(ACTION, status, 1. if status=='completed' else None, directory=str(out), result=result, error=error)
    return out

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Contact screen failed/retained:', exc, flush=True); return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
