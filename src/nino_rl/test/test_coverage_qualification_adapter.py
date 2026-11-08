"""Real failed-row regression and unchanged request/lifecycle delegation; offline."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from nino_rl import coverage_qualification_adapter as fix


def test_real_first_tick_reproduces_failure_and_metadata_only_fix_passes_validator():
    fixture=json.loads((Path(__file__).parent/'fixtures/coverage_first_tick_failure_v1.json').read_text())
    raw=fixture['row'];before=deepcopy(raw)
    epoch=raw['sensor_clock_s']-raw['task']['elapsed_s']
    abi=fix.failed_v1.protocol()['parent']['controller_abi_sha256']
    with pytest.raises(KeyError,match='qualification_condition'):
        fix.failed_v1.frozen.qualified.verify_transition(raw,None,epoch,abi)
    corrected=fix.condition_metadata(raw,'A_gaussian',11,6.)
    fix.failed_v1.frozen.qualified.verify_transition(corrected,None,epoch,abi)
    fix.failed_v1.frozen.feasibility(corrected,.04)
    assert raw==before
    assert {k:v for k,v in corrected.items() if k!='qualification_condition'}==raw
    assert corrected['qualification_condition']==dict(arm='A_gaussian',seed=11,source_stop_s=6.)


def test_proxy_delegates_configuration_request_and_response_without_truth_access():
    calls=[]
    class Backend:
        protocol={'command_until_s':6.}
        def advance_reference(self,*args,**kwargs):
            calls.append((args,kwargs));return 'view','labels',False,False,{'raw':'unchanged'}
    backend=Backend();proxy=fix.QualifiedBackend(backend,'C_stratified_probes',22)
    request=np.array([.004,.0]);result=proxy.advance_reference(request,dt=.1)
    assert calls[0][0][0] is request and calls[0][1]=={'dt':.1}
    assert result[:4]==('view','labels',False,False)
    assert result[4]['raw']=='unchanged'
    proxy.protocol={'command_until_s':8.}
    assert backend.protocol['command_until_s']==8.
    assert proxy.advance_reference(request)[4]['qualification_condition']['source_stop_s']==8.


def test_invalid_or_conflicting_metadata_fails_before_request_or_overwrite():
    class Backend:
        protocol={'command_until_s':7.}
        def advance_reference(self,*a,**kw):pytest.fail('Invalid plan must not reach backend')
    with pytest.raises(ValueError,match='Undeclared'):
        fix.QualifiedBackend(Backend(),'A_gaussian',11).advance_reference([0.,0.])
    with pytest.raises(ValueError,match='Conflicting'):
        fix.condition_metadata({'qualification_condition':{'source_stop_s':8.}},'A_gaussian',11,6.)


def test_prepared_factory_uses_frozen_wrapper_without_mutating_worker(tmp_path,monkeypatch):
    captured=[]
    monkeypatch.setattr(fix.failed_v1,'training_environment',lambda backend,*args:captured.append(backend) or 'prepared')
    backend=SimpleNamespace(protocol={'command_until_s':6.})
    assert fix.prepared_training_environment(backend,tmp_path,'A_gaussian',11)=='prepared'
    assert isinstance(captured[0],fix.QualifiedBackend)


@pytest.mark.parametrize('corrected',[False,True])
def test_first_step_through_actual_training_wrapper_and_real_validator(tmp_path,corrected):
    from nino_rl.coverage_sampling import CoverageSampler
    job=fix.failed_v1
    config,_,task,_=job.configuration(6.)
    backend=job.frozen.offline.fixture_backend(config,6.)
    original=backend.advance_reference
    def synthetic_guidance_envelope(*args,**kwargs):
        # The reduced fixture has no GuidedBackend. Explicit synthetic flags
        # let this test exercise the wrapper/validator interface, not physics.
        view,labels,term,trunc,info=original(*args,**kwargs)
        return view,labels,term,trunc,dict(info,truth_used_for_guidance=False,
            guidance_audit=dict(fault=False),source_lags_s=dict(wheel=0.,imu=0.))
    backend.advance_reference=synthetic_guidance_envelope
    backend.namespace='software_epoch_0';backend.current=backend
    backend.directory=tmp_path;backend.protocol=task
    factory=fix.prepared_training_environment if corrected else job.training_environment
    env=factory(backend,tmp_path,'A_gaussian',11)
    try:
        obs,_=env.reset(seed=11)
        request,audit=CoverageSampler(11,'A_gaussian').choose(obs,np.zeros(1,np.float32),0)
        env.model=SimpleNamespace(nino_collection_audit=audit)
        if not corrected:
            with pytest.raises(KeyError,match='qualification_condition'):env.step(request)
            assert env.rows==[]
        else:
            env.step(request)
            assert len(env.rows)==1
            assert env.rows[0]['qualification_condition']==dict(arm='A_gaussian',seed=11,source_stop_s=6.)
    finally:env.close()
