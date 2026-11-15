from copy import deepcopy
import json
import pytest
from nino_control.residual_velocity import FEATURES
from nino_rl.unknown_step_task import load,controller_features


def test_task_selected_by_user_is_not_a_physics_or_training_release():
    p=load()
    assert p['objective']['user_selected']
    assert p['objective']['priority'][0]=='physical_traversal_and_arrival'
    assert not p['release']['runtime_implemented'] and p['release']['allocated_attempts']==0
    assert p['numeric_acceptance']['path_max_m'] is None
    assert p['supersedes']['known_route_motion_quality_active'] is False


@pytest.mark.parametrize('channel',['obstacle_x_m','obstacle_height_m','distance_to_step_m',
    'time_to_contact_s','contact','truth_pose','caster_state','scenario_id','layout_seed'])
def test_privileged_channels_cannot_enter_declared_controller_packet(channel):
    sample={name:0. for name in FEATURES};sample[channel]=0.
    with pytest.raises(ValueError):controller_features(sample)


def test_feature_boundary_rejects_missing_nonfinite_and_preserves_order():
    sample={name:float(i) for i,name in enumerate(FEATURES)}
    assert controller_features(sample)==tuple(float(i) for i in range(20))
    sample.pop(FEATURES[0])
    with pytest.raises(ValueError):controller_features(sample)
    sample[FEATURES[0]]=float('nan')
    with pytest.raises(ValueError):controller_features(sample)


@pytest.mark.parametrize('change',['oracle','preview','priority','release'])
def test_misleading_contract_is_rejected_even_before_digest_check(tmp_path,change):
    p=deepcopy(load())
    if change=='oracle':p['controller_information']['privileged_contact_trigger']=True
    elif change=='preview':p['controller_information']['obstacle_preview']=True
    elif change=='priority':p['objective']['priority'][0]='vertical_IMU_RMS'
    else:p['release']['physics_allowed']=True
    path=tmp_path/'task.json';path.write_text(json.dumps(p))
    with pytest.raises(ValueError):load(path)
