"""Read-only prospective motion-quality design. No ROS/physics/training runner."""
import hashlib
import json
import math
from pathlib import Path

PROTOCOL_ID = 'nino_known_route_motion_quality_draft_v1_2026_11_09'
ROOT = next(p for p in Path(__file__).resolve().parents if (p/'src/nino_rl/config').is_dir())
PATH = ROOT/'src/nino_rl/config/known_route_motion_quality_draft_v1.json'
NO_RELEASE = dict(physics_allowed=False,allocated_attempts=0,training_allowed=False,
                  optimizer_updates=0,hardware_actions=0,runtime_implemented=False)


def load(path=PATH):
    p=json.loads(Path(path).read_text())
    if (p.get('protocol_id') != PROTOCOL_ID or p.get('status') != 'proposed_not_released'
            or p.get('release') != NO_RELEASE or p['objective']['accepted'] is not False
            or p['decision_rules']['accepted'] is not False):
        raise ValueError('Motion-quality draft does not accept objectives or release execution')
    unsigned={k:v for k,v in p.items() if k!='spec_sha256'}
    if hashlib.sha256(json.dumps(unsigned,sort_keys=True,allow_nan=False).encode()).hexdigest()!=p['spec_sha256']:
        raise ValueError('Prospective specification changed')
    for name,digest in p['frozen_inputs'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Prospective input changed: '+name)
    return p


def reference_plan(plan):
    """Analytic command kinematics, not physics or body-response prediction.

    Start from rest, ramp with the proposed acceleration bound; switch the
    requested speed at known progress zones. Used only to set the slow control
    BEFORE data collection. Runtime must use a verified estimated progress.
    """
    r=plan['reference']; m=plan['measurement']
    v,slow,a = r['cruise_m_s'],r['preview_m_s'],r['acceleration_m_s2']
    zone0,zone1 = r['preview_progress_zone_m']
    lo,hi = m['progress_window_m']; warmup=r['warmup_s']
    if not (0 < slow < v and a > 0 and 0 < lo < zone0 < zone1 < hi):
        raise ValueError('Require lower preview speed and ordered route window/zone')
    if v*v/(2*a) > lo+1e-12 or zone0+(v*v-slow*slow)/(2*a) >= zone1:
        raise ValueError('Insufficient approach/zone distance for proposed ramp')
    if zone1+(v*v-slow*slow)/(2*a) >= hi:
        raise ValueError('Measurement must include full recovery ramp')
    segments=[]; x=0.;t=warmup;current=0.
    def segment(duration, acceleration, label):
        nonlocal x,t,current
        if duration < 0: raise ValueError('Negative profile duration')
        nxt=x+current*duration+.5*acceleration*duration**2
        segments.append(dict(label=label,start_s=t,end_s=t+duration,start_m=x,end_m=nxt,
                             initial_m_s=current,acceleration_m_s2=acceleration))
        x=nxt;t+=duration;current+=acceleration*duration
    segment(v/a,a,'startup_ramp')
    segment((zone0-x)/v,0.,'approach')
    segment((v-slow)/a,-a,'slowdown')
    segment((zone1-x)/slow,0.,'preview_hold')
    segment((v-slow)/a,a,'recovery')
    segment((hi-x)/v,0.,'exit')
    def arrival(position):
        for s in segments:
            if s['start_m']-1e-12 <= position <= s['end_m']+1e-12:
                distance=position-s['start_m'];u=s['initial_m_s'];acc=s['acceleration_m_s2']
                dt=(2*distance/(u+math.sqrt(max(0.,u*u+2*acc*distance)))) if distance else 0.
                return s['start_s']+dt
        raise ValueError('Position outside profile')
    entry,exit=arrival(lo),arrival(hi);duration=exit-entry
    constant=(hi-lo)/duration
    # Formula distance/v is valid because all controls finish startup before lo.
    assert constant*constant/(2*a) <= lo
    constant_exit=warmup+constant/a+(hi-constant*constant/(2*a))/constant
    if max(exit,constant_exit) >= r['source_stop_s']:
        raise ValueError('Planned stop overlaps traversal; choose contract before release')
    return dict(status='analytic_reference_only_not_body_response',segments=segments,
                preview_entry_s=entry,preview_exit_s=exit,preview_segment_duration_s=duration,
                nominal_segment_duration_s=(hi-lo)/v,
                constant_pace_m_s=constant,constant_segment_duration_s=(hi-lo)/constant,
                predicted_time_cost_fraction=duration/((hi-lo)/v)-1,
                actual_time_matching_verified=False,physics_steps=0)
