"""Read-only discovery, incremental logs, resume counters and GUI ownership.

Fixtures model an external worker; no ROS, Gazebo, optimizer or signals.
"""
import json
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PyQt5 import QtWidgets as Q
from nino_pi import training_live as live


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))


def event(**fields):
    return live.PREFIX+json.dumps(dict(action='td3-common-studio',**fields))+'\n'


@pytest.fixture
def fixture(tmp_path):
    root=tmp_path/'output';directory=root/'run';proc=tmp_path/'proc';process=proc/'1234'
    (process/'fd').mkdir(parents=True)
    (process/'stat').write_text('1234 (fake worker) S '+'0 '*18+'123456 0')
    checkpoint=tmp_path/'parent';write(checkpoint/'checkpoint.json',dict(global_steps=20000,optimizer_updates=10000))
    request=dict(schema_version=2,engine='common103_v1',timesteps=10000,resume=str(checkpoint))
    request_path=tmp_path/'request.json';write(request_path,request)
    (process/'cmdline').write_bytes(b'\0'.join(s.encode() for s in [
        '/python','-m','nino_rl.training_studio_api','--request',str(request_path),'--output',str(root)])+b'\0')
    write(directory/'job.json',dict(status='running',request=live.normalized(request)))
    log=tmp_path/'stdout.log';log.write_text(event(directory=str(directory),phase='prepare'))
    (process/'fd/1').symlink_to(log)
    return dict(root=root,directory=directory,proc=proc,process=process,log=log,request=request)


def reader(f):
    return live.LiveJob(live.discover(proc=f['proc'])[0])


def test_discover_exact_module_root_and_normalized_request(fixture):
    f=fixture;workers=live.discover(proc=f['proc'])
    assert len(workers)==1 and workers[0]['directory']==str(f['directory'])
    assert live.alive(workers[0])
    assert live.discover([f['root']/'other'],proc=f['proc'])==[]
    assert len(live.discover([f['root']],proc=f['proc']))==1
    command=(f['process']/'cmdline').read_bytes()
    (f['process']/'cmdline').write_bytes(command.replace(b'nino_rl.training_studio_api',b'unrelated.module'))
    assert live.discover(proc=f['proc'])==[]


def test_no_ambiguous_attribution_without_stdout(fixture):
    f=fixture;(f['process']/'fd/1').unlink()
    assert len(live.discover(proc=f['proc']))==1
    write(f['root']/'other/job.json',dict(status='running',request=live.normalized(f['request'])))
    assert live.discover(proc=f['proc'])==[]


def test_resume_additional_progress_partial_tail_and_rotation(fixture):
    f=fixture;r=reader(f);assert r.poll()['global_steps']==20000
    line=event(global_steps=23000,phase='train',message='Common103 train 3000/10000 · critic 12999')
    with f['log'].open('a') as stream:stream.write(line[:-1])
    assert r.poll()['additional_steps']==0  # incomplete JSON line retained
    with f['log'].open('a') as stream:stream.write('\n')
    s=r.poll()
    assert s['global_steps']==23000 and s['additional_steps']==3000 and s['progress']==.3
    assert s['critic_updates']==12999 and s['critic_count_is_logged'] and s['actor_updates'] is None
    assert r.poll()['log_lines']==[]
    replacement=f['log'].with_suffix('.replacement')
    replacement.write_text(event(global_steps=24000,phase='train',message='rotated'))
    replacement.replace(f['log'])
    assert r.poll()['additional_steps']==4000


def test_coverage_and_transient_json_do_not_unlock_or_erase(fixture):
    f=fixture;r=reader(f);write(f['directory']/'coverage.json',dict(total=1500))
    assert r.poll()['additional_steps']==1500
    (f['directory']/'job.json').write_text('{')
    (f['directory']/'coverage.json').write_text('{')
    s=r.poll();assert s['status']=='running' and s['additional_steps']==1500
    (f['process']/'cmdline').write_bytes(b'')
    assert r.poll()['status']=='worker_missing'


def test_evaluation_final_checkpoint_and_pid_reuse(fixture):
    f=fixture;r=reader(f)
    write(f['directory']/'training_result.json',dict(global_steps=30000,
        optimizer_updates_total=20000,actor_updates_total=10000))
    write(f['directory']/'evaluation_progress.json',[dict(arm='B0')])
    for name in ('step_000000025000_periodic','.pending_final','incomplete'):
        write(f['directory']/'checkpoints'/name/'checkpoint.json',{})
        if name!='incomplete':write(f['directory']/'checkpoints'/name/'manifest.json',{})
    s=r.poll()
    assert s['phase']=='evaluate' and s['progress']==1 and s['evaluation_runs']==1
    assert len(s['checkpoints'])==1 and '025000' in s['checkpoints'][0]
    assert s['critic_updates']==20000 and s['actor_updates']==10000 and not s['critic_count_is_logged']
    (f['process']/'stat').write_text('1234 (different process) S '+'0 '*18+'999999 0')
    assert not live.alive(r.worker) and r.poll()['status']=='worker_missing'
    write(f['directory']/'job.json',dict(status='completed'))
    write(f['directory']/'result.json',dict(global_steps=30000,optimizer_updates_total=20000))
    assert r.poll()['status']=='completed' and r.poll()['final_result']


def test_external_GUI_attach_locks_launch_and_close_never_signals(fixture,monkeypatch):
    from nino_pi.td3_training_panel import TD3TrainingPanel
    f=fixture;workers=live.discover(proc=f['proc']);calls=[]
    monkeypatch.setattr(live,'discover',lambda roots=None:workers)
    q=Q.QApplication.instance() or Q.QApplication([])
    p=TD3TrainingPanel(root=f['root']);p.live_timer.stop()
    monkeypatch.setattr(p.runner,'start',lambda *args:calls.append('start'))
    monkeypatch.setattr(p.runner,'cancel',lambda:calls.append('cancel'))
    p.poll_live()
    assert p.busy and not p.active and not p.train.isEnabled() and not p.stop.isEnabled()
    assert p.runner.process is None and p.current_directory==f['directory']
    assert p.timesteps.value()==10000 and p.resume.isChecked()
    assert p.resume_info['global_steps']==20000
    with f['log'].open('a') as stream:stream.write(event(global_steps=22500,message='live fixture'))
    p.poll_live()
    assert p.progress.value()==25 and '22,500' in p.live_metrics.text()
    assert 'live fixture' in p.log.toPlainText()
    p.start('train');assert calls==[]
    p.close();q.processEvents()
    assert p.watch_closed and not p.live_timer.isActive() and calls==[]
    assert live.alive(workers[0])


def test_button_finds_new_worker_after_completed_job(fixture,monkeypatch):
    from nino_pi.td3_training_panel import TD3TrainingPanel
    f=fixture;workers=live.discover(proc=f['proc'])
    monkeypatch.setattr(live,'discover',lambda roots=None:workers)
    q=Q.QApplication.instance() or Q.QApplication([])
    p=TD3TrainingPanel(root=f['root']);p.live_timer.stop();p.poll_live()
    write(f['directory']/'job.json',dict(status='failed',error='fixture failure'))
    p.poll_live();assert not p.external_running and 'fixture failure' in p.log.toPlainText()
    workers.clear();p.find_live()
    assert p.live_reader is None and 'Chưa tìm thấy' in p.live_note.text()
    p.close();q.processEvents()
