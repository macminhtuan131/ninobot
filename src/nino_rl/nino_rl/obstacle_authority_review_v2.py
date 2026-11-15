"""Offline E2 query-support correction; no controller/runtime or metric changes."""
import numpy as np
from .causal_source_support import contrast, ns

REVIEW_ID = 'nino_e2_ambiguity_query_review_v2'


def compare_channel(control, candidate, channel, q, maximum_age):
    return contrast(control['data'][channel], candidate['data'][channel], q, maximum_age)


def approach(control, candidate, contract):
    out = {}
    ledger = []
    for name, shift, step, channel, age in (
        ('GT20ms', 0., .02, 'body', .04),
        ('GT20ms_shift10ms', .01, .02, 'body', .04),
        ('native100ms', 0., .1, 'native', .1),
    ):
        q = -.5 + shift + np.arange(round(.5/step))*step
        d, valid, a, b = compare_channel(control,candidate,channel,q,age)
        rms = float(np.sqrt(np.mean(np.asarray([v for v in d if v is not None])**2))) if np.any(valid) else None
        out[name] = dict(samples=len(q),supported_samples=int(valid.sum()),
            rms_candidate_minus_control_m_s=rms,
            pass_caliper=bool(np.all(valid) and rms <= contract['approach_caliper_m_s'] + 1e-12))
        ledger.extend(dict(grid=name,channel=channel,query_phase_ns=ns(t),supported=bool(v),
            control_source_phase_ns=sa,candidate_source_phase_ns=sb,control_reason=ra,candidate_reason=rb)
            for t,v,sa,sb,ra,rb in zip(q,valid,a.source_ns,b.source_ns,a.reasons,b.reasons))
    q = -.5 + np.arange(25)*.02
    d, valid, a, b = compare_channel(control,candidate,'reference',q,.1)
    values = [v for v in d if v is not None]
    out['precontact_accepted_reference'] = dict(supported_samples=int(valid.sum()),
        maximum_absolute_difference_m_s=float(np.max(np.abs(values))) if values else None,
        note='State-dependent follower; no exact-state equivalence')
    return out, ledger


def authority(control, candidate, contract, sign):
    if sign not in (-1,1): raise ValueError('Common sign must be -1 or +1')
    start=candidate['trigger'];deadline=min(control['drive'],candidate['drive'])
    if deadline<=start:
        return dict(supported=False,descriptive_chain_persistence_pass=False,reason='No remaining drive horizon',query_ledger=[])
    q=start+np.arange(int(np.ceil((deadline-start)/.02)))*.02
    q=q[q<deadline-1e-9]
    channels={k:compare_channel(control,candidate,k,q,age)
              for k,age in (('body',.04),('wheel',.04),('driver',.04),('reference',.1))}
    valid=np.logical_and.reduce([data[1] for data in channels.values()])
    mask=[];ledger=[]
    for i,t in enumerate(q):
        after=all(channels[k][3].source_ns[i] is not None and channels[k][3].source_ns[i]>=ns(start)
                  for k in ('body','wheel','driver'))
        d={k:data[0][i] for k,data in channels.items()}
        correct=bool(valid[i] and after)
        if correct:
            correct=(sign*d['reference'][0]>1e-9 and np.all(sign*d['driver']>1e-9)
                     and np.all(sign*d['wheel']>1e-9)
                     and sign*d['body'][0]>=contract['useful_signed_body_delta_m_s']-1e-12)
        mask.append(bool(correct))
        ledger.append(dict(phase_s=float(t),supported=bool(valid[i]),after_candidate_trigger=after,chain=bool(correct),
            channels={k:dict(delta=None if data[0][i] is None else data[0][i].tolist(),
                supported=bool(data[1][i]),control_source_phase_ns=data[2].source_ns[i],candidate_source_phase_ns=data[3].source_ns[i],
                control_reason=data[2].reasons[i],candidate_reason=data[3].reasons[i]) for k,data in channels.items()}))
    intervals=[];begin=None
    for i in range(len(q)+1):
        active=i<len(q) and mask[i]
        if active and begin is None:begin=i
        if not active and begin is not None:
            end=i-1
            spans=[(data[side].source_ns[end]-data[side].source_ns[begin])/1e9
                   for k,data in channels.items() if k in ('body','wheel','driver') for side in (2,3)]
            span=min(spans)
            intervals.append(dict(first_query_s=float(q[begin]),last_query_s=float(q[end]),
                minimum_observed_source_span_s=span,samples=i-begin,
                persistence_pass=span>=contract['minimum_observed_persistence_s']-1e-9))
            begin=None
    return dict(sign=sign,candidate_actual_trigger_phase_s=start,earlier_drive_deadline_phase_s=deadline,
        sampled_queries=len(q),supported_queries=int(valid.sum()),supported=bool(np.all(valid)),
        chain_signed_queries=sum(mask),intervals=intervals,
        descriptive_chain_persistence_pass=any(i['persistence_pass'] for i in intervals),
        source_span_not_cell_padding=True,causality_requires_approach_caliper=True,query_ledger=ledger)
