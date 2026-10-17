# Classical governor Optuna v2 artifacts

See the [Vietnamese report](../GT_GOVERNOR_OPTUNA_V2_2026-10-16.md) for the
preregistered budget, fixed objective, failures and decision.

- `contract_before_results.json`: six fixed candidates, scenario banks and gates.
- `selection_before_validation.json`: candidate frozen before validation.
- `trials.json` / `study.sqlite3`: new study registry and database backup.
- `decision.json`: validation unavailable, no retry or parameter promotion.
- `accounting_checks.json`: all 40 attempts retained; 35 completed traces;
  provenance/config checks and 489 unchanged protected files. The
  `completed_native_physical_failures` count applies only to native completed
  outcomes. Also inspect the two startup failsafes in `validation_startup_events.json`;
  neither is erased by the unavailable evaluator outcome.
- `episodes.csv` / `all_episodes.json`: per-attempt data, including unavailable cases.
- `executed_holds.json`: measured command phase durations, separate from configured timers.
- `trial_*/` / `validation/`: configs, scenario worlds, case logs, native CSVs,
  source metadata and analysis; native scores are unchanged.
- `source_manifest_sha256.json`: archived source/raw input hashes.

Large raw contact/sensor logs remain in
`rl_runs/gt_governor_optuna_v2_2026-10-16/` and are referenced by path/hash.
The independent logger is not the evaluator callback stream; its coverage
does not certify evaluator delivery. No unavailable impact or slip is zero-filled.

The study is closed at its 40-attempt budget. Its runner intentionally refuses
an existing output directory; this is not a command to resume or retry it.
