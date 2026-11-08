"""Real filesystem retention and GUI close lifecycle, with tiny synthetic jobs."""
import fcntl
import json
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from nino_pi import training_storage as storage


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    root = tmp_path / 'studio' / 'completed'
    root.mkdir(parents=True)
    save(root / 'job.json', dict(status='completed', hardware_actions=0, request=dict(mode='train')))
    for step, reason in [(5000, 'periodic'), (20000, 'final')]:
        folder = root / 'checkpoints' / f'step_{step}_{reason}'
        for name in ('model.zip', 'replay_buffer.pkl', 'resume_identity.json'):
            save(folder / name, dict(fixture=name))
        save(folder / 'checkpoint.json', dict(global_steps=step, reason=reason))
        save(folder / 'manifest.json', dict(kind='nino_common_studio_checkpoint_v1', status='resumable',
             files={p.name: storage.digest(p) for p in folder.iterdir()}))
    final = root / 'checkpoints/step_20000_final'
    save(root / 'training_result.json', dict(checkpoint=str(final), transitions=140,
         starting_global_steps=0, global_steps=140, optimizer_updates_this_job=0,
         final_segment_right_censored=False))
    (root / 'environment_trace.jsonl').write_text('')
    (root / 'training_trace.jsonl').write_text('')
    save(root / 'episodes/lifecycle.json', dict(status='closed'))
    save(root / 'episode_0_reset.json', dict(reset=True))
    save(root / 'episodes/episode_0/backend/raw.jsonl', dict(raw=True))
    save(root / 'episodes/episode_0/independent/source.jsonl', dict(raw=True))
    save(root / 'evaluation/stop6/raw.jsonl', dict(evaluation=True))
    save(root / 'tensorboard/events.fixture', dict(events=True))
    save(root / 'manifest.json', dict(kind='nino_common_studio_job_v1', status='completed', hardware_actions=0,
         files={str(p.relative_to(root)): storage.digest(p) for p in root.rglob('*') if p.is_file()}))
    return root


def test_preview_then_apply_preserves_checkpoints_eval_and_dashboard_inputs(job):
    before = {str(p.relative_to(job)): storage.digest(p) for p in job.rglob('*') if p.is_file()}
    preview = storage.prune_completed_job(job)
    assert preview['status'] == 'preview' and preview['removed_episode_count'] == 1
    assert not (job / storage.RECEIPT).exists()
    receipt = storage.prune_completed_job(job, apply=True)
    assert receipt['status'] == 'completed' and receipt['removed_file_count'] == 2
    assert not (job / 'episodes/episode_0').exists()
    for name, sha in before.items():
        if not name.startswith('episodes/episode_0/'):
            assert storage.digest(job / name) == sha
    assert receipt['removed_bytes'] == preview['planned_bytes']
    assert storage.prune_completed_job(job, apply=True)['already_pruned']


@pytest.mark.parametrize('name', ['job.json', 'training_result.json', 'environment_trace.jsonl',
                                 'checkpoints/step_20000_final/replay_buffer.pkl'])
def test_corrupt_retained_input_blocks_every_deletion(job, name):
    with (job / name).open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='Hash mismatch'):
        storage.prune_completed_job(job, apply=True)
    assert (job / 'episodes/episode_0/backend/raw.jsonl').is_file()
    assert not (job / storage.RECEIPT).exists()


def test_explicit_periodic_pruning_and_final_protection(job):
    with pytest.raises(ValueError, match='final/result'):
        storage.prune_completed_job(job, apply=True, drop_checkpoint_steps=[20000])
    result = storage.prune_completed_job(job, apply=True, drop_checkpoint_steps=[5000])
    assert result['dropped_checkpoint_steps'] == [5000]
    assert not (job / 'checkpoints/step_5000_periodic').exists()
    assert (job / 'checkpoints/step_20000_final/replay_buffer.pkl').is_file()


def test_unknown_checkpoint_step_refused_before_deletion(job):
    with pytest.raises(ValueError, match='step not found'):
        storage.prune_completed_job(job, apply=True, drop_checkpoint_steps=[12345])
    assert (job / 'episodes/episode_0/backend/raw.jsonl').is_file()
    assert not (job / storage.RECEIPT).exists()


@pytest.mark.parametrize('status', ['running', 'failed', 'cancelled'])
def test_not_completed_job_refused(job, status):
    manifest = json.loads((job / 'manifest.json').read_text())
    manifest['status'] = status
    save(job / 'manifest.json', manifest)
    with pytest.raises(ValueError, match='completed'):
        storage.prune_completed_job(job, apply=True)
    assert (job / 'episodes/episode_0/backend/raw.jsonl').exists()


def test_simulation_lock_blocks_cleanup(job):
    lock = Path.home() / 'nino_research/.factory_sim.lock'
    lock.parent.mkdir(parents=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='worker is active'):
            storage.prune_completed_job(job, apply=True)


def test_symlinks_and_unsealed_files_refused(job):
    outside = job.parent / 'real_data.json'
    outside.write_text('keep')
    link = job / 'episodes/episode_0/extra'
    link.symlink_to(outside)
    with pytest.raises(ValueError, match='Symlink'):
        storage.prune_completed_job(job, apply=True)
    assert outside.read_text() == 'keep'
    link.unlink()
    link.write_text('not sealed')
    with pytest.raises(ValueError, match='Unsealed'):
        storage.prune_completed_job(job, apply=True)


def test_original_manifest_and_receipt_mismatch_blocks_new_cleanup(job):
    storage.prune_completed_job(job, apply=True)
    with (job / 'manifest.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='receipt needs review'):
        storage.prune_completed_job(job, apply=True)


def test_gui_finished_job_cleanup_is_background_and_keeps_checkpoint(job):
    from PyQt5 import QtWidgets as Q, QtTest
    from nino_pi.td3_training_panel import TD3TrainingPanel
    q = Q.QApplication.instance() or Q.QApplication([])
    panel = TD3TrainingPanel(root=job.parent, observe_external=False)
    panel.dashboard.auto_laya.setChecked(False)
    assert panel.auto_cleanup.isChecked()
    panel.cleanup_requested = True
    panel.handle(dict(directory=str(job), closed=True, returncode=0))
    assert panel.cleanup_worker is not None and panel.active
    for _ in range(200):
        q.processEvents()
        QtTest.QTest.qWait(5)
        if panel.cleanup_worker is None:
            break
    assert not panel.active and 'GiB' in panel.status.text()
    assert (job / storage.RECEIPT).is_file()
    assert (job / 'checkpoints/step_20000_final/model.zip').is_file()
    assert not panel.runner.busy
    panel.close()
    q.processEvents()


def test_gui_failed_job_keeps_raw_even_when_auto_cleanup_selected(job):
    from PyQt5 import QtWidgets as Q
    from nino_pi.td3_training_panel import TD3TrainingPanel
    q = Q.QApplication.instance() or Q.QApplication([])
    panel = TD3TrainingPanel(root=job.parent, observe_external=False)
    panel.dashboard.auto_laya.setChecked(False)
    panel.cleanup_requested = True
    panel.handle(dict(directory=str(job), closed=True, returncode=1))
    assert panel.cleanup_worker is None
    assert not (job / storage.RECEIPT).exists()
    assert (job / 'episodes/episode_0/backend/raw.jsonl').is_file()
    panel.close()
    q.processEvents()
