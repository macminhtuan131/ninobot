# Old cable-course PPO checkpoint (1.5M steps)

This directory backs up the completed local run
`rl_runs/old_resumed/20260929-103314-954367`. Its final policy reached
**1,502,803 cumulative PPO steps**. The ZIP is the model to use with
`--init-model` when starting a fresh combined-course run; `ppo.yaml` is the
matching configuration for evaluating or resuming this *old cable-course*
checkpoint. Do not resume this checkpoint directly on the combined course.

The backup also contains `run_metadata.json`, the original monitor and full
episode history compressed as `monitor.csv.gz` and `episodes.jsonl.gz`, and the
original TensorBoard event file. Intermediate checkpoints are not included.

The resumed segment recorded 3,972 episodes and 2,305 successes (58.0%). Its
first 500 recorded episodes succeeded 40.8% of the time; the last 500 succeeded
78.0% of the time. These are training episodes on the old 6 m cable course,
not held-out evaluation or results on the combined 13 m course. Success in
this old run was based on wheel odometry; physical ground-truth goal error can
be larger.

Verify the model after copying it:

```bash
sha256sum artifacts/old_1_5m/nino_ppo_final.zip
# 4b60789906bc4fd92a6a9bd445d167bfe0ab3433552e1ea1f1347500bb69f350
```

To inspect its original curves:

```bash
.venv/bin/tensorboard --logdir artifacts/old_1_5m/tensorboard --port 6007
```

For the combined-course training command, see the root `README.md` and use
`artifacts/old_1_5m/nino_ppo_final.zip` as the `--init-model` path.
