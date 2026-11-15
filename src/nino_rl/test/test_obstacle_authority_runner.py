"""No-release, slot consumption, review and closure fault injection. No physics."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from nino_rl import obstacle_authority_draft as draft
from nino_rl import obstacle_authority_runner as runner


def save(path, data): path.write_text(json.dumps(data))


def test_disabled_template_rejects_before_creating_root(tmp_path):
    root = tmp_path / "never_created"
    path = draft.ROOT / "src/nino_rl/config/fixed6mm_postmanifold_runtime_release_v1.json"
    with pytest.raises(ValueError, match="No E2 physics allocation"): runner.run_next(root, path)
    assert not root.exists()


@pytest.mark.parametrize("status", ["running", "awaiting_review", "closed_failed", "completed_pending_comparison"])
def test_state_must_be_reviewed_ready(status):
    with pytest.raises(ValueError, match="review"):
        runner.next_slot(dict(status=status), draft.load())


def test_slots_are_ordered_bounded_and_require_review_hash():
    plan = draft.load(); state = dict(status="ready", attempts=[], consumed_wall_s=0)
    assert runner.next_slot(state, plan)["id"] == "E2-01"
    state["attempts"] = [dict(slot=plan["proposed_attempts"][0], summary_sha256="a")]
    with pytest.raises(ValueError, match="reviewed"): runner.next_slot(state, plan)
    state["attempts"][0]["reviewed_summary_sha256"] = "a"
    assert runner.next_slot(state, plan)["id"] == "E2-02"
    state["consumed_wall_s"] = 3600
    with pytest.raises(ValueError, match="wall"): runner.next_slot(state, plan)
    state["consumed_wall_s"] = 0
    state["attempts"][0]["slot"] = plan["proposed_attempts"][1]
    with pytest.raises(ValueError, match="order"): runner.next_slot(state, plan)


def test_failure_consumes_one_slot_and_closes_without_retry(tmp_path, monkeypatch):
    root = tmp_path / "runtime"; release = tmp_path / "release.json"; save(release, {})
    monkeypatch.setattr(runner, "require_release", lambda *_: dict(allocated_attempts=12))
    monkeypatch.setattr(runner, "preflight", lambda *_: {})
    import nino_rl.residual_sim_pilot as parent
    monkeypatch.setattr(parent, "prepare_worlds", lambda *_: {"box_c1_6mm":"fixture.sdf"})
    monkeypatch.setattr(runner, "verify_world", lambda *_: {})
    calls = []
    def failed(*args):
        calls.append(args); raise RuntimeError("injected closure failure")
    monkeypatch.setattr(runner, "evaluate_attempt", failed)
    with pytest.raises(RuntimeError, match="closure"): runner.run_next(root, release)
    state = runner.read(root / "ledger.json")
    assert state["status"] == "closed_failed" and len(state["attempts"]) == 1
    assert runner.read(root / "E2-01/manifest.json")["status"] == "failed"
    with pytest.raises(ValueError, match="review"): runner.run_next(root, release)
    assert len(calls) == 1


def test_preclaim_readiness_failure_consumes_no_slot(tmp_path, monkeypatch):
    release = tmp_path / "release.json"; save(release, {})
    root = tmp_path / "root"
    monkeypatch.setattr(runner, "require_release", lambda *_: dict(allocated_attempts=12))
    def fail(*_): raise ValueError("disk low")
    monkeypatch.setattr(runner, "preflight", fail)
    with pytest.raises(ValueError, match="disk"): runner.run_next(root, release)
    assert not (root / "ledger.json").exists()


def test_review_cannot_accept_a_changed_summary(tmp_path):
    slot = draft.load()["proposed_attempts"][0]
    target = tmp_path / slot["id"]; target.mkdir()
    save(target / "summary.json", dict(status="measurement_pass_pending_review"))
    digest = runner.sha(target / "summary.json")
    save(target / "manifest.json", dict(status="measurement_pass", files={"summary.json":digest}))
    save(tmp_path / "ledger.json", dict(status="awaiting_review", attempts=[dict(slot=slot, summary_sha256=digest)]))
    with pytest.raises(ValueError, match="hash"): runner.review_slot(tmp_path, "wrong")
    state = runner.review_slot(tmp_path, digest)
    assert state["status"] == "ready" and state["attempts"][0]["reviewed_summary_sha256"] == digest
    with pytest.raises(ValueError, match="awaiting"): runner.review_slot(tmp_path, digest)


def test_qualification_requires_both_runtime_and_runner_tests_without_skips(tmp_path):
    path=tmp_path/"test.xml"
    path.write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"><testcase classname="test_obstacle_authority_runtime"/><testcase classname="test_obstacle_authority_runner"/></testsuite></testsuites>')
    assert runner.require_test_report(path)["tests"] == 2
    path.write_text(path.read_text().replace('skipped="0"', 'skipped="1"'))
    with pytest.raises(ValueError, match="not passed"): runner.require_test_report(path)
    path.write_text('<testsuites><testsuite tests="1"><testcase classname="other"/></testsuite></testsuites>')
    with pytest.raises(ValueError, match="coverage"): runner.require_test_report(path)


@pytest.mark.parametrize("mutation", ["none", "root", "identity", "rules", "slots", "qualification", "tests"])
def test_release_requires_current_bound_sources_and_evidence(tmp_path, monkeypatch, mutation):
    ident = dict(id="fixture_only")
    monkeypatch.setattr(runner.context, "identity", lambda:ident)
    xml=tmp_path/"tests.xml"
    xml.write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"><testcase classname="test_obstacle_authority_runtime"/><testcase classname="test_obstacle_authority_runner"/></testsuite></testsuites>')
    q=tmp_path/"qualification.json"
    save(q, dict(status="offline_e2_runtime_qualified_not_Gazebo",identity=ident,
                 software_tests=runner.require_test_report(xml)))
    save(tmp_path/"manifest.json",dict(status="completed",files={q.name:runner.sha(q)}))
    root=tmp_path/"run"
    release=dict(protocol_id=draft.PROTOCOL_ID,runtime_id=runner.context.CONTEXT_ID,
        released=True,decision_rules_accepted=True,allocated_attempts=12,
        allowed_slot_ids=[s["id"] for s in draft.load()["proposed_attempts"]],
        retries=0,hardware_actions=0,optimizer_updates=0,root=str(root),
        protocol_sha256=runner.sha(draft.PLAN_PATH),identity=ident,
        qualification=str(q),qualification_sha256=runner.sha(q))
    if mutation=="root":release["root"]=str(tmp_path/"elsewhere")
    elif mutation=="identity":release["identity"]={}
    elif mutation=="rules":release["decision_rules_accepted"]=False
    elif mutation=="slots":release["allowed_slot_ids"]=["E2-01"]*12
    elif mutation=="qualification":q.write_text("{}")
    elif mutation=="tests":xml.write_text("<testsuites/>")
    path=tmp_path/"release.json";save(path,release)
    if mutation=="none":assert runner.require_release(path,root)==release
    else:
        with pytest.raises(ValueError):runner.require_release(path,root)


def test_nominal_world_validation_rejects_changed_radius(tmp_path):
    path=tmp_path/"world.sdf"
    text='''<sdf><world><model name="enclosed_hall"/><model name="controlled_box_floor"><link><collision><surface><friction><ode><mu>1.0</mu></ode></friction></surface></collision></link></model><model name="cable_bumps"><link><collision name="C1_collision"><pose>0.65 0 0.003 1.57079632679 0 0</pose><geometry><cylinder><radius>0.003</radius></cylinder></geometry></collision></link></model></world></sdf>'''
    path.write_text(text)
    assert runner.verify_world(path)["randomized"] is False
    path.write_text(text.replace("<radius>0.003", "<radius>0.011"))
    with pytest.raises(ValueError,match="geometry"):runner.verify_world(path)


def test_one_slot_prefix_exhausts_without_launching_next(tmp_path, monkeypatch):
    release=tmp_path/'release.json';save(release,{})
    root=tmp_path/'root';root.mkdir()
    slot=draft.load()['proposed_attempts'][0]
    save(root/'ledger.json',dict(status='ready',allocated_attempts=1,release_sha256=runner.sha(release),
        consumed_wall_s=1.,attempts=[dict(slot=slot,summary_sha256='a',reviewed_summary_sha256='a')]))
    monkeypatch.setattr(runner,'require_release',lambda *_:dict(allocated_attempts=1))
    monkeypatch.setattr(runner,'preflight',lambda *_:pytest.fail('Unallocated slot reached preflight'))
    with pytest.raises(ValueError,match='prefix exhausted'):runner.run_next(root,release)
