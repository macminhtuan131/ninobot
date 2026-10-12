# Rough observable PPO pilot: revision 47

Output: `rl_runs/rough_observable_pilot_v2`. Optuna remains held.
This is one fresh 20,480-transition pilot, with no checkpoint transfer and no
automatic extension if the results fail. The preceding pilot and all studies
remain preserved.

## Implemented corrections

### Bounded rearming and causal reward state

The original hardware cue thresholds are retained: vertical-acceleration EMA
1.5 m/s², body rate 0.35 rad/s, wheel-versus-command error 0.06 m/s. Holding
remains 0.6 s and cooldown 1.2 s. **Recovery now expires after at most 0.8 s**,
even if the actor cruises below scale 0.98. Returning above 0.98 may finish it
earlier. Wheel-versus-command error remains a tracking cue, not a truth-slip
measurement. Detection still uses causal endpoint measurements; actor summaries
now additionally retain the completed interval's IMU energy and peak.

The cue advances when the next actor observation is created. Its stored phase
is included in that observation, and the subsequent action's reward uses that
same stored phase. The action cannot receive a cruise-cost exemption triggered
by the consequence of that action. Reset clears all interval summaries, timers
and executed-command memory. These changes alter the reward gate contract,
while retaining exactly the previous numerical reward weights.

### Hardware observations: 72 × 5 = 360 inputs

The original 56 features are retained. Sixteen channels are appended per frame:

| Added channel | Normalization |
|---|---:|
| Completed interval vertical acceleration RMS | /10 m/s² |
| Completed interval vertical acceleration peak | /10 m/s² |
| Filtered acceleration cue | /10 m/s² |
| Roll/pitch angular-rate norm | /3 rad/s |
| Wheel-versus-command tracking error | /0.2 m/s |
| Disturbed flag | 0 or 1 |
| Holding, recovering, cooldown flags | three channels |
| Phase time remaining | /1.2 s |
| Actual ramped policy scale | raw scale |
| Previously published linear/yaw references | /0.5 m/s, /2.5 rad/s |
| Driver-executed linear/yaw references | /0.5 m/s, /2.5 rad/s |
| Completed IMU coverage fraction | 0–1 |

Driver-executed references come from stamped diagnostics within the completed
action interval, including the shared startup ramp. Interval energy/peak are
measured hardware IMU summaries, not terrain labels. All features are causal.
No terrain preview, generated terrain positions, ground-truth velocity or
truth slip enters the actor. Physical truth remains an independent simulator
reward/scoring input. The five-frame span remains 0.4 s; explicit sensor
summaries and cue state address the information omitted by endpoint history.

Exact input tensors and corresponding action, cue, executed scale and reward
terms are stored in compressed `actor_capture/chunk_*.npz` files per workflow
stage. Captures are newly created, never silently overwritten. This allows the
next inspection to use actual policy inputs rather than reconstructing them
from incomplete CSV diagnostics.

### Sustained exploration with supported action probabilities

This pilot uses installed SB3 PPO's **generalized State Dependent Exploration
(gSDE)**, refreshing the exploration noise matrix every six control steps
(0.6 s) and at rollout starts. Actions can vary with state while sharing the
same noise matrix; this is not a command held exactly constant for six steps.
SB3 calculates the corresponding action log probabilities. No external teacher
or injected command replaces PPO's sampled action.

Initial physical head bias scale is explicitly **0.85**. The legacy normalized
constructor field is set to `(0.85−0.55)/0.45`, not to 0.85 directly. Initial
gSDE matrix standard deviation is 0.065; action variance depends on actor
latents and is not equal to that matrix standard deviation. A synthetic hardware
frame produced clipped raw-action standard deviation about 0.334 in the offline
check. Actual safe slowdown/recovery exposure must pass a real rollout gate.

Speed action meanings and authority remain unchanged: target scale 0.55–1,
reference slew limit 0.4/s, unscaled PI yaw, no residual motor torque. CUDA
training uses seed 17000, fresh actor/critic/optimizer, learning rate 1e-4,
1,024-step rollouts, batch 256, three epochs and fixed learner reward scale 0.1.
All preceding longitudinal reward weights, including lateness after 31 s,
remain numerically identical.

## Gates and workflow

1. **Offline verification:** bounded rearming at constant scale 0.975; quiet
   sensors do not trigger; summary dimensions and units; truth/preview isolation;
   persistent noise on a fixed observation; fresh optimizer/counter; save/reload;
   rejection of the old 280-input model. Verified before simulation launch.
