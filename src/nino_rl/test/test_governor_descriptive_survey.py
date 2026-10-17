"""Offline survey contract/orchestration: no simulator subprocess allowed."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import run_governor_descriptive_survey as survey
import run_governor_h2_replication as executor
from prepare_governor_h2_protocol import ROOT,sha,write
from test_governor_h2_analysis import synthetic_batch
from test_governor_h2_executor import good,changed


@pytest.fixture(autouse=True)
def no_processes(monkeypatch,tmp_path):
    def forbidden(*a,**k):raise AssertionError("Offline test cannot start simulator")
    monkeypatch.setattr(executor.subprocess,"Popen",forbidden)
    monkeypatch.setattr(executor.subprocess,"run",forbidden)
    monkeypatch.setattr(survey,"CLAIM_BANK",tmp_path/"claims")


@pytest.fixture
def bundle(tmp_path):
    path=tmp_path/"bundle"
    survey.prepare(ROOT/"docs/governor_h2_replication_protocol_2026-10-17",path)
    return path


def test_new_contract_keeps_parent_app_and_physics_unchanged(bundle):
    parent=ROOT/"docs/governor_h2_replication_protocol_2026-10-17"
    before=json.loads((parent/"protocol.json").read_text())
    p,r=survey.validate_survey(bundle)
    assert p["contract"]!=before["contract"]
    for key in ("schedule","fixed","initialization","outcome_windows","measurement"):
        assert p[key]==before[key]
    assert sha(parent/"application_requirements.json")==sha(bundle/"application_requirements.json")
    assert p["decision"]["primary_metric"] is None and r["criteria_accepted"] is False
    assert r["formal_H2_authorized"] is False
    assert (bundle/"survey_spec.json").is_file()


def test_cannot_confirm_application_or_tamper_release(bundle):
    path=bundle/"application_requirements.json"
    app=json.loads(path.read_text());app["status"]="confirmed";write(path,app)
    with pytest.raises(ValueError):survey.validate_survey(bundle)


def test_formal_H2_release_validator_does_not_accept_descriptive_release(bundle):
    with pytest.raises(ValueError):executor.require_release(bundle,bundle/"survey_release.json")


def test_exact16_fake_cold_starts_and_no_reuse(bundle,tmp_path):
    run=tmp_path/"run";calls=[]
    def fake(job,attempt):
        ledger=json.loads((run/"ledger.json").read_text())["slots"]
        assert ledger[job["attempt"]-1]["launch_requested"] is True
        assert job["cold_start"] is True
        calls.append(job);return good(job)
    result=survey.execute(bundle,run,129,fake)
    assert len(calls)==16 and result["attempted"]==16
    assert result["H2_decision"]=="not_assessed" and result["thresholds_applied"] is False
    assert result["automatic_promotion"] is False
    with pytest.raises(FileExistsError):survey.execute(bundle,tmp_path/"other",129,fake)
    assert len(calls)==16


def test_ordinary_failure_counted_no_replacement(bundle,tmp_path):
    def fake(job,attempt):
        return changed(job,physical_success=False,termination="stall",stop_pass=None,quality_available=False,quality=None) if job["attempt"]==1 else good(job)
    result=survey.execute(bundle,tmp_path/"run",129,fake)
    assert result["attempted"]==16 and result["physical_failures"]==1
    assert result["retries"]==result["replacements"]==0


def test_integrity_stops_batch_without_retry(bundle,tmp_path):
    calls=[]
    def fake(job,attempt):
        calls.append(job);return changed(job,measurement_integrity_pass=False)
    result=survey.execute(bundle,tmp_path/"run",129,fake)
    assert len(calls)==result["attempted"]==1 and len(result["unattempted"])==15


def test_stats_use_exact8_pairs_but_no_application_decision():
    p,slots,criteria,evidence=synthetic_batch()
    report=survey.descriptive_report(p,slots,evidence)
    assert report["H2_decision"]=="not_assessed" and report["thresholds_applied"] is False
    assert report["primary_metric"] is None and report["counts"]["arrivals"]==16
    assert report["estimates"]["post_slip"]["aggregate"]["relative_benefit"]==pytest.approx(.2)
    assert len(report["pairs"])==8


def test_failures_and_missing_values_not_removed_or_zero_filled():
    p,slots,c,e=synthetic_batch()
    slots[0]["result"].update(physical_success=False,termination="timeout",quality=None)
    report=survey.descriptive_report(p,slots,e)
    assert report["counts"]["failures"]==1
    assert report["counts"]["metric_missing"]["post_slip"]==1
    assert report["estimates"]["post_slip"]["aggregate"]["relative_benefit"] is None
    assert len(report["episodes"])==16 and len(report["pairs"])==8


def test_sampling_reversal_is_reported_without_a_chosen_grid():
    p,slots,c,e=synthetic_batch()
    for row in slots:
        if row["profile"]=="reactive":
            row["result"]["quality"]["postcontact"]["shifted10ms"]["slip_square_per_m"]*=2
    report=survey.descriptive_report(p,slots,e)
    assert report["sampling_sensitivity"]["aggregate"]["sign_reversal"] is True
    assert report["H2_decision"]=="not_assessed"


def test_report_is_descriptive_with_all_rows_and_units():
    p,slots,c,e=synthetic_batch()
    text=survey.markdown(survey.descriptive_report(p,slots,e))
    assert "không kết luận H2" in text and "post_slip (s/m)" in text
    assert "77500/1" in text and "77501/4" in text
