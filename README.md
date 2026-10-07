# Nino: straight-line residual PPO and trajectory evaluation

**New rocky-terrain experiment:** [diagnosis, map, and training commands](docs/ROCKY_TRACKING.md).
It keeps the original 4 m hall width and 6 m goal distance, uses broad rolling
terrain across the hall, and trains trajectory stabilization with physical
simulation scoring and PI yaw-reference control. Select `rocky_tracking.yaml`
and `rocky_training.launch.py` together. The cable workflow below remains
available with its original map and configuration.

This branch controls the **caster-supported differential-drive Nino AMR** in
ROS 2 Jazzy / Gazebo Harmonic. The model has two powered wheels, two passive
casters, IMU, wheel encoders and **2D** LiDAR. It is not an unsupported two-wheel
inverted pendulum. Nav2 is disabled for this experiment. The cable workflow
uses a direct `/cmd_vel` reference, wheel-speed PI, and bounded differential
PPO torque. The Rocky Hall profile instead gives PPO a yaw reference that the
PI loop tracks, along with forward speed scaling and bounded common torque.

The updated workflow uses NVIDIA CUDA by default and refuses an automatic CPU
fallback. Gazebo physics and ROS still consume CPU; this is one Gazebo world,
not GPU-parallel Isaac Lab simulation. Keep only one train/evaluate/policy
process connected to that world at a time.

Nino simulation processes automatically use ROS domain 77 with localhost-only
discovery, preventing another machine or simulator from injecting a conflicting
`/clock`. To use manual `ros2 topic` or `ros2 service` diagnostics, first run
`export ROS_DOMAIN_ID=${NINO_ROS_DOMAIN_ID:-77}` and
`export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` in that shell.

- [Reward, policy and engineering decisions](src/nino_rl/RL_IMPROVEMENTS.md)
- [Timeout diagnosis and revision 27 validation](docs/RL_TRAINING_DIAGNOSIS_20260922.md)
- [Goal-first reward, policy and terrain curriculum (revision 30)](docs/RL_GOAL_FIRST_REVISION_28.md)
- [Vietnamese quick guide](src/nino_rl/README_VI.md)
- [Bài viết nghiên cứu tổng quan bằng tiếng Việt](docs/BAO_CAO_NGHIEN_CUU_RL_NINO.md)
- [Báo cáo tiến độ 04/10/2026: số liệu, roadmap, so sánh PID/Nav2/RL và 32 công trình](docs/BAO_CAO_TIEN_DO_VA_DOI_CHIEU_RL_NINO_2026-10-04.md)
- [Simulation and hardware reference](docs/HARDWARE_REFERENCE.md)
- [Raspberry Pi deployment guide](docs/RASPBERRY_PI_DEPLOYMENT.md)

The cable workflow uses training contract revision 30; Rocky Hall uses revision
31, and the combined rough-to-flat course uses revision 32. Because the cable contract's goal-distance reward,
restored full-size terrain, per-action exploration, physics-completion timing,
sensor-invisible goal marker, reward balance,
traversable-challenge flags, terrain geometry, downward preview, and rolling
hazard curriculum changed, older checkpoints cannot be resumed; start a new
run. New checkpoints retain rolling curriculum state, so
resume no longer resets hazard difficulty. Old models may still be used for
inference with their matching config. Old 54-input/2-action models are
incompatible. The `Completed_train` branch includes [trained weights and recorded training
results](src/nino_rl/models/completed_train/README.md). The final checkpoint has
1,001,634 cumulative steps; held-out performance gains and hardware transfer
have not been established.

## Combined course: rough ground, then the old flat cable hall

The separate `combined_hall.sdf` starts with real shallow depressions and mounds
from x=0.8 to 6.72 m. The surface meets a level floor at x=6.72 m; the old
hall's six cables run from x=7.2 to 12.0 m, and the goal is at x=13 m.
There are no cables beyond the goal in this world. The rough
ground's visual and collision use the same mesh. Nine pothole bowls are dug
into that mesh from y=-1 m to y=1 m: the three 7 cm route bowls are at
y=+0.30, 0.00, and -0.10 m. Six
additional bowls are 2.5–7.5 cm deep
across the rough section. They are physical depressions, with no separate
pothole objects. Selected potholes, mounds, and cables are also counted by
the challenge reward when the wheels cross them.
The bowl near x=4.72 m is centered at y=-0.40 m.
The uphill exit from the middle bowl near x=3.55 m is widened and locally
smoothed to reduce the sudden pitch change; its hollow remains in the mesh.
Two smaller 2.2 cm-deep bowls span 30 cm along the route for the 12.5 cm drive
wheels, and two 6 mm-deep bowls span 12 cm for the 3.2 cm casters. They sit along
the corresponding wheel tracks. The ground mesh samples every 2 cm along the
route so these small holes have actual contact geometry. During combined-course
training, the old adaptive spawner also adds pothole, bump, short-cable, and
groove surrogates on the flat section. It starts with one item and adds one
after five consecutive successful episodes, up to six. Each episode randomizes
their positions within x=7.1–12.2 m and y=-0.5–0.5 m. At each episode reset,
the six course cables keep their centers and radii but receive independent
angles uniformly sampled from −30° to +30°. The fixed-angle cables in the
world file are only the layout shown before training starts. Runtime potholes
are raised-rim surrogates, while the rough
section's potholes are actual depressions in its ground mesh.
See the [annotated combined-world preview](docs/combined_world_preview.png)
for the potholes, smoothed uphill exit, wheel holes, seam, and cables.