2. **PI authority:** three full-speed and three scale-0.7 episodes, seeds
   13100–13102, under the new snapshot. Arrival, route order, physical tracking,
   localization, no rollover, zero torque residual and actual driver yaw response
   must pass. Simulation timing/IMU freshness checks remain strict.
3. **Real stochastic exposure:** a fresh untrained actor, seeds 17010–17012,
   same gSDE construction and six-step refresh as training. Require 3/3 physical
   passes and at least 2/3 episodes exhibiting executed scale ≤0.85 for at least
   three successive steps during a disturbance/holding cue, then ≥0.95 within
   five seconds. This proves exploration exposure, not learned adaptation.
   No retraining or seed selection is used to turn a failed exposure gate green.
4. **Fresh training:** exactly 20,480 transitions, checkpoints every 4,096.
   The exposure actor is discarded. No weights/optimizer are transferred.
5. **Deterministic evaluation:** PPO, full PI and duration-matched PI on seeds
   17100–17104. Physical terrain remains fixed nominal half-relief E1.

Final acceptance requires all of the following:

- Existing strict physical arrival/tracking/localization criteria for PPO and
  both PI references, including no rollover.
- Every PPO episode passes the existing conditional response rule: actual
  slowdown below 0.9 followed by ≥0.98 recovery, quiet mean scale ≥0.95 and
  quiet-minus-holding mean scale ≥0.03.
- Mean PPO time is no more than 15% above full-speed PI.
- Matched PI duration is within 3% of PPO duration.
- At least one disturbance-window energy-per-metre metric improves by ≥5%
  against matched PI; neither vibration nor slip window energy worsens by >10%.
  Neither whole-episode vibration nor slip RMS may worsen by >10%.

The spatial windows are selected only from full-speed PI cues and applied to
all three controllers, retaining the prior −0.10/+0.80 m union rule. Terrain
coordinates are used for offline scoring only. A completed workflow can still
have `pilot_passed: false`; reliable arrival alone does not authorize Optuna.
One training seed and five fixed-map reset scenarios do not establish causal
IMU dependence, unseen-terrain generalization or sim-to-real performance.

## Commands

The automated runner owns and closes its own Gazebo/ROS processes. It checks
isolation on ROS domain 78 and partition `nino_rough_78`; do not open a second
rough simulator while it runs.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/prepare_rough_observable_pilot_v2.py
python src/nino_rl/scripts/verify_rough_observable_pilot.py
python src/nino_rl/scripts/run_rough_observable_pilot_v2.py --run
```

Read progress in a separate terminal:

```bash
cd ~/ninorobot
cat rl_runs/rough_observable_pilot_v2/status.json
cat rl_runs/rough_observable_pilot_v2/REPORT.md
tail -f rl_runs/rough_observable_pilot_v2/train/train.log
```

TensorBoard, once training creates events:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/rough_observable_pilot_v2/train --port 6008
```

Final result: `rl_runs/rough_observable_pilot_v2/comparison.json`. Saved models,
strict timing checks and failed-gate evidence are retained on interruption.
The runner does not automatically resume an interrupted PPO rollout.


## Startup evidence and version provenance

The prototype v1 completed all six PI checks and all three stochastic exposure
checks. All three exploration episodes physically arrived and exhibited
sustained slowdown then recovery; minimum executed scales were 0.71192,
0.71428 and 0.71795, with maximum scale 1.0 in each episode. Reduced-speed PI
produced 8–10 cue events per episode; recovery never exceeded 0.8 s.
810 recorded full-speed PI input tensors matched the exact phase/timer used
for their corresponding rewards. Seven existing regression tests passed.

A stale textual observation label in training-contract metadata was found
before any PPO transitions. The prototype runner was stopped during simulation
startup for training; no policy was trained under that contract. Its saved
checks remain in v1. Version v2 corrects the label to 72/frame and 360 history,
declares the action/exploration interfaces explicitly and uses revision 47.

The v2 preparer verifies that configuration bytes and every actor/controller/
sensor Python module match v1, except the training-contract metadata module.
It binds the original screen artifacts by hashes and reuses the nine checks;
no extra simulation was needed to repeat identical checks. A fresh model is
constructed only in v2. The exploration model is not transferred.

The v2 runner has entered fresh CUDA training startup, seed 17000. Final
learned behavior and ride-quality improvement remain unproven until its
post-training comparisons complete.
