# Fixed Optuna objective — physical arrival and motion quality

Implemented on 2026-10-08 for the split, rough-resume, combined and Rocky
Optuna scripts. This changes **trial evaluation and selection**, not the
training reward formula or the robot's physical arrival criteria.

The evaluation settings live in
[optuna_objective.yaml](../../src/nino_rl/config/optuna_objective.yaml).
The shared implementation is
[tuning_objective.py](../../src/nino_rl/nino_rl/tuning_objective.py).
The next preparation step adds
[comparable trial contracts and checkpoint audits](../comparable_optuna_trials_2026-10-08/README.md).

## 1. Arrival is a requirement

A trial qualifies only when **each evaluated route has at least 95% physical
arrival success**. Scoring uses the existing ground-truth task result, with
the physical goal circle and ordered route gates retained. An estimated
arrival outside the physical goal circle is rejected. Rocky retains its
existing ground-truth gate task.

This is an empirical threshold on the evaluation sample, not a statistical
claim that deployment reliability is at least 95%. For example:

| Evaluation sample | Minimum successful arrivals |
|---|---:|
| 12 episodes on one route | 12 |
| 24 episodes on one route | 23 |
| 20 episodes per route | 19 on **each** route |
| 12 episodes across E1/N1/S1, four each | 4 on **each** route |

Every active route must be covered. Success on E1 cannot hide failures on N1
or S1. Use more episodes and independent final-test seeds before claiming
reliable improvement over PI.

## 2. Motion quality determines the ranking

For a successful episode, define:

- `t`: completion time; `T`: the frozen route time target.
- `e`: ground-truth path RMSE; `E`: its fixed normalization scale.
- `a`: RMS world-vertical IMU acceleration, with gravity removed.
- `s`: RMS wheel-slip ratio, measured using physical motion in simulation.
- `A`, `S`: fixed vibration and slip normalization scales.

With `cap = 5`, the episode terms are:

```text
D = min(cap, t/T)
L = min(cap, max(0, t/T - 1)) + indicator(t > T)
P = min(cap, max(0, e/E - 1)) + 0.25 * min(cap, e/E)
V = min(cap, a/A)
S_term = min(cap, s/S)
```

The duration term rewards faster arrivals even before the deadline. The
lateness term adds a penalty as soon as the deadline is missed, followed by
a proportional penalty. Path error has a small cost below its scale and a
stronger cost above it. Lower vibration and slip reduce their costs.

**Failed episodes receive maximum penalties:** `D=5`, `L=6`, `P=6.25`,
`V=5`, `S_term=5`. A stationary robot or an early failed episode cannot gain
quality points for having low vibration or slip.

Average terms within each route, then average the route means equally:

```text
C = D + 4*L + 4*P + V + S_term
```

The scalar Optuna objective, maximized by every tuner, is:

```text
if every route arrival rate >= 0.95:
    score = 100 / (1 + C)
else:
    r = the lowest route arrival rate
    deficit = max(0, (0.95 - r) / 0.95)
    score = -1000 - 1000*deficit - 100*C/(1 + C)
```

Every qualified trial outranks every unqualified trial. Within qualified
trials, lower quality cost wins. The score is neither a success percentage
nor PPO's return. Progress and training reward return are not used.

The weights implement the chosen trade-off; they do not guarantee that every
individual metric improves. Arrival qualification also does not guarantee
all episodes meet the deadline or path-error target. Inspect the breakdown
and compare with matching PI results before selecting a policy.

## 3. Frozen scales and targets

| Course | Path RMSE scale `E` | Vibration scale `A` | Slip scale `S` |
|---|---:|---:|---:|
| Flat | 0.05 m | 3.0 m/s² | 0.20 |
| Rough | 0.05 m | 1.6 m/s² | 0.05 |
| Combined | 0.05 m | 3.0 m/s² | 0.20 |
| Rocky | 0.05 m | 1.6 m/s² | 0.05 |

These are explicit engineering choices for normalization, not learned
weights or proven physical limits. They stay fixed throughout a study.

By default, time targets are resolved **once from the base task**, before
sampling reward weights. The corrected flat profile uses 22 s. The fixed
rough E1/N1/S1 profile currently resolves E1 to 67.5 s and N1/S1 to 58.5 s
from its existing route budgets. These are task budgets, not durations of
failed PI runs. The duration cost still favors faster successful arrivals.

To choose different targets, copy the objective YAML and populate
`time_targets_seconds`, for example:

```yaml
time_targets_seconds:
  E1: 31.0
  N1: 58.5
  S1: 58.5
```

Pass the copy using `--objective-config PATH` and use a **new study output
directory**. Do not change the thresholds or scales in response to the
results of individual trials.

## 4. What remains fixed across trials

Each study saves `evaluation_objective.json` and the same contract in its
database. The contract freezes:

- Physical task geometry, controller and estimator settings, and evaluation
  randomization settings through the evaluation benchmark fingerprint.
- Route assignment, scenario seeds, episode count and time targets.
- Arrival threshold, metric scales, weights and failure treatment.
- Objective and evaluator implementation fingerprints.

Training reward weights and PPO settings may vary without changing this
objective. Configurations with inherited profiles are fully resolved before
tuning. Evaluations with missing scenarios, duplicate scenarios, invalid
measurements, changed benchmarks or incomplete reports cannot receive a score.

Every scored evaluation writes `optuna_objective.json` beside `summary.json`.
The database stores the breakdown and `arrival_feasible` flag as trial
attributes. If no trial passes the arrival gate, the tuner writes
`best_infeasible.json` and **does not export a qualified best policy/config**.

Old studies contain different scores. Keep their databases for historical
analysis, and start a new `--output` directory for this objective. They cannot
be resumed under the new scoring contract. The evaluation seeds used by
Optuna are validation seeds; use unseen seeds/layouts for the final test.

## 5. Offline check against saved PI evaluations

These are rescored existing PI reports, **not new simulation runs or Optuna
trials**. They demonstrate how the objective responds to current results.

| Reference | Physical arrival | Qualifies | New score | Interpretation |
|---|---|---|---:|---|
| Corrected flat PI, speed scale 0.78, 24 episodes | 24/24 | Yes | 11.455 | Arrival is reliable in this sample; late completion and path error still cost points. |
| Fixed rough route PI, four episodes per route | E1 4/4; N1 0/4; S1 0/4 | No | -2097.762 | E1 success cannot qualify a study with failing turn routes. |

The flat report has 21/24 late arrivals, mean completion 22.354 s and physical
path RMSE 0.05154 m. These metrics explain why perfect sampled arrival does
not produce a high quality score.

Do not compare the numeric flat and rough scores with each other: their
tasks, targets and normalization contracts differ. Compare candidates only
under the same contract.

Artifacts:

- [Reference score breakdowns](reference_scores.json)
- [Example flat objective contract](flat_example_contract.json)
- [Example rough objective contract](rough_example_contract.json)
- [Corrected training setup and route PI results](../corrected_training_setup_2026-10-08/README.md)

No Optuna study or RL training was started while implementing this objective.
