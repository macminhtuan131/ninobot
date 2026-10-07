# Flat stage 2: PPO speed-only check

The frozen 952,343-step final policy scored 11/24 physical successes versus
23/24 for PI on seeds 60000–60023. Before more training, test the same saved
policy with its additive torque corrections disabled.

`--speed-only` preserves the policy's speed action and replaces its forward
and differential torque actions with zero before actuation and action-history
updates. PI still supplies motor torque to track the scaled speed reference.
Residual torque noise is also suppressed. The policy is evaluated
deterministically, without weight updates. The reward formula, goal checks,
deadline, cable stage, and saved model remain unchanged.

This is a closed-loop controller ablation: changed motion and recorded action
history can change subsequent speed predictions. It is not a replay of the
original run's speed commands.

## Prepare the terminal

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-select nino_rl
source install/setup.bash
export ROS_DOMAIN_ID=79
export NINO_ROS_DOMAIN_ID=79
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_flat_79
```

## Simulator

Use the existing flat simulator if it is still running. Start this command in
a separate terminal with the same setup only if that simulator has stopped:

```bash
ros2 launch nino_rl combined_flat_section_training.launch.py headless:=true
```

Run one evaluator at a time on this simulator. The rough simulator uses its
own domain and partition.

## Run the speed-only evaluation

```bash
ros2 run nino_rl evaluate --device cuda \
  --config rl_runs/flat_arrival_guard_200k/20261006-230417-364560/ppo.yaml \
  --model rl_runs/flat_arrival_guard_200k/20261006-230417-364560/nino_ppo_final.zip \
  --flat-stage 2 --speed-only --episodes 24 --seed 60000 \
  --output rl_runs/flat_stage2_speed_only
```

This fixes the two-cable stage, angles within ±2°, no adaptive items, and no
easier-stage replay. Broader domain randomization is disabled, as in the
existing PI/PPO evaluation. Expect roughly 15–20 minutes at the previously
measured simulator pace, depending on episode lengths and system load.

The terminal prints the timestamped output directory at completion. Each
episode saves its physical trajectory and metrics. Metadata identifies this
controller as `ppo_speed_only`. Its `config.yaml` records the diagnostic
mask; use the original saved `ppo.yaml` for any future training.

## Compare with both completed reference evaluations

Run after all 24 episodes complete:

```bash
python - <<'PY'
import json
from pathlib import Path
from nino_rl.evaluation import compare_summaries

reference = Path("rl_runs/flat_stage2_comparison_952343_20261007")
ablation = Path("rl_runs/flat_stage2_speed_only")
provenance = json.loads((reference / "comparison.json").read_text())
candidate_path = sorted(ablation.glob("*/summary.json"))[-1]
candidate = json.loads(candidate_path.read_text())

for label, key in [("pi", "baseline_summary"), ("full_ppo", "candidate_summary")]:
    baseline = json.loads(Path(provenance[key]).read_text())
    result = compare_summaries(baseline, candidate)
    result.update(baseline_summary=provenance[key], candidate_summary=str(candidate_path.resolve()))
    output = candidate_path.parent / f"comparison_vs_{label}.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Compared with {label}: {output}")
    print("Physical success:", result["success_rate"])
    print("Physical path RMSE:", result["metrics"]["truth_path_rmse_m"])
PY
```

The comparator rejects incomplete or mismatched evaluations. The speed-only
mask is a controller change, so it does not change the task benchmark hash.

## Decision

- If success and tracking recover toward PI, investigate torque correction
  strength or a bounded yaw-reference action before another long run.
- If speed-only remains poor, inspect the learned speed schedule and goal
  approach; removing torque alone does not establish either as the cause.
- Keep physical goal checks intact. Both reference controllers exhibit
  odometry drift, including premature arrival stops.

Check success first, then physical tracking, slip, and impacts. A slower run
or early failure can lower some comfort metrics. This stage alone does not
qualify the full six-cable/adaptive-item course.

## Laya tracking during this evaluation

In another terminal:

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_rl/scripts/laya_training_monitor.py \
  rl_runs/flat_stage2_speed_only --course flat \
  --watch --interval 60 --window 24 --min-episodes 5 --threads 1 \
  --output rl_runs/laya_monitors/flat_speed_only.jsonl
```

The monitor reads the newest evaluation's `episodes.csv`, converts its boolean
and numeric fields, and excludes unfinished CSV rows. It reports frozen
evaluation status, controller name, physical errors, slip, impacts, and failure
counts. It keeps independent runs separate. Existing training JSONL and rough
curriculum block monitoring are still supported.

Laya runs on CPU and offers an issue label after at least five completed
episodes. Its packaged confidence values are uncalibrated. Numerical results
and the PI comparison determine the next action; Laya does not modify the
policy, controller, reward, or evaluation settings. Episode-to-episode changes
here are evaluation variation, not learning.
