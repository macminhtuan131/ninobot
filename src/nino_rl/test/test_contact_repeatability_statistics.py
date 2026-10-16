"""Small repeated screens must not manufacture replication or zero-valued data."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from summarize_contact_repeatability import exact_sign_flip, paired_metrics


def test_five_agreeing_blocks_cannot_reach_two_sided_point_zero_five():
    result=exact_sign_flip([-1,-2,-3,-4,-5])
    assert result["permutations"]==32
    assert result["two_sided_p"]==.0625
    assert result["favorable_blocks"]==5


def test_missing_metric_is_not_zero_and_acted_prefix_is_not_negative_control():
    rows=[dict(seed=1,profile="full",time_s=10.,first_50ms_peak=20.,first_50ms_uncontrolled=True),
          dict(seed=1,profile="moderate",time_s=11.,first_50ms_peak=5.,first_50ms_uncontrolled=False),
          dict(seed=2,profile="full",time_s=10.,physical_success=False)]
    results=paired_metrics(rows,[1,2])
    assert results["time_s"]["available_blocks"]==1
    assert results["time_s"]["unavailable_or_ineligible_seeds"]==[2]
    assert results["first_50ms_peak"]["available_blocks"]==0
    assert results["first_50ms_peak"]["exploratory_sign_flip"] is None


def test_deliberately_different_approach_is_not_a_negative_control():
    rows=[dict(seed=1,profile=p,time_s=t,first_50ms_peak=impact,first_50ms_uncontrolled=True)
          for p,t,impact in (("full",17.,6.),("moderate",17.1,12.))]
    metrics=paired_metrics(rows,[1],prefix_comparable=False)
    assert metrics["first_50ms_peak"]["available_blocks"]==0
    assert metrics["time_s"]["available_blocks"]==1
