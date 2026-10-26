"""Read-only source/artifact review; no ROS node, simulator, tuning or release."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/nino_rl'),str(ROOT/'src/nino_control'),str(ROOT/'src/nino_rl/scripts')]
from prepare_isolated_cadence_contract import validate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    out=Path(__file__).parent
    previous=ROOT/'docs/governor_isolated_cadence_v6_run_2026-10-23'
    bundle=ROOT/'docs/governor_isolated_cadence_contract_v7_2026-10-23'
    old_bundle=ROOT/'docs/governor_isolated_cadence_contract_v6_2026-10-23'
    p=json.loads((bundle/'protocol.json').read_text())
    old=json.loads((old_bundle/'protocol.json').read_text())
    protected=json.loads((previous/'closed_run_sha256.json').read_text())
    assert all(sha(path)==h for path,h in protected.items())
    assert p['fixed']==old['fixed'] and p['schedule']==old['schedule']
    assert p['parent_input_sha256']==old['parent_input_sha256']
    changed=[path for path,h in p['execution_dependency_sha256'].items()
             if old['execution_dependency_sha256'].get(path)!=h]
    assert set(changed)=={'src/nino_rl/nino_rl/isolated_acquisition.py',
                          'src/nino_rl/scripts/prepare_isolated_cadence_contract.py'}
    fixture=json.loads((previous/'queue_fault_fixture.json').read_text())
    assert sha(previous/'queue_fault_fixture.py')==fixture['fixture_source_sha256']
    assert sha(ROOT/'src/nino_rl/nino_rl/isolated_acquisition.py')==fixture['recorder_source_sha256']
    assert fixture['rows'][0]['received']=={'/joint_states':25,'/ground_truth/odom':5}
    assert fixture['rows'][1]['received']=={'/joint_states':50,'/ground_truth/odom':5}
    result=dict(mode='independent_offline_contract_review',date='2026-10-23',
        simulation_launches=0,ros_nodes_started=0,hardware_access=False,
        controller_changes=False,release_created=False,thresholds_accepted=False,
        contract_validation=validate(bundle),protected_v6_files_unchanged=len(protected),
        v6_v7_fixed_schedule_physical_inputs_equal=True,changed_dependencies=changed,
        fixture_source_binding_valid=True,
        qualification='Static provenance and fixture review only. Does not validate Gazebo coverage or useful control authority.',
        illustrative_math=dict(scale_change=.1,scale_rate_per_s=.4,ideal_ramp_duration_s=.25,
            earlier_publication_s=[.040,.042],ideal_shifted_ramp_reference_difference_m_s=[.0064,.00672],
            assumptions='Continuous equal ramps, same .4m/s reference, only start shifted. Not a bound on discrete event/retrigger trajectories or actual velocity.'),
        script_sha256=sha(__file__))
    (out/'review_v7.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
