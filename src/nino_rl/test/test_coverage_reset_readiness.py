"""Recorded V2 failure and offline candidate; no reset/job/physics release."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from nino_rl import coverage_reset_readiness as readiness
from nino_rl import residual_coverage_study_v2 as frozen_job


def fixture():
    return json.loads((Path(__file__).parent/'fixtures/coverage_v2_initial_permission_failure.json').read_text())


def test_recorded_inhibit_precedes_action_and_reproduces_real_validator_error():
    f=fixture();row=f['inhibited']['row'];before=deepcopy(row)
    assert row['step']==0 and row['timestep']==841
    assert row['reference_trace']['source_samples']['status']['values']['permission'] is False
    assert row['plan_projection']['windowed_common_m_s']==0.
    assert row['final_ros_reference']==[0.,0.] and row['reference_trace']['proposal'] is None
    with pytest.raises(TypeError,match='NoneType'):
        frozen_job.frozen.qualified.verify_transition(row,None,
            row['sensor_clock_s']-row['task']['elapsed_s'],frozen_job.protocol()['parent']['controller_abi_sha256'])
    with pytest.raises(readiness.DecisionInputNotReady,match='inhibited before replay'):
        readiness.require_uninhibited_transition(row)
    with pytest.raises(ValueError,match='feasibility failure'):
        frozen_job.frozen.feasibility(row,.04)
    assert row==before


def test_recorded_normal_history_warmup_remains_allowed_by_real_validator():
    row=fixture()['passing']['row'];before=deepcopy(row)
    assert row['reference_trace']['history_ready'] is False
    assert readiness.require_uninhibited_transition(row) is row
    frozen_job.frozen.qualified.verify_transition(row,None,
        row['sensor_clock_s']-row['task']['elapsed_s'],frozen_job.protocol()['parent']['controller_abi_sha256'])
    assert row==before


def test_joint_observer_support_and_quiet_do_not_replace_drive_acknowledgement():
    f=fixture();row=f['inhibited']['row'];drive=f['drive_before']
    decision=row['reference_trace']['input_stamp_s']
    checked=readiness.assess_zero_reset(drive['values'],source_age_s=decision-drive['stamp_s'],physically_quiet=True)
    assert checked==dict(ready=False,reasons=['drive_has_not_acknowledged_wheel_feedback'])
    # Later diagnostics are genuinely new support, not a fabricated replacement
    # for the failed decision. They cannot retrospectively validate its row.
    drive=f['drive_after']
    assert readiness.assess_zero_reset(drive['values'],source_age_s=row['sensor_clock_s']-drive['stamp_s'],
        physically_quiet=True)['ready']
    with pytest.raises(readiness.DecisionInputNotReady):readiness.require_uninhibited_transition(row)


@pytest.mark.parametrize('change,age,quiet',[
    ({'have_wheel_state':0.},.01,True),({'have_wheel_state':None},.01,True),
    ({'have_wheel_state':'1'},.01,True),({},.041,True),({},-.001,True),
    ({},float('nan'),True),({},None,True),({},.01,False),
    ({'left_target_rad_s':.01},.01,True),({'executed_linear_m_s':float('nan')},.01,True)])
def test_missing_stale_or_nonzero_reset_is_blocked(change,age,quiet):
    drive=fixture()['drive_after']['values'];drive.update(change)
    assert not readiness.assess_zero_reset(drive,source_age_s=age,physically_quiet=quiet)['ready']


def test_missing_proposal_never_becomes_a_fabricated_zero_request():
    row=fixture()['passing']['row'];row['reference_trace']['proposal']=None
    with pytest.raises(readiness.DecisionInputNotReady,match='Missing controller proposal'):
        readiness.require_uninhibited_transition(row)
    assert row['reference_trace']['proposal'] is None
