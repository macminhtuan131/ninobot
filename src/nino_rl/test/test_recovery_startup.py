from copy import deepcopy
import math

import pytest

from nino_rl.recovery_startup import INITIALIZATION_ID, bootstrap_estimator
from nino_rl.recovery_startup import RetainedSourceGuard
from nino_rl.recovery_contract import StartBudget


def journal():
    rows = []
    for t in (.004,.02,.04,.06,.08,.1):
        rows.append(dict(channel='wheel',stamp_s=t,receipt_monotonic_s=1.+t,values=[-.16,-.16]))
    for t in (.002,.02,.04,.06,.08,.1):
        rows.append(dict(channel='imu',stamp_s=t,receipt_monotonic_s=1.+t,values=[0.,0.,0.,0.,0.,9.81]))
    return sorted(rows,key=lambda r:r['receipt_monotonic_s'])


def bootstrap(rows=None, **changes):
    args = dict(now_s=.1, receipt_cutoff_s=1.2, initial_pose=[0.,0.,0.],
                geometry=dict(radius_l=.0625,radius_r=.0625),
                estimator_settings=dict(maximum_gap_s=.04), epoch='fixture_epoch')
    return bootstrap_estimator(journal() if rows is None else rows,**dict(args,**changes))


def test_settling_motion_is_integrated_before_the_first_policy_decision():
    estimator, report = bootstrap()
    assert estimator.estimate()['pose'][0] == pytest.approx(-.00096)
    assert estimator.initialization == INITIALIZATION_ID
    assert report['unsupported_prefix_s'] == .004 and report['updates'] == 5
    assert report['truth_input'] is False
    estimator.push('wheel',.12,[-.16,-.16],1.12)
    estimator.push('imu',.12,[0.],1.12)
    estimator.advance(.12)
    assert estimator.x == pytest.approx(-.00116)


def test_initial_alignment_uses_causal_estimate_without_relaxing_budget():
    estimator, _ = bootstrap()
    budget = StartBudget(.05,.03,.005,.005,.008,.03)
    result = budget.check(dict(progress_m=estimator.x,cross_track_m=0.,heading_error_rad=0.),
                          declared_progress_m=estimator.x,remaining_path_m=4.)
    assert result['endpoint_error_bound_m'] == 0. and budget.maximum_initial_error_m == .008


def test_truth_channels_and_future_samples_do_not_change_bootstrap_estimate():
    original, _ = bootstrap()
    rows = journal()+[dict(channel='truth',values={'pose':[100.,100.,0.]})]
    rows += [dict(channel='wheel',stamp_s=.12,receipt_monotonic_s=1.11,values=[100.,100.])]
    a, _ = bootstrap(rows)
    assert a.estimate()['pose'] == original.estimate()['pose']
    for row in rows:
        if row['channel']=='imu' and row['stamp_s']==.1:
            row['receipt_monotonic_s']=5.
    b, _ = bootstrap(rows)
    assert b.time == .08
    assert b.x != original.x


@pytest.mark.parametrize('mutation', ['wheel_gap','gyro_gap','duplicate','reversal','missing','prefix','nan'])
def test_incomplete_or_invalid_startup_support_is_rejected(mutation):
    rows = journal()
    if mutation=='wheel_gap':
        rows=[r for r in rows if r['channel']!='wheel' or r['stamp_s'] in (.004,.1)]
    elif mutation=='gyro_gap':
        rows=[r for r in rows if r['channel']!='imu' or r['stamp_s'] in (.002,.1)]
    elif mutation=='duplicate':
        rows.append(deepcopy(rows[-1]))
    elif mutation=='reversal':
        rows.append(deepcopy(rows[1]))
    elif mutation=='missing':
        rows=[r for r in rows if r['channel']!='wheel']
    elif mutation=='prefix':
        rows=[dict(r,stamp_s=r['stamp_s']+.1) for r in rows]
    else:
        rows[0]['stamp_s']=math.nan
    with pytest.raises(ValueError):
        bootstrap(rows,now_s=.2 if mutation=='prefix' else .1)


