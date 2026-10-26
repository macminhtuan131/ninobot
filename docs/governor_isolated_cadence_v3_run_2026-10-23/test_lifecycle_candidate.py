import importlib.util
from copy import deepcopy
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('candidate',Path(__file__).with_name('lifecycle_candidate.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
    session=dict(schema='isolated_joint_gt_integration_v1',session_id='s',protocol_sha256='p',
        source_sha256={'primary':{'logger':'hash'}},max_status_age_s=2.,max_source_age_s=.1)
    marker=dict(event='end',run_id='r',attempt=1,time_s=10.)
    receipt=dict(schema=session['schema'],session_id='s',protocol_sha256='p',role='primary',
        source_sha256={'logger':'hash'},pid=123,output='/capture',ready=True,closed=False,
        error=None,monotonic_ns=1_000_000_000,now_ns=10_000_000_000,
        marker=marker,lifecycle=[marker],counts={t:100 for t in m.SENSOR_TOPICS},
        latest_source_ns={t:10_000_000_000 for t in m.SENSOR_TOPICS})
    live=deepcopy(receipt);live.pop('marker');live['monotonic_ns']=4_000_000_000
    return session,live,receipt,marker


def test_old_receipt_with_fresh_live_heartbeat_is_not_missing_delivery():
    s,l,r,e=fixture()
    with pytest.raises(ValueError,match='Stale logger status'):
        m.check_status(s,r,'primary',marker=e,now_mono_ns=4_100_000_000)
    assert m.check_delivery(s,l,r,'primary',e,4_100_000_000)


@pytest.mark.parametrize('fault',[
    'stale','future','closed','error','not_ready','pid','output','session','source',
    'foreign_marker','missing_live_marker','receipt_newer','missing_stream','regressed_stream'])
def test_receipt_does_not_mask_faulty_live_process(fault):
    s,l,r,e=fixture();now=4_100_000_000
    if fault=='stale':now=7_000_000_000
    elif fault=='future':l['monotonic_ns']=5_000_000_000
    elif fault=='closed':l['closed']=True
    elif fault=='error':l['error']='disk error'
    elif fault=='not_ready':l['ready']=False
    elif fault=='pid':l['pid']=456
    elif fault=='output':l['output']='/other'
    elif fault=='session':l['session_id']='foreign'
    elif fault=='source':l['source_sha256']={}
    elif fault=='foreign_marker':e=dict(e,run_id='other')
    elif fault=='missing_live_marker':l['lifecycle']=[]
    elif fault=='receipt_newer':r['monotonic_ns']=5_000_000_000
    elif fault=='missing_stream':l['counts']['/joint_states']=0
    elif fault=='regressed_stream':l['latest_source_ns']['/joint_states']-=1
    with pytest.raises(ValueError):m.check_delivery(s,l,r,'primary',e,now)


def test_paused_simulation_does_not_require_advancing_sensors():
    s,l,r,e=fixture()
    # Exactly equal simulated clock/source stamps throughout wall-time wait.
    assert l['now_ns']==r['now_ns']
    assert m.check_delivery(s,l,r,'primary',e,4_100_000_000)


def test_initial_readiness_keeps_original_source_freshness_gate():
    s,l,r,e=fixture();l['latest_source_ns']['/joint_states']-=200_000_000
    with pytest.raises(ValueError,match='Stale/future logger sensor'):
        m.check_status(s,l,'primary',now_mono_ns=4_100_000_000)
