"""Meaningful offline checks: timestamps, full accounting, missing data, spikes."""
import sys
import json
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_governor_survey_phases import (
    asof, accounting, executed_transitions, partition, phase_at, parse_context,
)


def sequence():
    keys = [("CRUISE", 1.), ("HOLD", .96), ("HOLD", .92), ("HOLD", .9),
            ("RECOVER", .94), ("RECOVER", .98), ("CRUISE", 1.)]
    controls = [dict(governor_input_time_s=10+i*.1, governor_phase=p,
                     governor_scale=s, governor_requested_linear_m_s=.4) for i,(p,s) in enumerate(keys)]
    drive = [(10+i*.1+.02, dict(command_received_sim_s=10+i*.1,
                               requested_linear_m_s=.4*s, executed_linear_m_s=.4*s))
             for i,(_,s) in enumerate(keys)]
    return controls, drive


def test_saved_publication_not_endpoint_or_future_sample():
    controls, drive = sequence()
    bounds, detail = executed_transitions(controls, drive)
    assert bounds["braking"] == pytest.approx(10.12)
    assert bounds["holding"] == pytest.approx(10.32)
    assert bounds["recovery"] == pytest.approx(10.42)
    assert bounds["after_recovery"] == pytest.approx(10.62)
    assert detail[0]["input_s"] == pytest.approx(10.1)
    assert asof([(1., "a"), (2., "future")], 1.999999999, 1.) == (1., "a")
    assert asof([(1., "stale")], 2., .1) is None
    assert asof([(2., "future")], 1., .1) is None


def test_retrigger_or_missing_execution_not_silently_deleted():
    c,d = sequence()
    c.append(dict(c[-1], governor_input_time_s=11., governor_phase="HOLD", governor_scale=.96))
    with pytest.raises(ValueError, match="repeated sequence"):
        executed_transitions(c,d)
    c,d = sequence()
    with pytest.raises(ValueError, match="not found"):
        executed_transitions(c,d[:-1])
    d[0][1]["command_received_sim_s"] = 100.
    with pytest.raises(ValueError, match="Future"):
        executed_transitions(c,d)


def test_pi_event_translation_and_exhaustive_half_open_phases():
    bounds = dict(braking=11.1, holding=11.3, recovery=12.1, after_recovery=12.4)
    gov = partition(1.,11.,20.,bounds)
    pi = partition(2.,12.,22.,{k:v+1. for k,v in bounds.items()})
    assert gov[3][1]-11. == pytest.approx(pi[3][1]-12.)
    assert phase_at(gov, 11.1) == "braking"
    assert phase_at(gov, 12.1) == "recovery"
    assert phase_at(gov, 20.) == "after_recovery"
    assert phase_at(gov, 21.) is None
    with pytest.raises(ValueError, match="unordered"):
        partition(1.,11.,20., dict(bounds, recovery=11.2))


def test_clipped_quadrature_conserves_spike_integral_and_distance():
    t = np.arange(0.,1.001,.02)
    q = np.full(len(t), .001)
    q[20] = 100.  # Never drop or smooth the spike, even on a phase boundary.
    s = dict(time=t, q=q, xy=np.column_stack((t,np.zeros(len(t)))))
    windows = [("a",0.,.395),("b",.395,.413),("c",.413,1.)]
    pieces,total = accounting(s,windows,0.,1.)
    assert total["slip_square_integral_s"] > 1.99
    assert sum(p["slip_square_integral_s"] for p in pieces.values()) == pytest.approx(total["slip_square_integral_s"])
    assert sum(p["distance_m"] for p in pieces.values()) == pytest.approx(1.)


def test_missing_or_long_gapped_data_remains_unavailable_not_zero():
    t = np.arange(0.,1.001,.02)
    q = np.ones(len(t)); q[10:30] = np.nan
    s = dict(time=t,q=q,xy=np.column_stack((t,t*0)))
    pieces,total = accounting(s,[("all",0.,1.)],0.,1.)
    assert not pieces["all"]["available"]
    assert total["slip_square_integral_s"] is None
    assert total["observed_slip_square_integral_s"] > 0
    assert total["coverage_fraction"] < .98


def test_raw_imu_spike_and_unloaded_manifold_not_discarded_or_treated_as_load(tmp_path):
    (tmp_path/"resolved_config.json").write_text(json.dumps(dict(policy_v2=dict(imu_includes_gravity=True))))
    (tmp_path/"contact_events.jsonl").write_text("")
    stamp = dict(sec=1,nanosec=0)
    imu = dict(topic="/imu/data",data=dict(header=dict(stamp=stamp),orientation=dict(x=0.,y=0.,z=0.,w=1.),
                linear_acceleration=dict(x=0.,y=0.,z=9.80665)))
    spike = json.loads(json.dumps(imu)); spike["data"]["linear_acceleration"]["z"] = 109.80665
    contact = dict(topic="/nino/contact_lab/right_wheel",data=dict(header=dict(stamp=stamp),contacts=[dict(
        collision1=dict(name="cable_bumps::cables::C1_collision"),collision2=dict(name="wheel"),depths=[-.001],
        wrenches=[dict(body_1_wrench=dict(force=dict(x=0.,y=0.,z=0.)))])]))
    (tmp_path/"samples.jsonl").write_text("\n".join(json.dumps(r) for r in (imu,spike,contact))+"\n")
    out = parse_context(dict(logger=tmp_path,start=.9,end=1.1))
    assert [v for _,v in out["imu"]] == pytest.approx([0.,100.])
    value = out["contacts"]["right_wheel"][0][1]
    assert value["obstacle_manifold"]
    assert not value["obstacle_loaded"]