def test_retained_source_guard_checks_incremental_gaps_before_return(tmp_path):
    import json
    path = tmp_path/'raw.jsonl'
    def append(times, channels=RetainedSourceGuard.channels):
        with path.open('a') as stream:
            for t in times:
                for key in channels:
                    stream.write(json.dumps(dict(channel=key,stamp_s=t))+'\n')
    append([.08,.1])
    guard = RetainedSourceGuard(path,start_s=.1)
    assert guard.admit(.1)['valid']
    append([.12,.14,.16,.18,.2])
    assert guard.admit(.2)['counts']['imu'] == 7
    append([.22,.24,.26,.28],channels=('wheel','truth','drive'))
    append([.28],channels=('imu',))
    with pytest.raises(ValueError,match='gap'):
        guard.admit(.28)
    with pytest.raises(RuntimeError,match='failed'):
        guard.admit(.28)


def test_new_physical_pose_epoch_excludes_only_pre_reset_setup_history():
    setup = journal()
    setup = [r for r in setup if r['channel'] != 'wheel' or r['stamp_s'] in (.004,.1)]
    with pytest.raises(ValueError, match='gap'):
        bootstrap(setup)
    post = [dict(r, stamp_s=r['stamp_s']+1., receipt_monotonic_s=r['receipt_monotonic_s']+1.)
            for r in journal()]
    post.insert(0, dict(channel='wheel', stamp_s=1., receipt_monotonic_s=2., values=[-.16,-.16]))
    estimator, report = bootstrap(setup+post, now_s=1.1, receipt_cutoff_s=2.2, source_epoch_s=1.)
    assert report['source_epoch_s'] == 1.
    assert report['unsupported_prefix_s'] == 0.
    assert report['initial_integration_stamp_s'] == 1.
    assert estimator.x == pytest.approx(-.001)
    broken = [r for r in post if r['channel'] != 'wheel' or r['stamp_s'] in (1.,1.004,1.1)]
    with pytest.raises(ValueError, match='gap'):
        bootstrap(setup+broken, now_s=1.1, receipt_cutoff_s=2.2, source_epoch_s=1.)


def test_post_reset_gyro_before_first_new_wheel_is_integrated_with_causal_support():
    rows = [dict(channel='wheel', stamp_s=t, receipt_monotonic_s=t+1., values=[0.,0.])
            for t in (.998,1.004,1.02,1.04,1.06)]
    rows += [dict(channel='imu', stamp_s=t, receipt_monotonic_s=t+1., values=[0.,0.,1.])
             for t in (1.002,1.02,1.04,1.06)]
    estimator, report = bootstrap(rows, now_s=1.06, receipt_cutoff_s=2.1, source_epoch_s=1.)
    assert estimator.yaw == pytest.approx(.06)
    assert report['initial_wheel_support_stamp_s'] == .998
    assert report['unsupported_prefix_s'] == 0.
    assert report['updates'] == 4
    with pytest.raises(ValueError, match='causal wheel support'):
        bootstrap([r for r in rows if r['stamp_s'] != .998], now_s=1.06,
                  receipt_cutoff_s=2.1, source_epoch_s=1.)


@pytest.mark.parametrize('source_epoch', [-1., .2, math.nan, math.inf])
def test_invalid_reset_epoch_is_rejected(source_epoch):
    with pytest.raises(ValueError):
        bootstrap(source_epoch_s=source_epoch)


@pytest.mark.parametrize('field,value', [('control_raw_dt_max_s', .006),
    ('control_raw_dt_min_s', 0.), ('control_raw_dt_max_s', math.nan),
    ('control_updates', 0), ('control_dt_fallbacks', 1),
    ('control_dt_invalid', 1), ('control_future_joint_updates', 1),
    ('control_dt_over_4ms', 1)])
def test_dense_diagnostics_do_not_hide_missing_or_invalid_pi_updates(tmp_path, field, value):
    import json
    values = dict(control_raw_dt_min_s=.002, control_raw_dt_max_s=.002,
        control_updates=10, control_dt_fallbacks=0, control_dt_invalid=0,
        control_future_joint_updates=0, control_dt_over_4ms=0)
    path = tmp_path/'raw.jsonl'
    rows = [dict(channel=k,stamp_s=.1,values=dict(values)) for k in RetainedSourceGuard.channels]
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    guard = RetainedSourceGuard(path,start_s=.1,maximum_control_gap_s=.004)
    assert guard.admit(.1)['maximum_control_dt_s'] == .002
    rows = [dict(r,stamp_s=.12) for r in rows]
    rows[-1]['values'] = dict(values, **{field:value})
    with path.open('a') as stream:
        stream.writelines(json.dumps(r)+'\n' for r in rows)
    with pytest.raises(ValueError,match='PI control timing'):
        guard.admit(.12)
