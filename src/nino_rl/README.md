> **04/11 — parameter catalog:** `config/td3_parameter_profiles.yaml` + `nino_rl.td3_config` kiểm schema/hash và tạo config/ABI draft; smoke dùng profile chung. h1/h5/h8 research còn là đề xuất. Không mở budget hoặc hardware authority. Xem [Studio / contract](../nino_pi/REAL_DATA_STUDIO.md).

# Nino residual learning package

> **Factory TD3, 04/11:** [bounded smoke on the actual mixed factory world](../../docs/NINO_FACTORY_TD3_SMOKE_2026-11-04.md). GUI job **FACTORY · TD3 + Nino + wheel PI** uses the Nino URDF, swivel casters and existing torque-producing velocity PI. The older 128-step TD3/PPO jobs use the reduced-order fixture. Neither job is a hardware release or a claim of research benefit.

> **Cập nhật 04/11 — [History / Governor / TD3 / GUI v5](../../docs/NINO_RESIDUAL_IMPLEMENTATION_2026-11-04.md):** đã có environment chạy, optimizer smoke TD3/PPO, portable actor và kiểm ROS/Gazebo fixture. Xem tab **Xây project** để kiểm artifact hiện hành. Train nghiên cứu và learned residual trên robot vẫn chưa mở; dữ liệu thật chưa được thu thêm trong cập nhật này. Các mục có ngày trước bên dưới giữ bối cảnh lịch sử.

> **Current research route:** [bounded velocity residual, SysID and fair classical baselines](../../docs/NINO_RESEARCH_DIRECTION_2026-11-03.md). New TD3/PPO use a distinct20×5 contract. General training remains disabled; bounded fixture/factory smoke jobs have separate gates. Hardware residual deployment is unopened. Commands below describe legacy experiments.

For the expanded rough terrain, use the [evaluation-gated route curriculum,
terrain variants and Laya guide](../../docs/ROUGH_ROUTE_CURRICULUM.md).
The supervisor script starts E1 first, retains earlier routes while adding
goal groups, then introduces R1–R3 terrain variation between blocks.

All four Optuna scripts use the
[fixed physical-arrival and motion-quality objective](../../docs/optuna_objective_2026-10-08/README.md).
Every evaluated route must achieve at least 95% physical arrival in the sample;
qualified trials are ranked by time, lateness, physical path error, vibration
and slip. Objective weights stay fixed when training rewards change. Use a
new study directory for this objective, and inspect the metric breakdown
before choosing a policy.

Use the [comparable trial preparation guide](../../docs/comparable_optuna_trials_2026-10-08/README.md)
to audit the flat/rough starting actors and freeze world/profile, initialization,
training budget and scenarios. `--prepare-only` creates a plan without training;
each trial uses a fresh critic/optimizer and an aligned environment-step budget.

[Saved-result reuse and the queued specialist studies](../../docs/saved_optuna_results_2026-10-08/README.md)
use PI performance as references, enqueue the exact current parameters once,
and import completed historical PPO scores only after contract/artifact checks.
`--prepare-study` creates the queue without starting training; historical
databases are audited read-only.

The current implementation uses a 300-value observation history and three
continuous actions: straight-reference speed scale, common torque residual and
differential torque residual. Nav2 is disabled: the baseline is a direct forward
command with zero angular velocity. The robot has passive caster supports; it is not a two-wheel
inverted pendulum. CUDA training is the default.

1. Follow [the complete root README](../../README.md) from Ubuntu/driver setup
   through ROS/Gazebo, the Python venv, build, preflight and training.
2. Read [RL_IMPROVEMENTS.md](RL_IMPROVEMENTS.md) for the exact active reward,
   policy, engineering decisions and trajectory metrics.
3. Use `evaluate_baseline` and `evaluate` sequentially with matching phase,
   configuration and seeds. Each exports `trajectory.csv`, actual/reference CSVs and automatic
   path RMSE, P95, heading, completion, comfort and timing scores, plus an
   expected-versus-robot trajectory plot for every episode.
4. Use `trajectory_metrics` for custom geometric or timestamped references and
   `compare_evaluations` for compatible baseline/PPO summaries.

Training contract revision 24 requires a fresh run after this patch. Later phase
changes can resume revision-24 checkpoints. The older `ALGORITHM_V2.md` and
`REWARD_POLICY_UPDATE.md` describe historical revisions; current defaults and
commands are in the root README and RL_IMPROVEMENTS.md.

## Completed training bundle

[Weights, measured training results and integration commands](models/completed_train/README.md)
are included in this package. After rebuilding, `ros2 run nino_rl policy_node`
loads the bundled checkpoint and matching configuration on CPU by default.
