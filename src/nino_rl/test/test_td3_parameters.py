from copy import deepcopy
from pathlib import Path
import pytest
from nino_rl.core import load_config
from nino_rl.td3_config import load_profiles, validate_profile, apply_profile, validate_runtime
from nino_rl.residual_experiment import experiment_contract


def base():
    return load_config(Path(__file__).resolve().parents[1]/'config/residual_velocity_td3.yaml')


def test_profiles_are_proposals_not_releases_and_have_distinct_abis():
    abis=[]
    for name,p in load_profiles().items():
        report=validate_profile(p)
        assert report['valid'] and not report['training_authorized'] and not report['hardware_authorized']
        c=apply_profile(base(),name)
        assert c['training']==dict(allowed=False,backend_validation_artifact=None,budget_transitions=None)
        validate_runtime(c)
        if 'research_' in name:abis.append(experiment_contract(c)['abi_sha256'])
    assert len(set(abis))==3
    assert validate_profile(load_profiles()['nino_td3_research_h8_v1'])['history_span_s']==.7


@pytest.mark.parametrize('section,key,value',[
    ('algorithm','critic_lr',.001),('algorithm','gamma',float('nan')),
    ('algorithm','batch_size',True),('algorithm','buffer_size',1),
    ('algorithm','learning_starts',1000001),('algorithm','network_arch',[-1]),
    ('observation','history_len',0),('observation','missing_data','mask'),
    ('observation','normalization','frozen_train_stats'),('action','schema','direct_v_omega'),
    ('action','hardware_residual_scale',.05),('evaluation','seeds',[1,1]),
])
def test_invalid_or_unimplemented_contracts_rejected(section,key,value):
    p=deepcopy(load_profiles()['nino_td3_research_h5_v1']);p[section][key]=value
    with pytest.raises(ValueError):validate_profile(p)


def test_hash_changes_and_profile_edit_revokes_old_release():
    p=deepcopy(load_profiles()['nino_td3_research_h5_v1']);original=validate_profile(p)['sha256']
    p['algorithm']['gamma']=.98
    assert validate_profile(p)['sha256']!=original
    c=base();c['training']=dict(allowed=True,backend_validation_artifact='old.json',budget_transitions=99)
    c=apply_profile(c,'nino_td3_smoke_h5_v1')
    assert c['training']['allowed'] is False and c['training']['backend_validation_artifact'] is None
    c['algorithm_parameters']['TD3']['actor_lr']=.003
    with pytest.raises(ValueError,match='Unsupported'):validate_runtime(c)


def test_effective_profile_reaches_optimizer_replay_and_portable_actor(tmp_path):
    import numpy as np
    import torch
    from nino_rl.residual_workflow import default_config,validation_job
    from nino_rl.residual_experiment import make_environment,build_model
    from nino_rl.velocity_backend import VelocityBackend
    from nino_control.residual_actor import export_actor
    torch.set_num_threads(1)
    config=apply_profile(default_config(),'nino_td3_smoke_h5_v1')
    validation_job(tmp_path,config)
    config['training']=dict(allowed=True,backend_validation_artifact=str(tmp_path/'validation.json'),budget_transitions=32)
    env=make_environment(config,VelocityBackend(config))
    try:
        model=build_model(config,env,seed=7)
        assert model.learning_starts==16 and model.batch_size==32 and model.buffer_size==2048
        before=[p.detach().clone() for p in model.actor.parameters()]
        model.learn(total_timesteps=32)
        assert model.replay_buffer.size()==32 and model._n_updates==16
        assert sum((p.detach()-b).abs().sum().item() for p,b in zip(model.actor.parameters(),before))>0
        assert np.max(np.abs(model.replay_buffer.actions[:32]))<=1.
        export_actor(model,'TD3',tmp_path,experiment_contract(config),purpose='software_parameter_test')
        config['algorithm_parameters']['TD3']['batch_size']=64
        with pytest.raises(ValueError,match='differ from named profile'):validate_runtime(config)
    finally:env.close()
