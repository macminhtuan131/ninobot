# Step 1: verify rough E1 goal approach with PI

The completed fresh-rough checks had 0/20 physical successes for PI and for
each PPO checkpoint. PI's mean estimated endpoint distance was 0.195 m while
its mean physical endpoint distance was 0.264 m. The original controller
stopped inside the estimated 0.20 m circle. This test targets an estimated
0.05 m circle while retaining the physical 0.20 m success tolerance, heading
checks and ordered route gates. It tests a proposed mitigation; success is not
assumed.

Profile: `src/nino_rl/config/rough_e1_stop_margin_check.yaml`, extending the
existing expanded rough config. E1 is fixed for every episode. Sensors,
physics, terrain, reward and motor settings come from that existing profile.
This is pure path-follower/wheel-PI evaluation, with no PPO weight updates.

## Stop the rough curriculum

Press **Ctrl+C once in the rough curriculum supervisor terminal**, and wait
for checkpoint saving and simulator shutdown. Only one controller/test may
use its domain 78. The flat session uses domain 79.

## Terminal A: original bank terrain

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_rough_78

ros2 launch nino_rl training_sim.launch.py \
  world:="$PWD/rl_runs/rough_terrain_bank_v1/worlds/original.sdf" \
  world_name:=combined_rough_section headless:=true
```

Use `headless:=false` to view Gazebo. This launches the same original bank world
used in the failed curriculum evaluations.

## Terminal B: wait for readiness and evaluate

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_rough_78

ros2 run nino_rl wait_for_sim
ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/rough_e1_stop_margin_check.yaml \
  --episodes 20 --seed 10000 \
  --output rl_runs/rough_e1_stop_margin_pi
```

Seeds 10000–10019 match the previous PI evaluation. Each completed episode
prints its physical goal result. Reports include `summary.json`, `episodes.csv`
and per-episode estimated/physical trajectory plots under the timestamped
output directory. The different navigation setting changes the benchmark hash;
the old and new summaries describe a deliberate controller intervention.

Read the newest completed result:

```bash
python - <<'PY'
from pathlib import Path
import json
path = max(Path('rl_runs/rough_e1_stop_margin_pi').glob('*/summary.json'),
           key=lambda p: p.stat().st_mtime)
report = json.loads(path.read_text())
print('Report:', path)
print('Complete:', report['complete'])
print('Success:', report['success_rate'])
print('Outcomes:', report['termination_counts'])
print('Physical endpoint error:',
      report['metrics_all_episodes']['truth_endpoint_error_m']['mean'], 'm')
PY
```

Require a complete 20-episode result. A provisional target is at least **16/20
physical successes**; also inspect trajectory/heading failures. If that passes,
prepare corrected curriculum training and repeat qualification with the new
settings. If it fails, inspect the trajectories and odometry before further
long training or Optuna search.

The changed stop margin changes the training contract. An existing curriculum
study cannot silently resume with this setting. Corrected training needs a new
output directory and may initialize a compatible saved actor with
`--init-model`; its critic/optimizer start fresh. This PI test does not change
the existing training configs or checkpoints.

Verification: the probe config was checked against its parent, with only E1
selection and the stopping threshold changed. The original config commands
zero speed at 0.19 m estimated distance, while this probe continues moving
until inside 0.05 m. The 16 existing goal/arrival regression tests passed and
the RL package was rebuilt. Live PI results are produced by the commands
above.

## Completed PI check and next saved-policy evaluation (2026-10-07)

The corrected PI check completed **20/20 physical successes** on E1, with mean
physical path RMSE **0.0428 m**, mean physical endpoint error **0.1963 m**, and
mean episode time **27.76 s**. Saved report:
`rl_runs/rough_e1_stop_margin_pi/20261007-074629-284396/summary.json`.
This improvement comes from the goal-approach setting. PPO under this setting
still needs evaluation.

The expanded-map rough checkpoint saved at **112,589 steps** is intact and
compatible with this diagnostic config. Reopen the original-bank simulator
using Terminal A above. In Terminal B, with the same domain 78/partition setup,
evaluate that existing policy on the same twenty seeds:

```bash
ros2 run nino_rl wait_for_sim
ros2 run nino_rl evaluate --device cuda \
  --config src/nino_rl/config/rough_e1_stop_margin_check.yaml \
  --model rl_runs/rough_curriculum_v1/blocks/block_0005/train/20261007-071733-924985/nino_ppo_interrupted.zip \
  --route E1 --episodes 20 --seed 10000 \
  --output rl_runs/rough_e1_stop_margin_ppo
```

This runs deterministic inference using the saved actor, with its full speed
and torque actions. Its weights stay frozen. Flat speed-only evaluation can
continue separately in domain 79/partition `nino_flat_79`.

After all twenty episodes complete, compare the newest summary with the saved
corrected PI reference:

```bash
python - <<'PY'
from pathlib import Path
import json
from nino_rl.evaluation import compare_summaries

baseline_path = Path('rl_runs/rough_e1_stop_margin_pi/20261007-074629-284396/summary.json')
candidate_path = sorted(Path('rl_runs/rough_e1_stop_margin_ppo').glob('*/summary.json'))[-1]
result = compare_summaries(json.loads(baseline_path.read_text()),
                           json.loads(candidate_path.read_text()))
result.update(baseline_summary=str(baseline_path.resolve()),
              candidate_summary=str(candidate_path.resolve()))
output = candidate_path.parent / 'comparison_vs_pi.json'
output.write_text(json.dumps(result, indent=2) + '\n')
print('Comparison:', output)
print('Physical success:', result['success_rate'])
print('Physical path RMSE:', result['metrics']['truth_path_rmse_m'])
PY
```

Use this evidence to decide whether to retain the rough actor for corrected
curriculum training. Preserve the old study; applying the new stopping margin
to training changes its task contract and needs a new output/profile with
actor initialization rather than a direct resume of the old ledger.

## Recovering startup after an interrupted evaluation

If startup reports all of `imu, joint, odom, scan` missing while the rough
simulator remains present, check whether its world is paused. The 2026-10-07
startup fix discovers the effort-drive subscriber, sends stopped motor
commands, resumes physics to receive initial sensor/preview samples, then
pauses for policy construction. It prevents waiting indefinitely for sensor
samples from a paused world. This changes startup recovery, not the reward or
policy action mapping. The package was rebuilt and 64 control/integration
regressions passed. Re-source `install/setup.bash` and rerun the evaluation;
do not launch a second rough world against the existing session.

## Laya tracking for the saved rough PPO evaluation

In another terminal:

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_rl/scripts/laya_training_monitor.py \
  rl_runs/rough_e1_stop_margin_ppo --course rough \
  --watch --interval 60 --window 20 --min-episodes 5 --threads 1 \
  --output rl_runs/laya_monitors/rough_goal_margin_ppo.jsonl
```

This reads the newest evaluation CSV, including E1 physical tracking and goal
errors. It waits for the first completed episode and starts Laya advisories
after five episodes. It is a CPU log reader, so no ROS domain setup is needed
for the monitor. Keep the evaluator in domain 78 as shown above. The policy
remains frozen; Laya's issue label is advisory and its confidence is
uncalibrated. The completed PI/PPO comparison determines training decisions.
