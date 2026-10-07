# Rough route curriculum and Laya

Implemented 2026-10-06. Start a **new policy** for the expanded terrain and drawn
routes. The old short-map rough checkpoint is not resumed as the same task.
The flat-course process can keep running in domain 79.

## Stage transitions

| Stage | Active goals | Terrain |
|---|---|---|
| 0 | E1 | Original, fixed |
| 1 | E1, N1, S1 | Original, fixed |
| 2 | Earlier goals + N2, S2 | Original, fixed |
| 3 | Earlier goals + N3, S3 | Original, fixed |
| 4 | Earlier goals + W1 loop | Original, fixed |
| 5 | All eight | R1 variants: 30% probability per training block |
| 6 | All eight | R2 variants: 60% probability per block |
| 7 | All eight | R3 variants: 80% probability per block |

Earlier routes remain active to reduce forgetting. Training uses balanced
shuffled route cycles; frozen evaluation uses round-robin routes and a
deterministic policy. The route follower supplies steering references to wheel
PI; PPO retains speed scale, common torque residual and differential torque
residual. IMU observation history, terrain preview, reward and PPO parameters
stay consistent across these stages.

Every nominal **20,000 training steps**, the supervisor saves a checkpoint and
evaluates it. Each active route, including earlier routes, must meet all of:

- At least **20 completed evaluation episodes**.
- Physical success **at least 80%**.
- Mean ground-truth path RMSE **at most 0.25 m**, counting failed episodes too.
- Rollover rate **at most 5%**.
- Successful episodes within the configured **0.2 m physical goal tolerance**,
  with every ordered route gate passed. The environment also checks the
  configured **20 degree final heading tolerance**.

Training success averages do not advance stages. In R1–R3, every route must
qualify on **both the original terrain and each reserved validation map for
that level**. Failure keeps the same stage for another training block.

The runner also records a **path follower + wheel PI baseline** on matching
routes, terrain and evaluation seeds, cached once per stage/map. Comparisons
are in `gate.json`. Stage qualification does not establish that RL improves
on PI. Compare physical success, truth path error, slip, torque and vertical
acceleration. Early failure can lower reported error or time.

## Terrain randomization

The bank contains the original map plus **18 variants**: per level, three
training maps, one validation map and two reserved test maps. Split seeds are
disjoint. Training never samples validation or test maps.

| Level | Added relief change | Radius change | Position per axis | Added feature angle |
|---|---|---|---|---|
| R1 | ±10% | ±10% | Fixed | Fixed |
| R2 | ±15% | ±12% | ±0.15 m | ±15° |
| R3 | ±20% | ±15% | ±0.25 m | ±25° |

The rolling background stays fixed. Added features and legacy bowls vary;
legacy bowls remain axis aligned. Each terrain has a shared STL for visual and
collision, without extra objects pretending to be depressions. Spawn, goal
halls, route coordinates and smooth side joins stay fixed. Reject variants
with sampled maximum grade above 0.60 or absolute ground height above 0.33 m.
The generated bank has sampled maximum grade approximately 0.58. Route sampling
checks terrain relief; it does not prove traversability or wheel contact.

**Map changes happen between training blocks**, with a Gazebo restart. Terrain
stays fixed throughout a block's episodes. The probabilities apply to blocks;
other blocks use the original terrain. This finite bank does not establish
adaptation to arbitrary terrain.

Bank file hashes and the declared curriculum are checked on resume. Keep the
bank at its original path. Terrain or route changes require a new bank and
output directory.

## Terminal A: build and start

Stop an existing **rough** simulator in domain 78 in its own terminal first.
The supervisor manages its own Gazebo; do not launch a second rough simulator
alongside it. It refuses an occupied domain/partition and never stops unrelated
processes. Flat training in domain 79 remains independent.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-select nino_description nino_rl
source install/setup.bash
export ROS_DOMAIN_ID=78
export NINO_ROS_DOMAIN_ID=78
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_rough_78

python src/nino_description/scripts/generate_rough_terrain_bank.py \
  --output rl_runs/rough_terrain_bank_v1

python src/nino_rl/scripts/train_rough_curriculum.py \
  --config src/nino_rl/config/rough_route_curriculum.yaml \
  --bank rl_runs/rough_terrain_bank_v1/manifest.json \
  --device cuda --domain 78 \
  --timesteps 500000 --block-steps 20000 --checkpoint-every 10000 \
  --output rl_runs/rough_curriculum_v1