**The old wheel-torque policy can initialize this course**, since both use the
same 300-value observation, three-action policy and wheel-torque action meaning.
Use `--init-model` for a new run. It copies the actor and its exploration
scales; the critic and optimizer start fresh because the goal and reward have
changed. The new run starts at step zero with a 13 m goal and new reward/task
contract. `--resume` is only for continuing a checkpoint on its original
course with the matching saved config. Rocky Hall's yaw-reference policy has a
different third action and cannot initialize this wheel-torque course. Choose
an old checkpoint by evaluation on held-out episodes; the latest checkpoint is
not necessarily the best. The old 1.5M-step run improved from 41% success in
its first 500 recorded resumed episodes to 78% in its last 500, so its final
checkpoint is a stronger starting candidate than the earlier 1.0M-step one.
These rates were measured on the old hall, not the combined course.
On three paired combined-course evaluation seeds, both old checkpoints scored
0/3 successes, although the 1.5M-step model had lower physical path error
(0.269 m versus 0.531 m). The main observed failure was stopping at the
wheel-odometry goal while the physical robot was still short. A trial with a
slow goal-search command also scored 0/3 and increased off-path failures, so
it was not adopted. Better localization or further task-specific training is
needed before claiming a success improvement on the combined course.
The first 2,048-step actor-only warm-start smoke run had 0/7 episode successes
and stopped its first PPO update after one of five epochs at a 0.0001 learning
rate because it reached the KL limit. At 0.00003, the first update completed
all five epochs, while its pre-update rollout had 0/6 successes. The combined
profile now uses 0.00003 for gentler adaptation. These short rollouts do not
establish a performance gain; evaluate the trained policy on held-out episodes.

Finish and stop the currently running old trainer and its Gazebo world before
launching this one. Generate and build the course from the project directory:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python src/nino_description/scripts/generate_combined_world.py
python -m colcon build --symlink-install --packages-select nino_description nino_rl
source install/setup.bash
```

In **each new terminal**, run this setup before a combined-course ROS command:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=${NINO_ROS_DOMAIN_ID:-77}
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

Start Gazebo in terminal A and keep it running while training or evaluating.
Use `headless:=true` if you do not need the Gazebo window:

```bash
ros2 launch nino_rl combined_training.launch.py headless:=false
```

In terminal B, check the pipeline with a short warm-start run:

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_course.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 4096 --check-env --output rl_runs/combined_course_smoke
```

After the smoke run ends, train longer in terminal B with a separate output
directory:

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_course.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 500000 --checkpoint-every 25000 \
  --output rl_runs/combined_course
```

Do not run two trainers against the same Gazebo world. In terminal C, view
learning curves at `http://localhost:6007`:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/combined_course --port 6007
```

To continue a combined-course checkpoint later, use its saved `ppo.yaml` and
`--resume` with the checkpoint instead of `--init-model`.

After training, keep the combined world running and evaluate with new seeds:

```bash
ros2 run nino_rl evaluate --device cuda --episodes 20 --seed 10000 \
  --config rl_runs/combined_course/<run-id>/ppo.yaml \
  --model rl_runs/combined_course/<run-id>/nino_ppo_final.zip \
  --output rl_runs/combined_evaluation
```

### Tune the combined course with Optuna

#### Tune its two sections separately

`combined_rough_section.sdf` now preserves the original rough ground from
x=0.8 to 5.7 m inside y=-2..2 m and adds terrain to **x=10 m, y=-4..4 m**.
The rough patch is **8 m wide**, surrounded by connected flat goal halls.
The full enclosure spans **x=-2..12 m, y=-7.2..7.2 m**. North and south halls
are 2 m wide, reached through 1.2 m smooth side ramps; west and east halls
connect around the corners. Its dedicated
`rough_diverse_ground.stl` is shared by visual and collision. The extension
uses the same rolling-terrain generator as the first 1–6 m, with continuous
hills, valleys and asymmetric relief between **32 added sculpted features**:
round and flat-bottom depressions, angled
troughs, rounded and banked mounds, low plateaus, a mound–bowl pair, and staggered drive-wheel
and caster bowls. There is a flat landing at x=10..12 m.

See [the goal-hall overview](docs/rough_goal_halls_preview.png) for eight optional
goal stations (west, east, three north, three south). The green floor markers
have no collision. The rough config now uses **eight user-drawn routes**:
six L routes, straight E1, and the long clockwise loop to W1. Training selects
each route once per shuffled eight-episode cycle. Evaluation cycles through
all eight in a fixed order. See [the configured route preview](docs/rough_routes_preview.png)
and [route details and commands](docs/ROUGH_DRAWN_ROUTES.md).

**Route curriculum:** [start, resume, terrain variants and Laya commands](docs/ROUGH_ROUTE_CURRICULUM.md).
Use `rough_route_curriculum.yaml` with `scripts/train_rough_curriculum.py` to
start with E1, retain earlier goals while adding N1/S1, N2/S2, N3/S3 and W1,
then introduce bounded R1–R3 terrain variants. Every active route must pass a
complete physical evaluation before advancing. The runner manages Gazebo in
domain 78 and records matching path-PI comparisons. Laya reports per-route
issues and stage progress; numerical evaluation controls advancement. Maps
change between training blocks. The direct `combined_rough_section.yaml`
workflow still selects all routes at once.

**E1 arrival diagnostic:** [PI test with a 0.05 m estimated stop margin](docs/ROUGH_E1_STOP_MARGIN_CHECK.md).
Use this check when both PI and PPO stop near the estimated goal and time out
outside the physical 0.20 m success circle. It evaluates the original bank
terrain on E1 with matching seeds before starting further training.

See [the annotated rough preview](docs/rough_diverse_preview.png) and
[feature coordinates and heights](docs/ROUGH_TERRAIN_FEATURES.md) when drawing
new trajectories. Added depressions range from 6 mm to 12 cm deep and
mounds from 3.5 to 14 cm high. These values are added carving/rise relative to
the underlying rolling terrain, not absolute ground elevations. The route
coordinates are stored directly in `combined_rough_section.yaml`. An odometry
path follower supplies the turning reference; PPO retains its speed scale and
wheel torque residual actions. Ordered spatial gates and simulator pose check
route completion, preventing a shortcut to the nearby west goal. Progress
reward and goal braking use along-route distance. Episode time limits scale
with route length. Feature annotations are not mandatory reward checkpoints;
the rough config clears the obsolete five-region challenge list.

`combined_flat_section.sdf` has a flat floor and the same six
course cables, shifted into a local route from x=0 to 6.45 m. Its local cable
positions x=0.65..5.45 m correspond to x=7.2..12 m in the combined world. This
local origin keeps the robot's reset wheel odometry aligned with its goal and
reward. The flat config
also keeps the per-episode cable angles and adaptive items. Each section has a
different world name, task, config, and Optuna database. The split generator
reads `combined_hall.sdf`, then builds the extended rough mesh and isolated
flat world. The combined course keeps its original geometry and goal; its
transition does not automatically move to the extended rough course's endpoint.
Use a new rough run/study for this geometry revision. Old rough checkpoints can
be considered for compatible actor initialization, rather than continuing the
old benchmark with `--resume`.

To regenerate **only rough** and its annotated preview:

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_description/scripts/generate_split_worlds.py --section rough
python src/nino_description/scripts/preview_rough_section.py
```

