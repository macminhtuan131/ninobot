"""Offline planning arithmetic only. No runner, release, policy or ROS interface."""
import hashlib
import json
import math
from pathlib import Path

DRAFT_ID='nino_prestop_tail_authority_draft_v1_2026_11_08'


def load(path,verify_inputs=True):
    plan=json.loads(Path(path).read_text())
    if plan['draft_id']!=DRAFT_ID or plan['status']!='prepared_not_released':
        raise ValueError('Only the unreleased planning draft is supported')
    release=plan['release']
    if release!=dict(physics_allowed=False,allocated_attempts=0,training_allowed=False,
            training_transitions=0,optimizer_updates=0,hardware_actions=0,runtime_implemented=False):
        raise ValueError('This draft cannot grant execution authority')
    p=plan['intervention']
    if (p['tail_seconds'],p['common_bound_m_s'],p['tail_scalar_levels'],p['differential'],
            p['control_interval_s'],p['source_stops_s'],p['horizon_s'])!=(.5,.005,[-1,0,1],0,.1,[6.,8.],14.):
        raise ValueError('A changed question/action/window requires a new draft version')
    attempts=plan['proposed_attempts']
    if len(attempts)!=12 or len({r['id'] for r in attempts})!=12:
        raise ValueError('Expected twelve distinct proposed slots')
    cells={(r['block'],r['stop_s'],r['tail_scalar']) for r in attempts}
    if cells!={(b,s,a) for b in (0,1) for s in (6.,8.) for a in (-1,0,1)}:
        raise ValueError('Incomplete or duplicated draft matrix')
    if plan['proposed_budget']['task_decision_ticks']!=1680:
        raise ValueError('Draft task budget mismatch')
    if verify_inputs:
        for name,expected in plan['frozen_inputs'].items():
            path=Path(name)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Frozen input changed: '+name)
    return plan


def request_at(plan,t,stop,level,*,healthy,nominal_v,source_forward):
    """One proposed factor, tail common request; no post-stop residual authority."""
    p=plan['intervention']
    if type(t) not in (int,float) or not math.isfinite(t) or not 0<=t<p['horizon_s']:
        raise ValueError('Finite task decision time required')
    if type(stop) not in (int,float) or stop not in p['source_stops_s']:
        raise ValueError('Unsupported source stop')
    if type(level) is not int or level not in p['tail_scalar_levels']:
        raise ValueError('Unsupported tail scalar')
    if type(healthy) is not bool or type(source_forward) is not bool or not math.isfinite(nominal_v):
        raise ValueError('Explicit causal validity/source flags required')
    if not healthy or not source_forward or t<.5-1e-8 or t>=stop-1e-8 or abs(nominal_v-.2)>1e-8:
        return 0.
    return 1. if t<stop-p['tail_seconds']-1e-8 else float(level)


def reference_preview(plan,limits):
    """Synthetic reference trajectories, not wheel/body simulation or outcomes."""
    from nino_control.residual_velocity import ReferenceLimits,ResidualReference
    dt=plan['intervention']['control_interval_s'];result=[]
    for stop in (6.,8.):
        for level in (-1,0,1):
            nominal=ResidualReference(ReferenceLimits(**limits))
            reference=ResidualReference(ReferenceLimits(**limits))
            rows=[]
            for tick in range(140):
                t=tick*dt;forward=.5-1e-8<=t<stop-1e-8
                source=(.2 if forward else 0.,0.)
                n=nominal.compose(source,(0.,0.),dt,permission=True,sensors_fresh=True,history_ready=True,command_age_s=0.)
                a=request_at(plan,t,stop,level,healthy=True,nominal_v=n['body_reference'][0],source_forward=forward)
                trace=reference.compose(source,(a*.005/limits['residual_wheel_m_s'],0.),dt,authority=1.,
                    permission=True,sensors_fresh=True,history_ready=True,command_age_s=0.)
                rows.append(dict(tick=tick,t=t,source=source[0],nominal_v=n['body_reference'][0],
                    requested_scalar=a,proposed_common=trace['proposed_residual_wheel_m_s'][0],
                    accepted_reference=trace['body_reference'][0]))
            result.append(dict(stop_s=stop,tail_scalar=level,rows=rows))
    return result
