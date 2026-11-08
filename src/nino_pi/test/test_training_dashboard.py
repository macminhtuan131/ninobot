"""Map coordinates, episode/censor semantics and read-only dashboard lifecycle."""
import json
import math
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5 import QtWidgets as Q,QtTest
from nino_pi.training_dashboard_data import DashboardReader,world_geometry,laya_summary
from nino_pi.training_dashboard import TrainingDashboard


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def fixture(root):
    save(root/'request.json',dict(scenario='clear_box',resume=str(root/'parent')))
    save(root/'parent/checkpoint.json',dict(global_steps=20000))
    save(root/'job.json',dict(status='running'))
    (root/'clear_box.sdf').write_text('''<sdf><world name="test"><model name="hall">
      <pose>1 2 0 0 0 1.5707963267948966</pose><link name="walls">
      <collision name="wall"><pose>1 0 0 0 0 0</pose><geometry><box><size>2 .2 2</size></box></geometry></collision>
      <visual name="wall_visual"><geometry><box><size>2 .2 2</size></box></geometry></visual>
      </link></model><model name="cable"><link name="l"><collision name="bump">
      <pose>0 0 .003 1.5707963267948966 0 0</pose><geometry><cylinder><radius>.003</radius><length>1</length></cylinder></geometry>
      </collision></link></model></world></sdf>''')
    save(root/'episode_0_reset.json',dict(reset=dict(guidance_contract=dict(configuration=dict(path_points_m=[[0,0],[3,0]])))))
    return root


def row(episode,step,done=False,error=.003):
    return dict(episode=episode,step=step,done=done,reward=-1.,truth_pose_m_rad=[step*.1,episode,math.pi/2],
        estimator_audit=dict(pose=[step*.1+.01,episode,0]),termination_reason='task_success' if done else None,
        task=dict(elapsed_s=(step+1)*.1,velocity_error_m_s=error,cross_track_m=.002,
                  task_success=True,stop_completed=True),qualification_condition=dict(source_stop_s=6))


def append(path,rows):
    with path.open('a') as h:
        for r in rows:h.write(json.dumps(r)+'\n')


def test_collision_geometry_composed_transforms_and_horizontal_cylinder(tmp_path):
    root=fixture(tmp_path);g=world_geometry(root,'clear_box')
    assert len(g['shapes'])==2  # collision preferred, no visual duplicates
    wall=g['shapes'][0];xs=[p[0] for p in wall['polygon']];ys=[p[1] for p in wall['polygon']]
    assert abs(sum(xs)/len(xs)-1)<1e-8 and abs(sum(ys)/len(ys)-3)<1e-8
    cylinder=g['shapes'][1]['polygon']
    assert max(p[1] for p in cylinder)-min(p[1] for p in cylinder)==1
    assert abs(max(p[0] for p in cylinder)-.003)<1e-8
    save(root/'worlds.json',dict(clear_box=dict(path=str(root/'clear_box.sdf'),sha256='wrong')))
    assert world_geometry(root,'clear_box')['shapes']==[]


def test_incremental_episode_RMS_return_resume_and_reset_path(tmp_path):
    root=fixture(tmp_path);trace=root/'environment_trace.jsonl'
    append(trace,[row(0,0,error=.003),row(0,1,True,error=.004),row(1,0)])
    r=DashboardReader(root);s=r.poll()
    assert len(s['episodes'])==2 and s['trace_rows']==3
    a,b=s['episodes'];assert a['end_step']==20002 and a['reward']==-2.
    assert abs(a['metrics']['velocity_error_m_s']-math.sqrt((.003**2+.004**2)/2))<1e-12
    assert b['status']=='running' and b['task_success'] is None
    assert len(s['truth_path'])==1 and s['truth_path'][0][1]==1
    assert s['window']['episodes']==1 and len(laya_summary(s))==1
    assert r.poll()['trace_rows']==3  # no duplicate reads
    append(trace,[row(1,1,True)]);s=r.poll();assert s['window']['episodes']==2


def test_partial_line_missing_metrics_and_right_censor(tmp_path):
    root=fixture(tmp_path);trace=root/'environment_trace.jsonl';a=row(0,0);a['task'].pop('cross_track_m')
    with trace.open('w') as h:h.write(json.dumps(a)[:-1])
    r=DashboardReader(root);assert r.poll()['trace_rows']==0
    with trace.open('a') as h:h.write('}\n')
    save(root/'job.json',dict(status='cancelled'));s=r.poll();e=s['episodes'][0]
    assert e['status']=='right_censored' and e['task_success'] is None and s['window']['episodes']==0
    assert 'cross_track_m' not in e['metrics'] and laya_summary(s)==[]


