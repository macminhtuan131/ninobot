import hashlib
import json

from nino_pi.training_dashboard_data import DashboardReader


def test_goal_map_uses_its_episode_reset_layout_and_evaluation_scene(tmp_path):
    floor=tmp_path/'clear.sdf'
    bump=tmp_path/'bump.sdf'
    floor.write_text('<sdf><world name="x"><model name="floor"><link name="g"><collision name="floor"><geometry><box><size>3 2 0.1</size></box></geometry></collision></link></model></world></sdf>')
    bump.write_text(floor.read_text().replace('name="floor"','name="obstacle"'))
    def episode(path,world):
        path.mkdir(exist_ok=True)
        (path/'job.json').write_text(json.dumps(dict(status='completed')))
        (path/'episode_0_reset.json').write_text(json.dumps(dict(private_layout=dict(
            id='goal_fixture',world=str(world),world_sha256=hashlib.sha256(world.read_bytes()).hexdigest()))))
        row=dict(episode=0,step=1,done=True,reward=1.,truth_pose_m_rad=[1.,0.,0.],
                 task=dict(task_success=True,termination_reason='task_success',cross_track_m=.001,elapsed_s=1.))
        (path/'environment_trace.jsonl').write_text(json.dumps(row)+'\n')
    episode(tmp_path,floor)
    snap=DashboardReader(tmp_path).poll()
    assert snap['world']['sha256']==hashlib.sha256(floor.read_bytes()).hexdigest()
    assert snap['current']['termination']=='task_success'
    (tmp_path/'training_result.json').write_text('{}')
    target=tmp_path/'evaluation';target.mkdir();episode(target/'TD3',bump)
    snap=DashboardReader(tmp_path).poll()
    assert snap['world']['sha256']==hashlib.sha256(bump.read_bytes()).hexdigest()
    assert snap['map_scope'].startswith('EVAL')