Prepare from the repository root:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python src/nino_description/scripts/generate_split_worlds.py
python src/nino_description/scripts/preview_rough_section.py
python -m colcon build --symlink-install --packages-select nino_description nino_rl
source install/setup.bash
python -m pip install optuna
export ROS_DOMAIN_ID=78
export NINO_ROS_DOMAIN_ID=78
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_rough_78
```

In terminal A, launch the **rough** section. In terminal B, repeat the setup
above (including both domain variables), run a short check, then tune it:

```bash
ros2 launch nino_rl combined_rough_section_training.launch.py headless:=true
```

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_rough_section.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 2048 --check-env --output rl_runs/rough_section_smoke

python src/nino_rl/scripts/tune_split_optuna.py --section rough \
  --trials 12 --timesteps 50000 --eval-episodes 12 \
  --output rl_runs/rough_diverse_optuna_v5
```

For a sequential run, stop rough Gazebo before starting the **flat cable**
section. For a concurrent run, leave it running. Use domain 79 in both flat
terminals (`ROS_DOMAIN_ID=79` and
`NINO_ROS_DOMAIN_ID=79`) and set `GZ_PARTITION=nino_flat_79`, then launch and tune:

```bash
ros2 launch nino_rl combined_flat_section_training.launch.py headless:=true
```

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_section.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 2048 --check-env --output rl_runs/flat_section_smoke

python src/nino_rl/scripts/tune_split_optuna.py --section flat \
  --trials 12 --timesteps 50000 --eval-episodes 12 \
  --output rl_runs/combined_flat_optuna_v2
```

To run **both sections at the same time**, keep four terminals open. Use the
setup block below in each terminal, replacing `SECTION` and `DOMAIN` as shown:

| Terminals | SECTION | DOMAIN | Command after setup |
| --- | --- | ---: | --- |
| A (rough simulator), B (rough tuner) | `rough` | 78 | Commands below |
| C (flat simulator), D (flat tuner) | `flat` | 79 | Commands below |

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=78                 # use 79 in flat terminals
export NINO_ROS_DOMAIN_ID=$ROS_DOMAIN_ID
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_rough_78       # use nino_flat_79 in flat terminals
```

Start the simulators in A and C, then the tuners in B and D. The rough and flat
commands are the launch/tune pairs above. Each trainer requires its own running
simulator; keep both launch terminals open. The separate ROS domains, Gazebo
partitions, world names, and output directories prevent the two trials from
controlling each other's robot or writing into the same Optuna database. Both
jobs still share the computer's CPU and GPU, so each can run more slowly than
it would alone.

Each study saves `study.db`, trial logs and models, and `best_trial.yaml`.
Rerun an identical command to add trials; changing the base config, world,
terrain mesh, initial model, evaluation settings, or tuner requires a new output
directory. By default, trials start from the old 1.5M-step actor. Add
`--from-scratch` to omit that actor. The narrow search adjusts five section
specific reward weights and four PPO settings; it keeps the wheel-torque action
and network shape fixed. Tuning evaluates the normal course, with the flat
section at one adaptive item to match its initial training difficulty. After
selection, test the best model with new seeds and `--randomized`, and test the
flat specialist with up to six adaptive items before relying on it.

#### Train the flat course with a success-gated curriculum

Use `combined_flat_curriculum.yaml` for a new PPO run, after stopping the old
flat Optuna tuner. It does not change the original flat study or the rough
course. Stage 0 removes all cables and adaptive items to check physical goal
arrival. Stages 1–6 add the six cables one at a time, stages 7–9 widen their
angle range to ±10°, ±20°, and ±30°, and stages 10–15 add one adaptive item
at a time. The start and goal remain fixed. A stage advances after at least
75% ground-truth goal successes in its last 30 active-stage episodes. One in
five training episodes replays the preceding stage; replay outcomes do not
advance the current stage. Both the stage and its success window are saved in
normal PPO checkpoints.

In the flat simulator terminal, use the flat launch command above. In a second
terminal, use the same flat ROS domain and Gazebo partition, then check the
empty stage with the PI baseline before committing to a long training run:

```bash
ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/combined_flat_curriculum.yaml \
  --flat-stage 0 --episodes 12 --output rl_runs/flat_clear_baseline
```

If that check shows physical goal failures or large odometry drift, fix the
state estimate first. Otherwise, tune reward and PPO settings on **stage 1**
(one almost straight cable). Each trial trains its own model from the old
actor and evaluates that same fixed stage; it does not progress through all
16 stages. Use a new study directory so the original flat Optuna results stay
untouched:

```bash
python src/nino_rl/scripts/tune_split_optuna.py --section flat \
  --config src/nino_rl/config/combined_flat_curriculum_optuna.yaml \
  --device cuda --trials 8 --timesteps 30000 --eval-episodes 12 \
  --output rl_runs/flat_curriculum_optuna
```

The tuner writes `best_trial.yaml` (still locked to stage 1),
`best_curriculum.yaml` (unlocked for the full course), and `best_model.txt`
(path to the selected stage-1 model). Validate that model on new evaluation
seeds before the long run. If all trials still fail on one cable, inspect the
pose drift before increasing the trial budget.

The 2026-10-04 arrival checks found that stopping at the outer edge of the
20 cm odometry goal circle could leave the physical robot short. The opt-in
`combined_flat_curriculum_goal_margin.yaml` profile aims within 5 cm in
odometry while keeping physical success at 20 cm. It uses trial 6's tuned
PPO/reward settings and the unlocked curriculum. The old 1.5M actor scored
10/12 physical successes on one cable with this profile; the tuned actor
scored 8/12. These are nominal-course checks, not validation of the final
six-cable, six-item stage. See the [pretraining check report](docs/RL_PRETRAINING_CHECK_2026-10-04.md).

