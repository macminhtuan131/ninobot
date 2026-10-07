# Saved Nino RL experiments

These backups preserve selected trained policies, resolved configurations,
episode logs and completed evaluation evidence. Original local `rl_runs/`
directories are unchanged and remain ignored by Git, along with `.venv/`,
`build/`, `install/` and `log/`.

| Directory | Saved policy | Status |
|---|---|---|
| `old_1_5m` | 1,502,803 steps, old cable course | Existing preserved training run |
| `rough_straight_676124` | 676,124 steps | Earlier straight-route rough actor |
| `flat_torque_952343` | 952,343 steps, torque actions | Two-cable frozen evaluation: 11/24 physical successes |
| `flat_speed_yaw_20480` | 20,480 steps, speed/yaw references through PI | Pilot complete; matching frozen PI comparison pending |
| `rough_routes_112589` | 112,589 steps, expanded-map rough actor | Corrected E1 stopping-margin evaluation: 20/20 physical successes |

Each new checkpoint backup has a `backup_manifest.json` recording its source,
model filename and SHA256. Matching `ppo.yaml` files contain the resolved
training configuration. Monitor and episode files are compressed losslessly.

`evaluations_2026_10_07/` preserves completed numerical comparisons. Rough PPO
and PI both reached E1 in all twenty corrected-stop evaluations, but PPO was
slower and had greater physical tracking error. Success alone does not establish
an advantage. The rough speed-only diagnostic has no completed episodes saved
at this snapshot and is not represented as a completed comparison.

The rough curriculum state is saved as historical evidence. It contains local
absolute paths and is not a portable resume ledger. Generate and verify a
terrain bank on the destination machine, and use the actor with `--init-model`
for a fresh curriculum. Direct `--resume` requires an identical training
contract, compatible saved configuration and the original verified terrain bank.

The flat speed/yaw pilot has a different action contract from torque actors.
`--init-speed-model` transfers only features and speed from a torque actor into
a new speed/yaw run. A saved torque output must not be interpreted as a yaw
velocity reference. See `docs/FLAT_SPEED_YAW_PILOT_2026-10-07.md` and
`docs/ROUGH_E1_STOP_MARGIN_CHECK.md` for the experiment commands and limitations.
