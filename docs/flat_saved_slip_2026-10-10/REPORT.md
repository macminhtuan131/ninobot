# Flat saved-slip inspection

Read-only analysis of scale-only PPO and matching PI on seeds 64000–64023.

Mean paired RMS slip increase: **0.010123**; scenario bootstrap 95% interval **[-0.008406, 0.028436]**.
PPO had more slip in **14/24** episodes.

## Episodes contributing the largest slip increases

| Seed | PPO RMS slip | PI RMS slip | Difference | PPO time | PI time |
|---|---:|---:|---:|---:|---:|
| 64021 | 0.2556 | 0.1572 | +0.0984 | 18.50 | 17.30 |
| 64022 | 0.2173 | 0.1324 | +0.0849 | 18.40 | 17.20 |
| 64014 | 0.2242 | 0.1559 | +0.0683 | 18.50 | 17.50 |
| 64011 | 0.2134 | 0.1471 | +0.0663 | 18.30 | 17.30 |
| 64010 | 0.2601 | 0.2084 | +0.0517 | 18.60 | 17.70 |
| 64012 | 0.2169 | 0.1761 | +0.0409 | 18.20 | 17.50 |

## What the saved data can establish

Episode totals identify which scenarios account for the mean difference. Pose trajectories do not contain wheel speed or action-window slip, so they cannot assign that difference to a cable, acceleration, yaw correction or the final approach. No phase-specific cause is claimed.

Exploratory associations are recorded in analysis.json; they do not establish causation. The confidence interval covers paired evaluation scenarios, not variation across independent training seeds.

The second-seed comparison records per-action left/right slip and existing drive diagnostics. This adds observability to that comparison without changing the reward or physical scoring. It cannot reconstruct missing traces from the first run.
