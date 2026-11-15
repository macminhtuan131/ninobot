"""Ambiguity stays unsupported; absence never becomes zero or future evidence."""
import numpy as np
import pytest
from nino_rl.causal_source_support import SourceSeries, contrast
from nino_rl.obstacle_authority_review_v2 import authority


def test_conflict_preserves_every_payload_and_blocks_fallback_until_new_source():
    s=SourceSeries([(0.,2.),(.02,3.),(.02,4.),(.02,3.),(.04,5.)])
    q=s.query([.01,.02,.03,.04],.04)
    assert q.supported.tolist()==[True,False,False,True]
    assert q.values[1] is None and q.values[2] is None
    assert s.conflicts[0]['payloads']==[[3.],[4.],[3.]]
    assert s.conflicts[0]['packet_count']==3
    assert q.reasons[1]=='ambiguous_source'


def test_conflict_before_window_does_not_invalidate_later_distinct_source():
    s=SourceSeries([(0.,1.),(0.,2.),(.01,3.),(.02,4.)])
    q=s.query([.01,.02],.04)
    assert q.supported.all() and len(s.conflicts)==1


@pytest.mark.parametrize('offset_ns,good', [(-1,True),(0,False),(1,False)])
def test_conflict_at_query_boundary_is_not_discarded(offset_ns,good):
    s=SourceSeries([(0.,1.),(.02,2.),(.02,3.),(.04,4.)])
    q=s.query([.02+offset_ns/1e9],.04)
    assert bool(q.supported[0]) is good


def test_identical_duplicates_are_supported_and_counted_without_fabrication():
    s=SourceSeries([(1.,[1.,2.]),(1.,[1.,2.])])
    assert s.query([1.],.04).supported.all()
    assert len(s.groups[0]['payloads'])==2 and not s.conflicts


def test_one_nanosecond_future_and_stale_queries_are_rejected():
    s=SourceSeries([(1.,2.),(1.02,3.)])
    q=s.query([1.-1e-9,1.01,1.06,1.06+1e-9],.04)
    assert q.supported.tolist()==[False,True,True,False]
    assert q.source_ns[1]==1000000000
    assert q.values[0] is None and q.values[3] is None


@pytest.mark.parametrize('samples',[[(1.,1.),(.99,2.)],[(1.,float('nan'))],[(float('inf'),1.)],[],[(1.,[1.]),(2.,[1.,2.])]])
def test_invalid_data_is_rejected_without_sorting_or_repair(samples):
    with pytest.raises(ValueError):SourceSeries(samples)


def test_unsupported_contrast_has_no_numeric_delta():
    a=SourceSeries([(0.,1.),(.02,2.),(.02,3.)]);b=SourceSeries([(0.,2.),(.02,4.)])
    d,valid,_,_=contrast(a,b,[0.,.02],.04)
    assert d[0][0]==1. and d[1] is None and valid.tolist()==[True,False]


@pytest.mark.parametrize('deadline,expected',[(.19,False),(.23,True)])
def test_authority_uses_observed_span_without_padded_cells(deadline,expected):
    q=np.arange(-.1,.51,.02)
    def run(candidate):
        d=.005 if candidate else 0.
        return dict(trigger=0.,drive=deadline,data={
            'body':SourceSeries([(t,.2+d) for t in q]),
            'wheel':SourceSeries([(t,[10+d,10+d]) for t in q]),
            'driver':SourceSeries([(t,[.2+d,10+d,10+d]) for t in q]),
            'reference':SourceSeries([(t,.2+d) for t in q])})
    result=authority(run(False),run(True),dict(useful_signed_body_delta_m_s=.001,minimum_observed_persistence_s=.2),1)
    assert result['descriptive_chain_persistence_pass'] is expected
    assert all(i['last_query_s']<deadline for i in result['intervals'])


def test_ambiguity_inside_authority_window_keeps_support_failure():
    q=np.arange(-.1,.51,.02)
    def run(candidate):
        d=.005 if candidate else 0.
        wheels=[]
        for t in q:
            wheels.append((t,[10+d,10+d]))
            if candidate and abs(t-.1)<1e-9:wheels.append((t,[9.,9.]))
        return dict(trigger=0.,drive=.49,data={
            'body':SourceSeries([(t,.2+d) for t in q]),'wheel':SourceSeries(wheels),
            'driver':SourceSeries([(t,[.2+d,10+d,10+d]) for t in q]),
            'reference':SourceSeries([(t,.2+d) for t in q])})
    r=authority(run(False),run(True),dict(useful_signed_body_delta_m_s=.001,minimum_observed_persistence_s=.2),1)
    assert r['supported'] is False
    invalid=[x for x in r['query_ledger'] if not x['supported']]
    assert invalid[0]['channels']['wheel']['delta'] is None
    assert invalid[0]['channels']['wheel']['candidate_reason']=='ambiguous_source'
