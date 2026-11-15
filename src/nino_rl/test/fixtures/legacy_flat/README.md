# Small legacy fixtures

These four inputs preserve regression checks without depending on deleted
`rl_runs` output directories. They are test data, not a runnable historical
experiment or a supported training overlay.

- `pilot.yaml`, `training_contract.py`: flat seed43 optimizer contract check.
- `ros_env.txt`: exact historical text used by the optional trace insertion test.
- `height_22mm.sdf`: frozen geometry comparison for the height generator.

Original paths and SHA256 hashes are recorded in
`artifacts/rl_runs_cleanup_2026-11-08/fixture_provenance.json` in the client
workspace. Runtime code must not import these fixtures.
