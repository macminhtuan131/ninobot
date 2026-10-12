# Reactive rough speed intervention and conditional PPO pilot

Optuna remains held. Old maps, models and studies are preserved.

## Step 1: fixed authority test

Five paired E1 reset seeds **15100–15104**, nominal physics and the same half-relief terrain. Full-speed PI and the intervention use unchanged steering, wheel PI, localization, physical arrival and timing checks.

The trigger reads tilt-compensated IMU vertical acceleration, body roll/pitch rates, and encoder wheel-speed error relative to the last published command. It reads no truth velocity, pose, terrain geometry or preview. Thresholds are fixed before evaluation: filtered absolute vertical acceleration 1.5 m/s², body rate 0.35 rad/s, or wheel-speed error 0.06 m/s. An 0.8 s startup exclusion and minimum motion request of 0.15 m/s prevent startup/stop triggering.

A trigger requests speed scale **0.70 for at most 0.60 s**, using the existing 0.4 scale/s reference ramp. It then requests full speed until scale reaches 0.98, followed by a 1.2 s cooldown. It cannot perpetually extend a slowdown in response to its own acceleration transient. Yaw remains PI-controlled; additive torque stays zero.

Disturbance intervals are selected from the **PI reference only**: from 0.10 m before each trigger to 0.80 m after, merged where overlapping. Physical X is used only for offline E1 scoring; it is unavailable to the trigger. Per-action IMU energy, coverage and slip squared are allocated by spatial overlap. This finite-resolution allocation is not an exact high-frequency contact reconstruction. Report window RMS, energy per metre, time, and whole-episode metrics.

The frozen gate requires physical arrival/tracking, actual slowdown and recovery in every run, no more than **15% added time**, at least **5% lower window vibration or slip energy per metre** with a positive median paired gain, no more than **10% regression** in the other window energy or whole-episode slip. Five fixed-map reset seeds are an authority screen, not proof of generalization.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
python src/nino_rl/scripts/run_rough_reactive_authority.py --run
```

Progress: `rl_runs/rough_reactive_authority_v1/REPORT.md`. Final gate and traces: `authority_result.json`, `pi/`, `reactive/` in that directory.

### Borderline first batch: one fixed confirmation

The first batch passed 5/5 physical arrivals and recovery, with 4.82% additional time. Window vibration RMS fell 5.09%, but vibration energy per metre fell **4.944%**, narrowly missing the predeclared 5% energy threshold. The failed first-batch gate is preserved.

One additional batch uses **15200–15204**, identical controller/task configuration and the same thresholds. Its protocol is frozen before evaluating those seeds. Training authorization uses the aggregate of all ten paired seeds, not selection of whichever batch looks better. No third confirmation batch or threshold relaxation is planned. See `rl_runs/rough_reactive_confirmation_v1/confirmation_protocol.json`, then `combined_result.json` when complete.

The combined screen **passed**: 10/10 physical arrivals and recoveries, mean physical path RMSE **0.01631 m**, zero rollovers. Window vibration energy per metre decreased **6.13%**, vibration RMS decreased **5.72%**, and slip energy per metre decreased **2.21%**. Mean total time increased **4.41%**; whole-episode slip RMS changed by **+0.09%**. The median paired vibration-energy reduction was only **1.51%**; these fixed-map results authorize the learning pilot, not a robust performance or sim-to-real claim.

Seven focused tests passed. The new policy verifier confirmed a one-action/280-input model, initial speed scale 0.90090, fresh optimizer/counter, no preview/truth velocity in actor inputs, successful save/reload, and rejection of the old observation/action contract. The new runner is launched at `rl_runs/rough_reactive_reward_pilot_v1`; its status distinguishes PI validation, actual PPO training and completed evaluation.

```bash
python src/nino_rl/scripts/run_rough_reactive_confirmation.py
```

## Steps 2–3: conditional new learning contract

Only a passing authority gate permits preparing the new pilot. The candidate reward reduces cruise tracking pressure and time cost, increases the vibration weight, uses a smaller slip normalization scale, and restores cruise tracking after each bounded sensor-cue holding interval. It adds a soft lateness cost after 31 s while preserving the original physical mission deadline. The sensor-cue monitor changes reward weighting only; it does not override PPO actions or provide position-based teacher actions.

The candidate penalizes changes in the executed, ramped speed reference rather than unexecuted Gaussian target jumps. It keeps the 280-value hardware observation, speed action, reference ramp and PI steering fixed. Fresh actor, critic and optimizer start at seed **16000**, near speed scale 0.901, with a 20,480-step budget. Evaluate on **16100–16104** against full-speed and duration-matched PI, including disturbance windows, variable actions and recovery. No Optuna follows automatically.

If Step 1 fails, these reward settings remain an unexecuted candidate; report the failed tradeoff rather than training on a task that has not demonstrated useful reactive authority.

After a passing authority result:

```bash
python src/nino_rl/scripts/prepare_rough_reactive_pilot.py
python src/nino_rl/scripts/verify_rough_longitudinal_pilot.py --snapshot rl_runs/rough_reactive_reward_pilot_v1
python src/nino_rl/scripts/run_rough_reactive_pilot.py --run
```

Pilot progress, if started: `rl_runs/rough_reactive_reward_pilot_v1/REPORT.md`. The final comparison includes per-seed speed variation and recovery plus window metrics. The scripted intervention is not active when PPO is evaluated.

### Pilot started

All six new-profile PI startup checks passed. Fresh CUDA training is active at `rl_runs/rough_reactive_reward_pilot_v1/train/20261011-144616-193015`, with seed 16000 and 20,480 requested transitions. The new reward contract is revision 45. Old checkpoints are not loaded. Completion of startup validation does not establish learned response.

The offline E1 trace reward reconstruction (`reward_audit.json` in the pilot directory) gives mean candidate return **18.84 for PI** and **19.18 for the brief intervention**. It uses captured IMU energy/slip and a reconstructed previous estimated PI request; it is an incentive check, not a new rollout or proof of learning. The final rollout comparison remains necessary.

The automated learned-response check requires physical arrival/tracking, no more than 15% additional time, actual slowdown followed by recovery, and at least a 0.03 difference between mean quiet and holding-interval speed scales, with quiet scale at least 0.95. Fixed-map response association still does not prove causal IMU dependence or unseen-terrain adaptation. Full-speed and duration-matched PI window comparisons are recorded separately from that response check.

```bash
cat rl_runs/rough_reactive_reward_pilot_v1/REPORT.md
tail -f rl_runs/rough_reactive_reward_pilot_v1/train/train.log
.venv/bin/tensorboard --logdir rl_runs/rough_reactive_reward_pilot_v1/train --port 6008
```

### Completed pilot and inspection

Training completed all 20,480 steps. PPO, full-speed PI and duration-matched PI
each reached the physical goal in 5/5 evaluation episodes. PPO took 27.60 s,
versus 26.96 s for full PI and 27.60 s for matched PI. Relative to matched PI,
PPO vibration RMS was 7.56% higher and wheel-slip RMS was 19.09% lower.
The declared conditional slowdown/recovery test failed in all five PPO episodes.

The [saved-data audit](ROUGH_REACTIVE_PPO_AUDIT_2026-10-11.md) verified frozen
inputs and exact reward accounting. It identified recovery-state lockout below
scale 0.98, a short endpoint observation history lacking interval IMU summaries
and reward-gate state, and insufficient exploration of the scripted slowdown.
The final PPO return is below both PI references; a larger vibration penalty
alone is not the next justified correction. No additional pilot or Optuna study
was launched by this inspection.
