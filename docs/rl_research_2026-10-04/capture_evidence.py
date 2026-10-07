"""Freeze existing Nino logs and plot them; does not launch or modify training.

Run from the repository root: .venv/bin/python docs/rl_research_2026-10-04/capture_evidence.py
Rerunning replaces the snapshot, so preserve a copy if comparing later dates.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
import math
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNS = {
    "rough_specialist": "rl_runs/rough_specialist/20261004-130935-610775",
    "flat_pilot": "rl_runs/flat_curriculum_goal_margin/20261004-130945-967736",
    "flat_arrival_guard": "rl_runs/flat_curriculum_arrival_guard/20261004-184722-846090",
}
EVALS = {
    "rough_trial3": "rl_runs/rough_trial3_heldout/20261004-110351-994914/summary.json",
    "rough_trial6": "rl_runs/rough_trial6_heldout/20261004-111746-996777/summary.json",
    "flat_old": "rl_runs/flat_old_clear_comparison/20261004-164659-061413/summary.json",
    "flat_pilot": "rl_runs/flat_pilot_clear_validation/20261004-153537-095341/summary.json",
    "flat_pi": "rl_runs/flat_clear_pi_comparison/20261004-182112-771935/summary.json",
    "guard_targeted": "rl_runs/flat_arrival_guard_targeted/20261004-183803-878376/summary.json",
}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def windows(es, n):
    return {
        "episodes": len(es), "successes": sum(bool(e["success"]) for e in es),
        "success_rate": sum(bool(e["success"]) for e in es) / max(1, len(es)),
        "terminations": dict(Counter(e.get("termination", "unknown") for e in es)),
        "means": {k: sum(float(e[k]) for e in es) / len(es) for k in (
            "truth_path_rmse_m", "truth_endpoint_error_m", "odom_truth_position_error_m",
            "rms_vertical_acceleration_m_s2", "rms_wheel_slip", "rms_wheel_torque_nm",
            "time_seconds", "return") if es and all(k in e for e in es)},
        "window_requested": n,
    }

def model_steps(path):
    if not path.exists():
        return None
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("data"))["num_timesteps"]

def wilson(k, n):
    z = 1.959963984540054
    p = k / n
    a = 1 + z*z/n
    center = (p + z*z/(2*n))/a
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/a
    return [center-half, center+half]

snapshot = {
    "captured_at": datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(),
    "timezone": "Asia/Bangkok", "scope": "Existing logs only; no new robot evaluations",
    "training": {}, "evaluations": {}, "studies": {}, "source_hashes": {},
}
rows = {}
for name, relative in RUNS.items():
    p = ROOT / relative
    raw = (p / "episodes.jsonl").read_bytes()
    lines = raw.splitlines()
    es = []
    for i, line in enumerate(lines):
        try:
            es.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines)-1:
                raise
    rows[name] = es
    checkpoints = sorted((p / "checkpoints").glob("*.zip"), key=lambda q: q.stat().st_mtime)
    snapshot["training"][name] = {
        "run": relative, "log_sha256": digest(raw), "log_bytes": len(raw),
        "completed_episodes": len(es), "latest_logged_step": es[-1]["training_step"],
        "final_checkpoint_steps": model_steps(p / "nino_ppo_final.zip"),
        "latest_checkpoint": str(checkpoints[-1].relative_to(ROOT)) if checkpoints else None,
        "last_stage": es[-1].get("flat_curriculum_stage"),
        "next_stage": es[-1].get("next_flat_curriculum_stage"),
        "all": windows(es, len(es)), "first100": windows(es[:100], 100),
        "last100": windows(es[-100:], 100), "last30": windows(es[-30:], 30),
        "metadata": json.loads((p / "run_metadata.json").read_text()),
        "rolling100": [
            {"step": es[i]["training_step"], "success_rate": sum(bool(e["success"]) for e in es[i-99:i+1])/100}
            for i in range(99, len(es))
        ],
    }
for name, relative in EVALS.items():
    raw = (ROOT / relative).read_bytes()
    summary = json.loads(raw)
    k = summary["termination_counts"].get("success", 0)
    snapshot["evaluations"][name] = {
        "source": relative, "sha256": digest(raw), "summary": summary,
        "success_wilson95": wilson(k, summary["episodes"]),
        "ci_note": "Descriptive binomial interval; episodes are paired, fixed map, one training seed. Not a between-method significance test.",
    }
old_path = ROOT / "artifacts/old_1_5m/episodes.jsonl.gz"
old = [json.loads(l) for l in gzip.decompress(old_path.read_bytes()).splitlines() if l.strip()]
snapshot["old_1_5m"] = {
    "model_steps": model_steps(ROOT / "artifacts/old_1_5m/nino_ppo_final.zip"),
    "logged_episodes": len(old), "first_logged_step": old[0]["training_step"],
    "last_logged_step": old[-1]["training_step"],
    "first500_successes": sum(bool(e["success"]) for e in old[:500]),
    "last500_successes": sum(bool(e["success"]) for e in old[-500:]),
    "log_sha256": digest(old_path.read_bytes()),
    "note": "Logged resumed segment only, not all episodes from the beginning of 1.5M training.",
}
for name in ("combined_rough_optuna_fresh", "combined_flat_optuna_fresh", "flat_curriculum_optuna"):
    with sqlite3.connect(f"file:{ROOT / 'rl_runs' / name / 'study.db'}?mode=ro", uri=True) as c:
        states = dict(c.execute("select state,count(*) from trials group by state"))
        top = []
        for trial_id, number, score in c.execute(
            "select t.trial_id,t.number,v.value from trials t join trial_values v using(trial_id) where t.state='COMPLETE' order by v.value desc limit 3"
        ):
            attrs = {k: json.loads(v) for k,v in c.execute("select key,value_json from trial_user_attributes where trial_id=?", (trial_id,))}
            top.append({"number": number, "objective_score": score, "attributes": attrs})
        snapshot["studies"][name] = {"states": states, "top3": top}
for relative in (
    "src/nino_control/nino_control/effort_drive.py", "src/nino_control/config/effort_drive.yaml",
    "src/nino_rl/nino_rl/control_v2.py", "src/nino_rl/nino_rl/ros_env.py",
    "src/nino_rl/nino_rl/task_geometry.py", "src/nino_rl/nino_rl/policies.py",
    "src/nino_rl/nino_rl/training_contract.py", "src/nino_rl/scripts/tune_split_optuna.py",
    "src/nino_description/urdf/nino.urdf.xacro", "src/nino_description/worlds/combined_hall.sdf",
    "src/nino_description/terrains/combined_rough_ground.stl",
    "src/nino_rl/config/combined_flat_curriculum_arrival_guard.yaml",
):
    snapshot["source_hashes"][relative] = digest((ROOT / relative).read_bytes())
(OUT / "training_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+"\n")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
for ax, name, label in zip(axes[0], ("rough_specialist", "flat_arrival_guard"), ("Rough: tiếp tục từ trial 6", "Flat: học với arrival guard")):
    roll = snapshot["training"][name]["rolling100"]
    ax.plot([r["step"]/1000 for r in roll], [r["success_rate"]*100 for r in roll], color="#176b87", linewidth=2)
    ax.set(title=label, xlabel="Bước đã ghi (nghìn)", ylabel="Thành công / 100 episode gần nhất (%)", ylim=(0, 100))
    ax.grid(alpha=.2)
    if name == "flat_arrival_guard":
        ax.text(.04, .94, "Tất cả episode vẫn ở stage 0 (sàn trống)", transform=ax.transAxes, va="top", fontsize=9)
flat = [snapshot["evaluations"][k] for k in ("flat_old", "flat_pilot", "flat_pi")]
ys = [e["summary"]["success_rate"]*100 for e in flat]
errors = [[y-e["success_wilson95"][0]*100 for y,e in zip(ys,flat)], [e["success_wilson95"][1]*100-y for y,e in zip(ys,flat)]]
ax = axes[1,0]
ax.bar(["PPO cũ 1,5M", "PPO pilot 50k", "PI baseline"], ys, yerr=errors, capsize=5, color=["#98a8b4", "#299d8f", "#df9a36"])
for i,e in enumerate(flat):
    ax.text(i, 5, f"{e['summary']['termination_counts'].get('success',0)}/24", ha="center", color="black", fontweight="bold")
ax.set(title="Đánh giá cố định: cùng 24 seed, sàn trống", ylabel="Thành công (%) + Wilson 95%", ylim=(0, 105))
ax.grid(axis="y", alpha=.2)
ax = axes[1,1]
names = ["PPO cũ 1,5M", "PPO pilot 50k", "PI baseline"]
ax.bar(names, [e["summary"]["metrics_all_episodes"]["truth_path_rmse_m"]["mean"] for e in flat], color=["#98a8b4", "#299d8f", "#df9a36"])
ax.set(title="Sai lệch đường đi vật lý: cùng phép đánh giá", ylabel="Trung bình path RMSE (m)")
ax.grid(axis="y", alpha=.2)
fig.suptitle("Nino - tách dữ liệu học ngẫu nhiên và đánh giá deterministic\nSnapshot: "+snapshot["captured_at"], fontsize=13)
fig.savefig(OUT / "training_progress.png", dpi=180)
plt.close(fig)
print(json.dumps({"captured_at": snapshot["captured_at"], "training": {k: {p:v[p] for p in ("completed_episodes", "latest_logged_step", "final_checkpoint_steps", "last_stage", "first100", "last100", "last30", "all")} for k,v in snapshot["training"].items()}, "studies": snapshot["studies"]}, ensure_ascii=False, indent=2))
