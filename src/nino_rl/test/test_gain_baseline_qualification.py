"""Exercise the actual nine-cell runner on a synthetic interface, never physics."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from nino_rl import gain_baseline_qualification as job


def lifecycle(monkeypatch, deny=False, map_fault=False):
    instances = []
    real_lifecycle = job.EpisodeLifecycle
    class Backend:
        residual_contract_id = real_lifecycle.residual_contract_id
        kind = 'synthetic_gain_one_interface_fixture'
        calibrated_to_hardware = False
        def __init__(self, c, directory, world, g, task, bc, lp, backend_factory=None):
            assert backend_factory.func is job.GainReadinessBackend
            assert backend_factory.keywords == dict(allow_physics=True)
            self.config, self.directory = c, directory
            directory.mkdir(parents=True)
            self.current = self.namespace = None
            self.closed = False
            self.calls = 0
            instances.append(self)
        def reset(self, seed=None):
            self.namespace = 'synthetic_episode_0'
            (self.directory/self.namespace).mkdir()
            c = deepcopy(self.config)
            c['backend'].update(wheel_gain=[1., 1.], motor_lag_s=[.16, .16], imu_noise_std=0.)
            self.current = job.preflight.fixture_backend(c)
            return self.current.reset(seed=seed)
        def view(self):
            result = deepcopy(self.current.last_view)
            if deny:
                result['permission'] = False
            return result
        def advance_reference(self, *args, **kwargs):
            self.calls += 1
            v, labels, term, trunc, info = self.current.advance_reference(*args, **kwargs)
            if map_fault:
                info['gain_map_audit']['map_calls_this_update'] = 2
            return v, labels, term, trunc, info
        def __getattr__(self, name):
            current = self.__dict__.get('current')
            if current is None:
                raise AttributeError(name)
            return getattr(current, name)
        def close(self):
            self.closed = True
            if self.current is not None:
                self.current.close()
    monkeypatch.setattr(job, 'EpisodeLifecycle', Backend)
    monkeypatch.setattr(job.parent.frozen.baseline, 'summarize', lambda rows, target: dict(
        steps=len(rows), functional_proposal_pass=True, nominal_velocity_rmse_m_s=.01, synthetic_summary=True))
    monkeypatch.setattr(job.parent.frozen.timing, 'timestamp_diagnostic', lambda *a: dict(valid=True,
        header_grid={'0.0': dict(rmse_m_s=.01), '0.01': dict(rmse_m_s=.01)}, synthetic_only=True))
    return instances


@pytest.mark.parametrize('arm', ['B0', 'Classical_scheduled', 'Causal_gain_candidate'])
def test_actual_evaluate_gain_one_full_wrapper_and_real_validator(tmp_path, monkeypatch, arm):
    instances = lifecycle(monkeypatch)
    condition = next(c for c in job.protocol()['evaluation_order'] if c['gain'] == 1. and c['arm'] == arm)
    result = job.evaluate(tmp_path/'eval', condition, 'synthetic_not_gazebo')
    rows = [json.loads(line) for line in (tmp_path/'eval/trace.jsonl').read_text().splitlines()]
    assert result['steps'] == instances[0].calls == len(rows) == 140
    assert instances[0].closed and rows[-1]['terminated'] and not rows[-1]['truncated']
    assert all(r['gain_context_identity'] == job.context.identity() for r in rows)
    assert result['actor_loads'] == result['optimizer_updates_in_job'] == 0


@pytest.mark.parametrize('deny,map_fault', [(True, False), (False, True)])
def test_failure_retains_attempt_and_closes_backend(tmp_path, monkeypatch, deny, map_fault):
    instances = lifecycle(monkeypatch, deny, map_fault)
    with pytest.raises(ValueError, match='Input not ready' if deny else 'applied more than once'):
        job.evaluate(tmp_path/'eval', job.protocol()['evaluation_order'][0], 'synthetic')
    assert instances[0].closed
    assert instances[0].calls == (0 if deny else 1)
    assert job.parent.read(tmp_path/'eval/failure.json')['valid_rows'] == 0
    assert (tmp_path/'eval/trace.jsonl').exists() is (not deny)


def test_foreign_condition_cannot_allocate_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(job, 'EpisodeLifecycle', lambda *a, **kw: pytest.fail('No backend'))
    with pytest.raises(ValueError, match='Undeclared'):
        job.evaluate(tmp_path/'eval', dict(arm='TD3', gain=1., source_stop_s=8.), 'none')
    assert not (tmp_path/'eval').exists()


def test_protocol_integration_inside_budget():
    p = job.protocol()
    assert len(p['evaluation_order']) == p['maximum_launches'] == 9
    assert [c['gain'] for c in p['evaluation_order']] == [1.]*3+[.98]*3+[1.02]*3
    assert p['maximum_eval_ticks'] == 9*140 == 1260
    assert all(p[k] == 0 for k in ('actor_loads', 'training_transitions', 'optimizer_updates', 'retries', 'extra_smokes', 'hardware_actions'))


def test_release_denial_never_consumes_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path/'home'))
    monkeypatch.setattr(job, 'release_record', lambda: dict(released=False))
    with pytest.raises(ValueError, match='not released'):
        job.run(tmp_path/'root')
    assert not (tmp_path/'root/state.json').exists()


def test_corrupt_ledger_cannot_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path/'home'))
    (tmp_path/'state.json').write_text('broken')
    monkeypatch.setattr(job, 'source', lambda *a: pytest.fail('Consumed first'))
    with pytest.raises(ValueError, match='already consumed'):
        job.run(tmp_path)


@pytest.mark.parametrize('cancel', [False, True])
def test_coordinator_failure_seals_and_prevents_retry(tmp_path, monkeypatch, cancel):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path/'home'))
    monkeypatch.setattr(job, 'release_ready', lambda root: dict(synthetic=True))
    monkeypatch.setattr(job, 'source', lambda *a: dict(synthetic=True))
    monkeypatch.setattr(job, 'fingerprint', lambda: 'synthetic')
    def fail(*a):
        raise KeyboardInterrupt() if cancel else RuntimeError('synthetic fault')
    monkeypatch.setattr(job, 'execute', fail)
    with pytest.raises(KeyboardInterrupt if cancel else RuntimeError):
        job.run(tmp_path/'root')
    state = job.parent.read(tmp_path/'root/state.json')
    row = state['runs'][0]
    assert state['latest'] == {}
    assert row['status'] == ('cancelled' if cancel else 'failed')
    assert job.parent.read(tmp_path/'root'/row['path']/'manifest.json')['status'] == row['status']
    with pytest.raises(ValueError, match='already consumed'):
        job.run(tmp_path/'root')


def test_matrix_stops_on_first_fault_no_unused_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(job.parent.frozen, 'prepare_worlds', lambda out: dict(clear_box='none'))
    calls = []
    def evaluate(out, condition, world):
        calls.append(condition)
        if len(calls) == 2:
            raise RuntimeError('synthetic matrix fault')
        return dict(steps=140)
    monkeypatch.setattr(job, 'evaluate', evaluate)
    with pytest.raises(RuntimeError):
        job.execute(tmp_path, {})
    progress = job.parent.read(tmp_path/'evaluation_progress.json')
    assert calls == job.protocol()['evaluation_order'][:2]
    assert progress['remaining_slots_closed'] and progress['unused_slots_closed'] == 7


@pytest.mark.parametrize('kind,expected', [
    ('better', 'descriptive_causal_candidate_separate_validation_required'),
    ('worse', 'retain_fixed_classical_no_learning_justified'),
    ('small', 'unknown_small_or_gain_dependent_effect'),
    ('grid', 'unknown_grid_sensitive'),
    ('zero', 'unknown_nonfinite_or_zero_denominator')])
def test_comparison_is_descriptive_preserves_primary_and_grids(kind, expected):
    runs = []
    for condition in job.protocol()['evaluation_order']:
        value = (.94 if kind == 'better' else 1.02 if kind == 'worse' else .98) if condition['arm'] == 'Causal_gain_candidate' else 1.
        gt = 1.02 if kind == 'grid' and condition['arm'] == 'Causal_gain_candidate' else value
        if kind == 'zero' and condition['arm'] == 'B0':
            value = 0.
        runs.append(dict(evaluation_condition=condition, nominal_velocity_rmse_m_s=value,
            timestamp_diagnostic=dict(header_grid={'0.0': dict(rmse_m_s=gt), '0.01': dict(rmse_m_s=gt)})))
    result = job.compare(runs)
    assert result['decision'] == expected and not result['benefit_verified']