Start with a 50k-step curriculum pilot using this profile and the old actor.
The changed navigation contract requires `--init-model` rather than
`--resume`. Inspect physical success and stage advancement before extending
the pilot; the 2,048-step pipeline check remained at stage zero:

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_curriculum_goal_margin.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 50000 --checkpoint-every 10000 \
  --output rl_runs/flat_curriculum_goal_margin
```

To evaluate an intermediate checkpoint at a selected stage, pass
`--flat-stage 0` through `--flat-stage 15` to `ros2 run nino_rl evaluate`.
Without that option, evaluation uses the final six-cable, six-item stage. Use
fresh evaluation seeds and inspect physical success as well as odometry drift.

After the first 50k pilot, the clear-floor comparison measured 17/24 successes
for its actor, 12/24 for the old actor, and 22/24 for the PI baseline. Five
pilot goal misses kept moving at about 0.19–0.22 m/s after overshooting despite
the minimum approach reference. The opt-in
`combined_flat_curriculum_arrival_guard.yaml` profile tapers residual wheel
torques in the final 0.5 m of estimated path travel. See the
[arrival diagnosis and next training command](docs/FLAT_ARRIVAL_GUARD_2026-10-04.md).
Initialize that changed profile from the 50k pilot actor with `--init-model`;
its critic and optimizer start fresh. Localization drift remains unresolved.

The 2026-10-07 two-cable evaluation scored 11/24 physical successes for the
952,343-step final PPO and 23/24 for PI. Before extending that run, use the
[speed-only evaluation commands](docs/FLAT_SPEED_ONLY_CHECK_2026-10-07.md)
to retain PPO speed scaling while disabling its additive torque corrections.
This evaluates the saved policy with `--speed-only`; its weights are frozen.

The completed speed-only diagnostic scored 20/24 successes but averaged
28.61 s on successful episodes, missing the 22 s target. The new
`combined_flat_speed_yaw_pilot.yaml` profile uses two PPO outputs (speed and
bounded yaw reference) through PI, with zero additive torque. It also tightens
the estimated stop margin and raises minimum approach speed. Start a new
contract with `--init-speed-model` to reuse only the old actor's features and
speed output; the yaw head, critic and optimizer start fresh. See the
[20k pilot, Laya and matching PI comparison commands](docs/FLAT_SPEED_YAW_PILOT_2026-10-07.md).

The two `nino_ppo_final.zip` files **cannot be merged by averaging weights**.
They can be used in a switched controller that runs the rough policy before
x≈6.55 m and the flat policy after that point, but that controller is not yet
implemented. To obtain one checkpoint, initialize a new combined-course run
from one specialist actor, then fine-tune and evaluate on the entire combined
world; the other specialist's skill is not automatically retained.

### Tune the full combined course with Optuna

With the combined Gazebo world running in terminal A, set up terminal B as
shown above, install Optuna in the project virtual environment, and run trials
sequentially against that one simulator:

```bash
cd ~/ninorobot
python -m pip install optuna
python src/nino_rl/scripts/tune_combined_optuna.py \
  --config src/nino_rl/config/combined_course.yaml \
  --trials 12 --timesteps 50000 --eval-episodes 12 \
  --output rl_runs/combined_optuna
```

The default uses `artifacts/old_1_5m/nino_ppo_final.zip` as an actor
initialization. Each trial starts a fresh run and tunes selected active reward weights,
challenge bonuses, learning rate, and PPO update settings. The policy network
shape stays fixed so the old actor can transfer. To tune actor/critic widths,
history features, activation, and initial action scales too, add
`--from-scratch`; those trials do not use the old checkpoint. Task geometry,
sensors, and terminal success criteria stay fixed so trials
share a comparable task. The score uses held-out physical goal success first,
then progress and ground-truth path error; it does not maximize the reward being
tuned. The study persists in `study.db`; rerun the same command to add trials.
Read `best_trial.yaml` and the best trial's evaluation report before training a
longer run. Validate the selected policy on **new** seeds, since the trial
evaluation seeds were used to select it. Twelve trials are an initial search
in a large parameter space, so retest the selected configuration. To train
longer with the best warm-start configuration:

```bash
ros2 run nino_rl train --device cuda \
  --config rl_runs/combined_optuna/best_trial.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 500000 --checkpoint-every 25000 \
  --output rl_runs/combined_tuned_500k
```

For a `--from-scratch` study, omit `--init-model` in this command. Use
`--init-model`, rather than `--resume`, when transferring the old actor to a
new combined-course run. Regenerating the terrain changes the physical task;
start a new combined run after this pothole edit.

### Inspect training with Laya

Laya is an optional classifier for training statistics. It reads the trainer's
`episodes.jsonl`, compares the latest and previous episode windows, and names
one issue to inspect. The numeric metrics come directly from the log; Laya's
label is a suggestion, not a measured cause or a change to PPO or rewards.
The monitor uses CPU so the training GPU remains available. The first
classification downloads Laya's model checkpoint from Hugging Face.

```bash
cd ~/ninorobot
source .venv/bin/activate
python -m pip install 'laya==0.3.22'
python src/nino_rl/scripts/laya_training_monitor.py \
  rl_runs/combined_optuna_2day_v1 --window 100 --watch
```

For the two split-course studies, run one monitor per course in separate
terminals. Each follows only that study's newest training trial and appends
structured reports to a separate JSONL file:

```bash
python src/nino_rl/scripts/laya_training_monitor.py \
  rl_runs/combined_rough_optuna_fresh --course rough \
  --window 100 --watch --interval 300 \
  --output rl_runs/laya_monitors/rough.jsonl
```

```bash
python src/nino_rl/scripts/laya_training_monitor.py \
  rl_runs/combined_flat_optuna_fresh --course flat \
  --window 100 --watch --interval 300 \
  --output rl_runs/laya_monitors/flat.jsonl
