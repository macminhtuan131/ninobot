# Rough trial 8: critic audit, matching PI, and fixed-route progression

## Execution status

Started the validation supervisor at **09:37 on 2026-10-10 (Asia/Bangkok)**,
PID **50911**. It waits for the active flat validation supervisor to finish
before launching rough Gazebo. Rough uses ROS domain **78** and Gazebo partition
`nino_rough_78`; flat keeps its existing domain 79/partition.

Live evidence:

- `rl_runs/rough_trial8_validation_v1/status.json`
- `rl_runs/rough_trial8_validation_v1/status_history.jsonl`
- `rl_runs/rough_trial8_validation_v1/supervisor.log`
- `rl_runs/rough_trial8_validation_v1/REPORT.md`

This document records the authorized protocol. The live report, not preparation,
establishes which phases completed or failed. No new rough Optuna worker starts.

## Source and preserved conditions

Source is the fixed trial-8 model:
`rl_runs/rough_e1_v16_optuna_v1/trial_0008/train/20261010-030720-658073/nino_ppo_final.zip`.
The plan records its SHA256, configuration, frozen v16 package/controller/robot
assets and original terrain bank. Old studies and models remain preserved.

The saved TensorBoard audit records final logged explained variance
**−0.0246465** and value MSE **221.183**. These logs suggest weak value learning;
they do not provide the rollout observations needed to measure gradient balance.
The live probe is therefore required before changing learner reward units.

## 1. Read-only critic and gradient audit

- Three stochastic frozen-actor episodes: seeds **11000, 11001, 11002**.
- Capture observations, raw Gaussian actions, values, log probabilities,
  rewards, terminal boundaries and episode outcomes.
- Reconstruct GAE targets using the saved gamma/lambda and measure actor/critic
  gradient norms with the installed PPO loss. Perform **no optimizer updates**.
- Verify the model hash remains unchanged.

The numerical imbalance gate requires all three conditions:

1. Explained variance below 0.1.
2. Median critic/actor gradient-norm ratio at least 5.
3. Median fraction retained by global clipping at most 0.01.

If confirmed, test fresh-critic initializations with multipliers **0.1, 0.03,
0.01**, without learning. Select the largest tested multiplier that brings the
median critic/actor ratio to at most 3 and at least doubles the retained gradient
fraction. This measures the actual fresh critic; it does not assume flat's
0.01 multiplier is appropriate. If no candidate meets the numerical criteria,
the correction is held. The probe is small and does not reconstruct historical
training batches or prove future convergence.

## 2. Matching E1 comparison

Evaluate trial 8, full-speed PI, and PI at **0.70 speed scale** on the same
unused reset seeds **12000–12019**, using the frozen v16 setup. Report physical
arrival, ordered gates, tracking, completion, vibration, peak acceleration,
slip, and the same objective terms as the existing E1 study. New scenario
identifiers/objective hashes are kept outside the historical Optuna database.

Check achieved durations: speed matching is valid only within **5%** of PPO's
mean duration. The report explicitly records whether 0.70 meets that tolerance;
do not attribute slower-PI comfort differences to learned control when it does
not. These tests use the **same fixed geometry with domain randomization
disabled**. Unused reset seeds do not establish unseen-terrain generalization.

## 3. Conditional short correction

Only the measured imbalance gate can authorize the correction branch.

- Copy the **complete trial-8 actor**, including its existing action heads.
- Fresh critic, fresh optimizer, timestep counter zero.
- Exactly **20,480 steps**, at the selected reward multiplier.
- Preserve task reward weights/formulas, controller, estimator, terrain,
  action meanings, physical arrival and timing checks.
- Place the constant multiplier after Monitor; raw episode metrics remain raw.
- Record new `critic/*` target/prediction and fit diagnostics.
- Use isolated package files and a new **revision-39 training contract**.
  An old-optimizer resume into changed reward units is rejected.

Evaluate the corrected model on the same 20 E1 seeds and compare with trial 8
and both PI profiles. Changing units lowers the numerical magnitude of MSE;
only explained variance and physical outcomes can establish useful improvement.
E1 must retain at least **19/20 independent physical arrivals**, mean physical
path RMSE at most **0.05 m**, and zero rollovers before route progression.
If the numerical imbalance is not confirmed, skip correction and require the
same physical gate from the unchanged trial-8 model.

## 4. Route-PI recheck, then fixed-map replay

Recheck PI on **E1, N1 and S1**. First use three screening seeds (13000–13002).
Only routes passing that screen receive a 20-seed confirmation (13100–13119).

Admission requires the declared arrival rate, physical endpoint radius and
ordered route gates, mean physical path RMSE **≤0.05 m**, mean pose disagreement
**≤0.10 m in every episode**, no rollovers, and longest physical commanded
wheel-spin stall **≤2 s**. Earlier N1 arrivals with 0.116 m path RMSE would fail
this gate. A failed route holds N1/S1 training; it does not relax tracking limits.

Once all route PI checks pass:

1. **E1 + N1:** balanced replay, 20,480 additional steps.
2. **E1 + N1 + S1:** balanced replay, another 20,480 steps, only after stage 1 passes.

The map stays original and fixed. No terrain randomization is enabled. Each
stage evaluates **20 episodes per active route** using seeds 14000–14019;
all active routes, including E1 replay, must meet the original curriculum gate.
Only declared stage selection changes, so a model already trained under the new
contract can retain its new optimizer across stages. Failed stages are held;
there is no unbounded automatic continuation. Maximum new training is 61,440
steps if correction and both route stages are needed and qualified.

## Checks and recovery

**10 focused tests passed**, covering the measured numerical decision,
prevention of correction based on MSE alone, N1 tracking admission, independent
physical criteria, preservation of controller/reward source files, incompatible
resume rejection, and legal declared-stage continuation. The held-out objective
was checked against both PPO and PI evaluation configurations. Frozen source
assets and workflow implementations are verified before simulation work.

If interrupted or an execution error occurs, completed evaluation batches and
models are retained. A rerun reuses complete validated evidence. An interrupted
training checkpoint requires review before a compatible optimizer resume; it
is not silently discarded or used to restart a second training block.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

# Preparation only; do not run while the supervisor owns its worker lock.
python src/nino_rl/scripts/run_rough_trial8_validation.py --prepare-only

# Run/recover the bounded workflow when no worker owns it.
python src/nino_rl/scripts/run_rough_trial8_validation.py
```

Current execution has already started; these commands are for inspection/recovery,
not another concurrent launch. The supervisor closes only its own processes.

The current localization uses the v16 multi-layer LiDAR and known wall geometry.
This validation does not establish transfer to arbitrary maps or real hardware.

## Later N1 repair and flat recovery — 10 October, 22:46

See [feedback recovery and N1 braking](FEEDBACK_RECOVERY_AND_N1_BRAKING_2026-10-10.md)
for the latest execution evidence. Flat's missing nine PI seeds are recovered
with unchanged timing checks, and its 24-seed quality comparison fails.

N1 v19 early braking reached 3/3 goals but failed the 0.05 m tracking limit
(0.0933 m RMSE). V20 maintained heading authority during earlier braking but
failed all three arrivals: two repeated wheel-spin/translation stalls near
(2.53 m, 0.63 m), and one localization-validity termination. Its low pre-failure
path error does not qualify it. Both candidates and the earlier failed profiles
are preserved. E1/S1 settings and physical scoring are unchanged; curriculum
and further rough tuning remain held pending contact and validity inspection.