def test_checkpoint_window_excludes_post_checkpoint_episodes_and_pending(tmp_path):
    root=fixture(tmp_path);append(root/'environment_trace.jsonl',[row(0,0,True),row(1,0,True),row(2,0)])
    for name,step in [('step_one',20001),('.pending',20002),('unpublished',20002)]:
        save(root/'checkpoints'/name/'checkpoint.json',dict(global_steps=step,optimizer_updates=14999,replay_size=25000,reason='periodic'))
        if name!='unpublished':save(root/'checkpoints'/name/'manifest.json',{})
    s=DashboardReader(root).poll();assert len(s['checkpoints'])==1
    c=s['checkpoints'][0];assert c['window']['episodes']==1 and c['critic_updates']==14999 and c['trace_caught_up']


def test_Qt_dashboard_updates_from_background_without_process_or_policy(tmp_path,monkeypatch):
    root=fixture(tmp_path);append(root/'environment_trace.jsonl',[row(0,0,True),row(1,0)])
    q=Q.QApplication.instance() or Q.QApplication([]);p=TrainingDashboard();p.auto_laya.setChecked(False)
    p.set_job(root);p.show()
    for _ in range(100):
        q.processEvents();QtTest.QTest.qWait(10)
        if p.snapshot:break
    assert p.snapshot and p.episodes.rowCount()==2 and p.laya is None
    assert 'EP 2' in p.map.note.text() and p.map.dynamic
    # World Y is up and world positive yaw is CCW: arrow tip points up.
    arrow=p.map.dynamic[-1].polygon();assert arrow[0].y()<arrow[2].y()
    p.close();q.processEvents();assert p.closed and not p.timer.isActive()


def test_laya_reply_cannot_alter_numeric_stats(tmp_path):
    root=fixture(tmp_path);append(root/'environment_trace.jsonl',[row(0,0,True)])
    q=Q.QApplication.instance() or Q.QApplication([]);p=TrainingDashboard();p.timer.stop();p.auto_laya.setChecked(False)
    s=DashboardReader(root).poll();p.reader=DashboardReader(root);p.render(s)
    p.laya_error('fixture missing cache')
    assert not p.auto_laya.isChecked() and p.episodes.item(0,5).text()=='3.000'
    assert 'fixture missing cache' in p.laya_note.text()
    p.close();q.processEvents()


def test_checkpoint_Laya_uses_only_episodes_before_its_step(tmp_path,monkeypatch):
    root=fixture(tmp_path);append(root/'environment_trace.jsonl',[row(0,0,True,error=.003),row(1,0,True,error=.009)])
    cp=root/'checkpoints/first';save(cp/'checkpoint.json',dict(global_steps=20001));save(cp/'manifest.json',{})
    q=Q.QApplication.instance() or Q.QApplication([]);p=TrainingDashboard();p.timer.stop()
    monkeypatch.setattr(p,'send_laya',lambda:None)
    s=DashboardReader(root).poll();p.queue_laya(s)
    jobs=list(p.pending);assert len(jobs)==2
    cp_job=next(v for v in jobs if 'cp:' in v['key']);assert len(cp_job['rows'])==1
    assert cp_job['rows'][0]['truth_path_rmse_m']==.002
    p.queue_laya(s);assert len(p.pending)==2  # no repeated classification on idle polls
    p.close();q.processEvents()


def test_map_switches_to_evaluation_while_training_statistics_stay_separate(tmp_path):
    root=fixture(tmp_path);append(root/'environment_trace.jsonl',[row(0,0,True)])
    save(root/'training_result.json',dict(global_steps=20001))
    target=root/'evaluation/6_B0';target.mkdir(parents=True)
    append(target/'environment_trace.jsonl',[row(0,1)])
    s=DashboardReader(root).poll()
    assert s['map_scope'].startswith('EVAL 6_B0')
    assert s['current']['truth_pose'][0]==.1 and s['truth_path'][0][0]==.1
    assert s['episodes'][0]['truth_pose'][0]==0 and s['window']['episodes']==1


def test_installed_GUI_resolves_source_workspace_without_env(tmp_path,monkeypatch):
    from nino_pi import research_jobs
    root=tmp_path/'repo';marker=root/'src/nino_rl/scripts/residual_workflow.sh'
    marker.parent.mkdir(parents=True);marker.touch()
    monkeypatch.delenv('NINO_REPO',raising=False)
    monkeypatch.setattr(research_jobs,'__file__',str(root/'install/nino_pi/lib/python3.12/site-packages/nino_pi/research_jobs.py'))
    assert research_jobs.repository()==root
    monkeypatch.setenv('NINO_REPO',str(tmp_path/'missing'))
    import pytest
    with pytest.raises(ValueError):research_jobs.repository()