```

Each report includes success and termination counts, ground-truth and wheel
odometry endpoint errors, odometry drift, and Laya's suggested issue. Read the
counts and errors first: the installed Laya checkpoint can disagree with the
dominant measured failure and its confidence is not calibrated for this task.
These monitors read logs and do not change Optuna trials, PPO weights, rewards,
or robot commands.

The monitor accepts a timestamped run directory, its parent `train` directory,
or the Optuna study directory; for a study it follows the newest trial. It can
start before the first episode is written. Use `--preview` to see the statistics without loading Laya;
omit `--watch` for a one-time report. With `--watch`, it checks every five
minutes and waits for 20 episodes before asking Laya. Stop it with Ctrl+C.
Compare `laya_advisory` with `most_common_failure_group`; the packaged
checkpoint has issued a temperature-calibration warning in this environment,
so do not treat its confidence number as a reliable probability.

## Rocky Hall: run, drive, train, and evaluate

Complete the installation in sections 1–5 below first. From the repository
root, regenerate the current terrain and build its ROS packages:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python src/nino_description/scripts/generate_rocky_world.py
python -m colcon build --symlink-install --packages-select nino_description nino_rl
source install/setup.bash
```

In **each new terminal**, run this setup before any Rocky Hall command:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=${NINO_ROS_DOMAIN_ID:-77}
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

Start the world in terminal A. Use `headless:=true` for training without the
Gazebo window; keep this launch running while training or evaluating.

```bash
ros2 launch nino_rl rocky_training.launch.py headless:=false
```

To drive manually, run this in terminal B, with that terminal focused. Stop
teleop before starting a trainer or evaluator so only one process commands
`/cmd_vel`.

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/cmd_vel
```

To check the training pipeline, run a short **fresh** job in terminal B. Stop
manual teleop first. This profile uses a 6 m straight route and CUDA by
default; old cable-course checkpoints have different action meanings. Start a
new run after changing the terrain mesh so its results describe this surface.

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/rocky_tracking.yaml \
  --timesteps 4096 --check-env --output rl_runs/rocky_tracking
```

For a longer fresh run, use the same command with more steps and checkpoints:

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/rocky_tracking.yaml \
  --timesteps 200000 --checkpoint-every 25000 \
  --output rl_runs/rocky_tracking
```

View training metrics in another prepared terminal with
`.venv/bin/tensorboard --logdir rl_runs/rocky_tracking --port 6007`.

Training prints its timestamped run directory under `rl_runs/rocky_tracking/`.
After stopping the trainer, evaluate the baseline and saved PPO model **one at
a time** while terminal A is still running. Replace `<run-id>` with the
directory printed by training:

```bash
ros2 run nino_rl evaluate_baseline --episodes 20 --seed 10000 \
  --config src/nino_rl/config/rocky_tracking.yaml \
  --output rl_runs/rocky_baseline
ros2 run nino_rl evaluate --device cuda --episodes 20 --seed 10000 \
  --config rl_runs/rocky_tracking/<run-id>/ppo.yaml \
  --model rl_runs/rocky_tracking/<run-id>/nino_ppo_final.zip \
  --output rl_runs/rocky_evaluation
```

The terrain mesh is fixed when generated; changing the training seed does not
create a new map. See the [terrain preview, training metrics, and experiment
details](docs/ROCKY_TRACKING.md).

### Tune Rocky Hall PPO with Optuna

Install the optional tuner in the same virtual environment, then start the
headless Rocky Hall world in terminal A using the setup above:

```bash
python -m pip install optuna
ros2 launch nino_rl rocky_training.launch.py headless:=true
```

In a second prepared terminal, run sequential trials against that world:

```bash
python src/nino_rl/scripts/tune_rocky_optuna.py \
  --device cuda --trials 12 --timesteps 50000 --eval-episodes 10 \
  --output rl_runs/rocky_optuna
```

The script tunes PPO learning rate, batch size, training epochs, entropy
coefficient, and clip range. Every trial saves its config, training log, model,
and evaluation report under `rl_runs/rocky_optuna/trial_*/`. Optuna stores the
study in `rl_runs/rocky_optuna/study.db`. Run the same command again to add
trials; use a new `--output` directory if you change the base config, training
budget, evaluation seeds or episode count, or device. The 4096-step smoke test
above is too short to rank policies reliably. Keep one tuning process on the
world; parallel trials need separate Gazebo and ROS instances.

The score gives most weight to evaluation success rate, then progress and
ground-truth path error. After tuning, run `ros2 run nino_rl evaluate` again
with the printed best model and its sibling `ppo.yaml`, using new seeds and
more episodes. Compare that report with a baseline report made with the same
seeds and episode count; the tuning evaluations are already used for model
selection and are not a final test. If your intended training budget is much
longer than 50000 steps, retrain the promising settings at that budget before
choosing a final model.

## 1. Prepare Ubuntu and the NVIDIA GPU

Use Ubuntu **24.04**, its system Python **3.12**, and an NVIDIA-capable machine.
Run these commands on the machine that will actually train, not a separate
laptop without the GPU. Skip driver installation if `nvidia-smi` already works.

```bash
sudo apt update
sudo apt install git curl locales software-properties-common \
  python3-venv python3-pip build-essential ubuntu-drivers-common
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
ubuntu-drivers devices
sudo ubuntu-drivers install
sudo reboot
```

After reboot, `nvidia-smi` must list the intended GPU (for example RTX 4080).
Resolve driver/Secure Boot issues before installing RL dependencies. Installing
`nvidia-utils` alone does not install a working kernel driver. See
[Ubuntu's NVIDIA driver guide](https://documentation.ubuntu.com/server/how-to/graphics/install-nvidia-drivers/).

## 2. Install ROS 2 Jazzy, Gazebo, Nav2 and RViz

If `/opt/ros/jazzy/setup.bash` already exists, skip the ROS repository setup.
Otherwise enable Universe and install the official ROS apt-source package:

```bash
sudo add-apt-repository universe
NINO_ROS_APT_VERSION=$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
curl -fL -o /tmp/nino-ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${NINO_ROS_APT_VERSION}/ros2-apt-source_${NINO_ROS_APT_VERSION}.noble_all.deb"
sudo dpkg -i /tmp/nino-ros2-apt-source.deb
sudo apt update
sudo apt upgrade
sudo apt install ros-jazzy-desktop ros-dev-tools
```

Install the robot dependencies:

```bash
sudo apt install python3-rosdep python3-colcon-common-extensions \
  ros-jazzy-ros-gz ros-jazzy-ros-gz-interfaces ros-jazzy-gz-ros2-control \
  ros-jazzy-xacro ros-jazzy-robot-state-publisher ros-jazzy-controller-manager \
  ros-jazzy-effort-controllers ros-jazzy-joint-state-broadcaster \
  ros-jazzy-ros2controlcli ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox ros-jazzy-robot-localization ros-jazzy-rviz2 \
  ros-jazzy-tf2-ros