```

The bank already generated for this implementation is reused without rewriting
it. Add `--plan` to validate artifacts and inspect stages without starting
anything. Add `--gui` to see the runner's Gazebo window.

`--timesteps 500000` is the **cumulative training budget**, including saved
steps on resume. Evaluation and baseline episodes are additional work. PPO may
round a block up to a full rollout. Final stage qualification stops training
early. Reaching the budget alone does not mark the curriculum passed; all eight
stages may need more than 500k steps. Full evaluations take substantial wall
time, especially after the longer routes are introduced.

The runner prints its current `train.log` path. Training files are in
`blocks/block_XXXX/train/<timestamp>/`; each block has Gazebo and readiness logs
too. `curriculum_state.json` stores stage, checkpoint, cumulative steps, active
block and last gate. `gate.json` stores complete per-map/per-route evidence and
the baseline comparison.

## Terminal B: Laya tracking

Laya 0.3.22 is already installed in the project environment. On a fresh system,
run `python -m pip install 'laya==0.3.22'` after activating it.

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_rl/scripts/laya_training_monitor.py \
  rl_runs/rough_curriculum_v1 --course rough \
  --watch --interval 120 --window 100 --min-episodes 20 --threads 2 \
  --output rl_runs/laya_monitors/rough_curriculum_v1.jsonl
```

The monitor reads this policy's consecutive training blocks, without adding
evaluation episodes or other Optuna trials. Comparison windows use the current
stage only. It reports per-route statistics, active stage/map, last numerical
gate and Laya's suggested issue. It reports stage changes even while waiting
for the new stage's episodes. It uses CPU with two threads.

Laya advises which issue to inspect; it does **not** modify weights, rewards,
motor commands or stage transitions. Its packaged checkpoint emits a
temperature calibration warning. Confidence is not a calibrated probability,
and the model can disagree with the measured failure counts; the report flags
that disagreement. Read the counts and frozen evaluations before acting on
its label.

Optional TensorBoard in another terminal:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/rough_curriculum_v1/blocks --port 6008
```

Open `http://localhost:6008`. Blocks appear as separate runs with cumulative
policy step numbering. Logs record route ID, stage, map ID and terrain level.

## Stop and resume

Press **Ctrl+C once** in Terminal A. The supervisor asks its trainer to save
`nino_ppo_interrupted.zip`, closes its own Gazebo and saves stage progress.
A power cut loses steps since the last intact checkpoint. Partial ZIPs are
ignored when an earlier intact save exists. Unfinished PPO rollouts are
discarded. Resume restores stage and saved policy progress, without restoring
the exact interrupted episode or simulator state.

After the same Terminal A shell setup:

```bash
python src/nino_rl/scripts/train_rough_curriculum.py \
  --config src/nino_rl/config/rough_route_curriculum.yaml \
  --bank rl_runs/rough_terrain_bank_v1/manifest.json \
  --device cuda --domain 78 --resume \
  --timesteps 500000 --block-steps 20000 --checkpoint-every 10000 \
  --output rl_runs/rough_curriculum_v1
```

To extend a budget-exhausted study, increase the cumulative target, e.g.
`--timesteps 1000000` for approximately one million total steps. Keep config,
bank and output unchanged. Completed evaluation suites are reused after an
interruption; an incomplete map suite is rerun.

## Final unseen-map evaluation

After qualification, evaluate the latest checkpoint on the six reserved test
terrains and all eight routes **without weight updates**:

```bash
python src/nino_rl/scripts/train_rough_curriculum.py \
  --config src/nino_rl/config/rough_route_curriculum.yaml \
  --bank rl_runs/rough_terrain_bank_v1/manifest.json \
  --device cuda --domain 78 --resume --test-only \
  --test-episodes-per-route 20 \
  --output rl_runs/rough_curriculum_v1
```

Results are in `held_out_tests/<checkpoint_hash>/report.json`. Repeatedly tuning
against these results makes those maps development data. Separate new terrain,
sensor/mass/friction variation and hardware testing remain necessary before
claiming broader real-world adaptation.

## Verification

Tests cover stage coverage, physical gates, false odometry goals, forgotten
routes, split isolation, checkpoint contracts and interruption recovery.
Artifact checks verify all generated meshes have finite vertices, upward
normals, flat side joins, and matching visual/collision URIs. Plan validation,
ROS package builds and a real CPU Laya inference were checked. The assistant
has not started a live curriculum training run; these commands are for your
terminal.
