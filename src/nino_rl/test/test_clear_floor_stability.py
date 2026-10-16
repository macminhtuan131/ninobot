import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/"scripts/audit_clear_floor_stability.py"
spec=importlib.util.spec_from_file_location("stability_audit",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_isolated_zero_wheel_sample_is_not_a_sustained_stall():
    samples=[(0.,2.),(.02,0.),(.04,2.),(.06,2.)]
    assert module.sustained_start(samples,lambda value:value<1.) is None


def test_missing_samples_do_not_fabricate_stall_duration():
    samples=[(0.,0.),(.02,0.),(.5,0.),(.52,0.)]
    assert module.sustained_start(samples,lambda value:value<1.) is None


def test_continuous_stall_reports_onset_not_confirmation_time():
    samples=[(i*.02,0.) for i in range(8)]
    assert module.sustained_start(samples,lambda value:value<1.)==0.


def test_stability_profile_preserves_PI_and_physical_scoring_contract():
    from nino_rl.core import load_config
    root=Path(__file__).resolve().parents[1]/"config"
    original=load_config(root/"factory_floor_governor_full.yaml")
    fixed=load_config(root/"factory_floor_stability_pi_check.yaml")
    assert fixed["simulation_model"]["caster_wheel_damping"]==.001
    assert not fixed["simulation_model"]["hardware_validated"]
    for key in ("simulation_model","research_map"):
        original.pop(key,None);fixed.pop(key,None)
    assert original==fixed  # No reward, sensor, PI, arrival or clock gate drift.


def test_missing_stop_feedback_cannot_be_reported_as_settled(tmp_path):
    (tmp_path/"samples.jsonl").write_text("")
    result=module.settling_audit(tmp_path,10.)
    assert not result["available"] and result["settled"] is None