source /opt/ros/jazzy/setup.bash
```

Use the [official Jazzy installation guide](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
if repository packaging changes. `ros-jazzy-ros-gz` supplies the compatible
Gazebo integration; do not install Gazebo Classic for this project.

## 3. Get the source and apply the patch

For a fresh checkout:

```bash
cd ~
git clone --branch add_rl https://github.com/macminhtuan131/Ninobot_controlled_with_torque.git ninorobot
cd ~/ninorobot
```

For an existing checkout, enter its directory and check `git status`. Preserve
local edits before changing branches. The supplied patch was made against
`d015b8239648c64974e5badd041aa87f3a5a0fdc` on `add_rl`.

```bash
git rev-parse HEAD
git apply --check ~/Downloads/ninobot-rl-improvements.patch
git apply ~/Downloads/ninobot-rl-improvements.patch
```

Use the actual download path. If the check reports conflicts, stop and reconcile
the branch/local changes; do not force the patch or discard your work.
Skip applying the patch if these changes are already in your checkout.

Initialize rosdep once (skip `init` if already initialized), then resolve the
packages required by this training workspace:

```bash
sudo rosdep init
rosdep update
rosdep install --from-paths src/nino_description src/nino_control src/nino_rl \
  src/linorobot2/linorobot2_navigation --ignore-src --rosdistro jazzy -r -y
```

## 4. Create the Python environment and install CUDA PyTorch

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade --force-reinstall torch==2.13.0 \
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r src/nino_rl/requirements.txt
python -m pip check
python -c 'import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))'
```

