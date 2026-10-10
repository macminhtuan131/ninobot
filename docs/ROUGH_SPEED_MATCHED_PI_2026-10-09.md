# Rough E1: speed-matched PI comparison — 2026-10-09

## Setup

Completed 20 PI episodes at speed scale 0.70 on seeds 10000–10019, compared
with the saved deterministic PPO pilot and full-speed PI on those same seeds.
All use the frozen v16 terrain, controller, estimator and robot snapshot, fixed
E1 route, and unchanged physical arrival criteria. No additional PPO training
or Optuna tuning was started.

The comparison helper verified matching benchmark IDs, phase, pose source,
episode count and evaluation seeds. PI and PPO mean completion times differ
by 0.15 s (0.386%), within the predefined 5% matching tolerance.

## Results

All three evaluations achieved **20/20 physical arrivals**. Speed-matched PI
passed all 10 ordered route gates on every episode; its maximum physical
endpoint error was 0.199884 m, within the unchanged 0.20 m arrival radius.

| Metric | Full-speed PI | PI at 0.70 | PPO |
|---|---:|---:|---:|
| Completion time (s) | 27.10 | 38.71 | 38.86 |
| Physical path RMSE (cm) | 2.04 | 2.60 | 2.42 |
| RMS vertical acceleration (m/s²) | 1.556 | 1.153 | 1.130 |
| Mean episode peak vertical acceleration (m/s²) | 14.89 | 11.70 | 9.25 |
| RMS wheel slip | 0.0537 | 0.0411 | 0.0483 |
| RMS wheel torque (N·m) | 0.3400 | 0.3092 | 0.3082 |

## Interpretation

Slowing PI reproduces about **95% of the original RMS vertical-acceleration
reduction** between full-speed PI and PPO. This is a descriptive comparison
of mean differences, not a causal attribution or statistical significance claim.

Against speed-matched PI, PPO has:

- 2.0% lower RMS vertical acceleration, a small remaining difference.
- 20.9% lower mean episode peak vertical acceleration.
- 7.0% lower physical path RMSE, an absolute difference of only 1.83 mm.
- 17.4% higher RMS wheel slip.
- Essentially the same mean wheel torque and completion time.

The policy is not uniformly better. Most of the original RMS vibration advantage
is explained by slower travel, but lower peak acceleration remains worth
investigating. Equal mean completion time does not imply identical instantaneous
speed profiles, so this comparison cannot isolate the contribution of residual
torque actions. These are evaluations of one trained policy on fixed E1, not
independent training seeds or unseen-terrain tests.

## Next decision

Preserve this pilot as a reliable E1 checkpoint. Before a long continuation,
define an explicit acceptable time/comfort tradeoff and keep arrival scoring
strict. If peak impacts are the target, assess them alongside the slip regression.
E1 qualification permits a short fixed E1+N1 curriculum block with E1 replay;
it does not establish superiority over PI or readiness for terrain randomization.
Rough Optuna remains held. This comparison launched no curriculum continuation.

## Evidence and rerun

- PPO: `rl_runs/rough_wall_recovery_v16/curriculum/blocks/block_0000/evaluation/original/20261009-111540-895313/summary.json`
- Full-speed PI: `rl_runs/rough_wall_recovery_v16/curriculum/baselines/stage_0/original/20261009-113412-803772/summary.json`
- Speed-matched PI: `rl_runs/rough_wall_recovery_v16/speed_matched_pi_0.70/20261009-120037-129118/summary.json`
- Comparison: `rl_runs/rough_wall_recovery_v16/speed_matched_pi_0.70/comparison.json`
- The experiment plan, localization observations and complete evaluation log
  are beside `comparison.json`.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
python src/nino_rl/scripts/run_rough_speed_matched_pi.py --speed-scale 0.70
```

The command owns and closes its isolated rough simulator and preserves the
flat session. Complete existing evidence is verified and reused on rerun.