The CUDA 12.6 wheel above is an explicit example from the
[official PyTorch version matrix](https://pytorch.org/get-started/previous-versions/).
Use a compatible NVIDIA driver. A `+cpu` wheel or `torch.version.cuda == None`
is wrong for this workflow. The system CUDA toolkit is not required just to use
these wheels. `--system-site-packages` is necessary for ROS Python modules;
`python3-venv` prevents the `ensurepip is not available` error.

## 5. Build with the venv interpreter

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-up-to nino_rl
source install/setup.bash
ros2 run nino_rl check_cuda
```

Expect `CUDA khả dụng: True`, the correct GPU, and a successful CUDA matrix
multiplication. Always use **`python -m colcon` inside the venv** so installed
Python entry points can import PyTorch. Do not move the venv after building.

For every new terminal, run these four lines first:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
```

## 6. Start simulation and check it

Set the endpoint and forward controller in `src/nino_rl/config/ppo.yaml`:

```yaml
goal_tolerance_m: 0.10
navigation:
  start_pose: [0.0, 0.0, 0.0]
  goal_pose: [6.0, 0.0, 0.0]
  straight_speed_m_s: 0.75
  minimum_approach_speed_m_s: 0.03
  goal_slowdown_distance_m: 0.50
```

The robot is successful only while its center is inside the 10 cm endpoint
circle and its heading is within 12 degrees of the path direction. Merely
crossing the goal plane no longer counts, so overshoots and lateral misses are
failures. The direct command always has
`angular.z = 0`; the residual policy may apply differential wheel correction to
counter drift while following the straight reference. The curriculum cable is
at `x=4 m`, leaving 2 m for recovery and drift measurement before the 6 m goal.
With `headless:=false`, Gazebo displays the goal as a bright green disc, pole,
and flag. The marker is visual-only and cannot collide with the robot or LiDAR.

Training starts with one adaptive hazard. One more is added after five
consecutive successful episodes. Any failure breaks the streak, and adding a
hazard clears the streak. The cap is eight adaptive hazards plus the single
phase cable. Rolling results and the
current hazard count are stored in every regular, final, and interrupted
checkpoint. The established pothole-like patches, low stepped bumps, short
transverse cables, and road-groove surrogates are randomized per episode inside
the four-metre training zone. Every center is uniformly sampled between the
left and right wheel-center lines (approximately ±17.1 cm). The 35 cm post geometry is classified as a blocking
route-planning obstacle and is never sampled or rewarded as a wheel-control
challenge. Adaptive geometry remains at full height in every phase: in
particular, the pothole basin keeps its 30 mm relief. The phase cable changes
diameter and skew; its tilt sign is randomized every episode, including the
easiest phase's ±5-degree cable.

The road groove uses two gently sloped, 20 mm-high shoulders around a 100 mm
floor-level transverse channel. This creates a physical relative drop for the
wheels. Gazebo cannot subtract a runtime hole from the hall floor, so it is a
local raised-road surrogate rather than below-world geometry.

Speed is a learned continuous action: PPO scales the 0.75 m/s straight
reference from 0 to 100% on every 0.1 s policy step. A 20 Hz downward-looking
LiDAR fan provides a fresh, deployable preview of low cable/terrain relief, in
addition to the forward safety LiDAR. Successful arrival before the 15 s target
earns a proportional bonus, while impact, slip, torque, timeout, and path terms
prevent "always full speed" from being the only useful strategy. TensorBoard
records mean/min/max speed scale and mean ground speed for every episode.

The other two actions are common and differential residual effort. They map
bijectively onto bounded left/right wheel torque, so PPO can increase one wheel,
decrease the other, or change both independently while the 500 Hz PI loop keeps
the requested wheel velocity stable. Acceleration is not a competing actuator
mode: it is the physical result of bounded torque, velocity targets, and the
controller's wheel-acceleration/slew limits.

Traversable challenges use one-shot privileged reward flags that are not added
to the actor observation. Flags require a powered wheel's swept footprint to
intersect the region, rather than merely passing a bump under the chassis.
This is a geometric crossing estimate, not a physical contact-force sensor.
Entering a challenge can earn at most +2 over the
whole episode, clearing its local forward edge at most +8, and a successful
goal earns up to another +90 in proportion to the fraction cleared. These
totals are divided across the episode's challenge count, so adding hazards does
not inflate the maximum return. Oscillation cannot collect a flag twice, and a
collision, rollover, timeout, off-path, or wrong-direction step earns no new
challenge bonus. Episode reports and TensorBoard include chosen/cleared counts
and fractions under `challenge_*` fields.

At phase 1, the randomized pothole is a 0.60 m round, 30 mm-deep relative basin with smooth
approximately 12.5-degree entry/exit ramps and a roughly 3 mm leading edge. It
is sized to admit the 16 mm caster wheels while still requiring useful drive
effort. Gazebo cannot subtract a randomly spawned shape from the existing flat
floor, so this is an annular raised-basin surrogate rather than a literal hole
below the hall floor; a true excavated hole would require replacing the floor
with a pre-cut mesh or heightmap.

Terminal A:

```bash
ros2 launch nino_rl training_sim.launch.py headless:=true
```

For visual debugging, stop that launch and restart with `headless:=false`.
Do not launch both copies. This training launch
starts the effort controller, sensors and Gazebo reset services. It does not
start Nav2, AMCL, a map server, or a planner.
It refuses to start if the same Gazebo world is already running; this prevents
multiple `/clock` and IMU publishers from corrupting lockstep training.
Wait for the simulator and controllers. Terminal B:

```bash
ros2 control list_controllers
ros2 param get /effort_drive accept_torque
ros2 topic hz /imu/data
```

Both `joint_state_broadcaster` and `wheel_effort_controller` must be active;
`accept_torque` must be `True`. Stop the topic-rate command with Ctrl-C.
The nominal IMU frequency is 50 Hz in simulation time. The training command
performs the mandatory 12-point preflight, including actuation, before learning.
Use `training_sim.launch.py`, not the standalone description launch, for RL.

## 7. Smoke-test, then train phase 1

Keep Terminal A running. Terminal B:

```bash
ros2 run nino_rl train --device cuda --phase 1 --timesteps 4096 --check-env
```

This is a plumbing test, not enough training to learn a useful policy. Once it
works, start the real run:

```bash
ros2 run nino_rl train --device cuda --phase 1 --timesteps 500000 \
  --checkpoint-every 25000
```

The run prints its directory, e.g. `rl_runs/20260917-123456-123456/`. It contains
`ppo.yaml`, software/device metadata, `monitor.csv`, `episodes.jsonl`, TensorBoard logs,
`checkpoints/nino_ppo_*_steps.zip` and `nino_ppo_final.zip` when finished.
Rollouts are 2048 steps, so SB3 can exceed the requested step count to complete
a rollout. Training is already active while those steps are collected; the
first PPO optimizer table does not appear until the first rollout completes.
Watch the live `EPISODE END` lines for collection progress. A 500000-step run
needs at least 50000 simulated seconds at 10 Hz,
plus reset/update overhead; actual wall time depends on Gazebo throughput.

Terminal C:

```bash
tensorboard --logdir rl_runs --port 6006
```

Judge learning using `episode/success`, `episode/timeout_failure`, and
`episode/endpoint_distance_m` together. `episode_reward/*` shows whole-episode
reward totals, while `reward_terms/*` shows per-step averages. The corrected
timing should keep `episode/max_clock_error_seconds` near zero and
`episode/max_motion_sensor_lag_seconds` below 0.04 s. Individual records are
saved in `episodes.jsonl`, including the termination reason and curriculum phase.
Revision 28 needs a fresh run; older models learned under different timing and
reward semantics. Restart the simulator after rebuilding so both lidar masks
exclude the decorative goal beacon.

Progress now measures reduction in actual endpoint distance, including lateral
misses and overshoot. The speed reference stays low after passing the goal;
more than 0.30 m longitudinal overshoot ends the forward-only task with
`goal_missed` and a failure penalty. An in-circle heading error retains a small
forward reference so PPO still has differential steering authority. Initial
Gaussian standard deviations are `[0.20, 0.12, 0.05]` for speed/common torque/
steering; each remains trainable. Watch `policy/std_*` and
`episode/goal_missed_failure` alongside the other outcomes.

Open `http://localhost:6006`. Inspect success, path RMSE/P95, completion,
heading RMSE, impact RMS, torque, reward terms and PPO KL/entropy together.
Gazebo uses lockstep training: every action advances exactly 50 two-ms physics
steps (0.1 simulated seconds), then waits for fresh sensor and torque feedback while
paused. Optimizer wall time therefore cannot consume the mission deadline.
CUDA memory usage alone is not evidence of successful learning.

A Ctrl-C or runtime transport failure saves `nino_ppo_interrupted.zip` if a
model exists; its unfinished rollout is discarded on resume. Fix the transport
problem before continuing. Resume only compatible v2 runs with their saved config:

```bash
ros2 run nino_rl train --device cuda --phase 1 --timesteps 500000 \
  --config rl_runs/YOUR_RUN/ppo.yaml \
  --resume rl_runs/YOUR_RUN/checkpoints/nino_ppo_25000_steps.zip
```

`--timesteps` is additional training. A saved but never-updated model is still
untrained. Training seeds are set by `seed` in the YAML; use separate configs
with different seeds for repeatability checks.

## 8. Evaluate baseline and PPO automatically

Stop the trainer; keep the same training simulation running. Run these commands
**sequentially**, using the real model/config paths printed by training:

```bash
ros2 run nino_rl evaluate_baseline --phase 1 --episodes 20 --seed 10000 \
  --config rl_runs/YOUR_RUN/ppo.yaml --output rl_runs/baseline-p1
ros2 run nino_rl evaluate --device cuda --phase 1 --episodes 20 --seed 10000 \
  --config rl_runs/YOUR_RUN/ppo.yaml --model rl_runs/YOUR_RUN/nino_ppo_final.zip \
  --output rl_runs/ppo-p1
```

Each command prints a timestamped report directory. It contains `summary.json`,
`episodes.csv`, a config/metadata snapshot, and for every completed episode:
`episode-001/trajectory.csv`, `actual.csv`, `reference.csv`, `metrics.json`, and
`trajectory.png`. `trajectory.csv` contains `time_s,x_m,y_m,yaw_rad,frame_id`
and can be loaded directly by pandas, a spreadsheet, or MATLAB. The PNG overlays
the fixed straight reference and the measured robot trajectory.
Automatic metrics
include time-weighted path/cross-track RMSE, P95/max path error, heading RMSE,
endpoint error, completion, backtracking, success, timing, slip, torque and IMU
impact. Incomplete evaluations are marked and cannot be compared as full runs.

```bash
ros2 run nino_rl compare_evaluations \
  --baseline rl_runs/baseline-p1/BASELINE_STAMP/summary.json \
  --candidate rl_runs/ppo-p1/PPO_STAMP/summary.json \
  --output rl_runs/comparison-p1.json
```

Compare **success first**, then errors/comfort and successful completion time.
A stopped or failed robot can have low RMSE. Reports separate all episodes from
successful episodes. The comparator checks phase, seeds, count, perturbation
mode and task config. Matching seeds reproduce the terrain draws; they do not
make asynchronous ROS/Gazebo execution bitwise deterministic.

`--randomized` on **both** evaluators tests full-strength residual/sensor
perturbations. These are not physical friction/mass changes.
The baseline receives zero residual torque, including under randomized testing.

## 9. Run all six cable phases automatically

Every phase has exactly one cable at 4 m. Training progresses from easy to hard;
only cable diameter and absolute angle define phase difficulty. The sign of a
nonzero angle is randomized so the policy does not favor one wheel.

Run one continuous training job with the default configuration:

```bash
ros2 run nino_rl train --device cuda --timesteps 600000 --check-env
```

Omit `--phase`: specifying it deliberately locks the run to one phase.
Steps 0–99,999 use phase 6, then phases 5, 4, 3, and 2 each receive
100,000 steps; phase 1 starts at step 500,000. Terrain changes on the first
episode reset after a boundary, so an active crossing is never interrupted.
The phase remains 1 after the schedule finishes. Resume preserves absolute
step progress and the hazard success streak. API checks do not advance the
schedule. PPO may finish its final rollout beyond the requested step budget.

| Phase | Difficulty | Diameter | Absolute angle |
|---|---|---:|---:|
| 1 | Hardest | 15 mm | 45 degrees |
| 2 | Very hard | 13 mm | 36 degrees |
| 3 | Hard | 11 mm | 27 degrees |
| 4 | Medium | 9 mm | 18 degrees |
| 5 | Easy | 7 mm | 9 degrees |
| 6 | Easiest | 5 mm | 0 degrees |

Domain randomization is disabled by default so the phase comparison is based
only on size and angle. Use `--randomized` during evaluation only when you
specifically want a robustness test.

Suggested initial gate: at least 19/20 held-out successes, no rollover/collision,
acceptable P95 path error (e.g. <0.25 m for this hallway), and no material comfort
regression versus baseline. These are proposed acceptance criteria, not measured
results. Use additional seeds for a final test, distinct from development seeds.

```bash
ros2 run nino_rl train --device cuda --timesteps 300000 \
  --config rl_runs/YOUR_RUN/ppo.yaml \
  --resume rl_runs/YOUR_RUN/checkpoints/nino_ppo_300000_steps.zip
```

Evaluate each phase using the same phase/seeds for baseline and PPO. The phase
schedule is step-based and does not wait for evaluation success. Keep several checkpoints; the final
one is not automatically best. Evaluate them on the same development seeds,
then test the chosen model on new seeds. Do not run an evaluation callback
against the same live world while the trainer is collecting a rollout.

## 10. Compare against your own ideal path or timed trajectory

A geometric reference CSV uses `x_m,y_m,frame_id`. An actual trace uses
`time_s,x_m,y_m,yaw_rad,frame_id`; yaw is optional. All coordinates must use the
same frame. The automatically exported files already follow this format.

```bash
ros2 run nino_rl trajectory_metrics \
  --actual rl_runs/ppo-p1/PPO_STAMP/episode-001/actual.csv \
  --reference rl_runs/ppo-p1/PPO_STAMP/episode-001/reference.csv \
  --mode path --output rl_runs/path-score.json --plot rl_runs/path-overlay.png
```

To compare with a scheduled ideal trajectory, give the reference a strictly
increasing `time_s` column as well, then use `--mode timed --max-gap 0.5`.
`position_rmse_m` compares interpolated positions at common simulation times;
there is no timestamp shift, rigid alignment, or extrapolation. Clock origins
must match. Exported time is relative to the first odometry sample; the episode
metrics record `clock_origin_sim_s` for converting absolute simulator timestamps. Long gaps, duplicate timestamps and frame mismatches are rejected.
Coverage is reported so an early-ending run cannot hide unobserved reference
time. Choose the gap limit according to your sampling rate, not to conceal loss.

A geometric straight path has no desired timestamps. Its default automatic score is therefore
**path RMSE**, not timed position RMSE. Poses are wheel odometry transformed by
localization, not external ground truth. For physical accuracy studies, export
motion-capture or correctly transformed simulator ground-truth poses instead.
Nearest-segment progress is ambiguous on self-crossing paths; use timed scoring
for such experiments. Do not concatenate several episode clocks into one CSV.

The scoring tools also work without ROS:

```bash
PYTHONPATH=src/nino_rl python -m nino_rl.trajectory_metrics --help
```

## Troubleshooting and scope

| Symptom | Action |
|---|---|
| `ensurepip` missing | Install `python3-venv`, recreate the incomplete venv |
| Torch `+cpu` / CUDA false | Install the CUDA wheel in the same venv; check driver; run `check_cuda` |
| Cannot import `rclpy` | Source Jazzy and use system Python 3.12 + `--system-site-packages` |
| `ros2 run` cannot import Torch | Rebuild Python packages with active venv and `python -m colcon` |
| Zero torque preflight | Use training launch, active effort controller, `accept_torque=True` |
| IMU coverage timeout | Check `/clock`, `/imu/data` stamps and load; the bounded wait handles delivery races but does not fabricate samples |
| Resume contract error | Use matching post-update run/config, or start a new run |
| No `/cmd_vel` subscriber | Rebuild `nino_control`, restart the simulation, and rerun preflight |

This patch does not introduce SWAE, a 3D terrain map, an ESKF, Isaac Lab,
asymmetric privileged critics, or unvalidated slope balancing. The existing
terrain-preview input is now driven by the simulated downward LiDAR. Hardware
deployment requires an equivalent calibrated producer; simulation alone cannot
establish transfer performance. See the design note for the selection rationale
and exact reward.
