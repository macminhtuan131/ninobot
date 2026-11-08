> **Mới nhất06/11 — Gain baseline Gazebo đã đóng9/9:** 1.260ticks;283hashes/3.834support checks đạt,0actor/train. Causal/fixed native: +23,0% tại1; +29,8% tại0,98; −15,3% tại1,02. SoB0 còn sampling-sensitive ở1/0,98; chưa promote/learner. Tiếp correction estimator cổ điển offline. [Kết quả](../../docs/NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Backend/context gain đạt parity offline:** 41 software tests; 4.800 callbacks kernel và 840 transitions wrapper fixture, 0 Gazebo/train mới. Cùng gain=1 giữ observation/reward/reference/terminal, context ABI mới chặn checkpoint cũ. Tiếp runner/release baseline qualification riêng. [Kết quả](../../docs/NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Benchmark đã chốt offline:** giữ cổ điển cho clear known-stop; câu hỏi mới chỉ về gain common cố định chưa biết. Đã kiểm causal encoder candidate và phân rã 840 hàng cũ; 0 physics/training mới. Tiếp backend/context riêng, parity gain=1 trước qualification baseline. [Quyết định](../../docs/NINO_SIM_BENCHMARK_DECISION_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Mới nhất 06/11 — Eval reset-ready đã đóng 6/6:** 840 eval ticks, 0 train/optimizer. A seed11 có native velocity RMSE cao hơn cổ điển 71,5%/88,8%; hai GT grids cùng chiều. 199 hashes/2.561 support checks đạt. Giữ cổ điển cho clear known-stop; chốt benchmark trước training mới. [Kết quả](../../docs/NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md). Real cutoff vẫn 02/11; các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](../../docs/NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Coverage V2 đã đóng:** A seed11 hoàn tất, C seed11 partial; **1.864 replay /1.736 critic /868 actor updates,0eval**,15launches;49slot còn lại đóng. Lỗi initial drive readiness/permission, không phải thiếu joint của observer. Candidate correction chỉ kiểm offline; [kết quả](../../docs/NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Cập nhật06/11 — Coverage V2:** runner mới đã nối metadata vào full train path; preflight qua GUI **80 tests đạt**, GUI **54 tests đạt**, build2package. Chưa release physics hoặc có scientific train/eval mới. V1 vẫn đóng; [kết quả V2](../../docs/NINO_SIM_COVERAGE_V2_IMPLEMENTATION_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Sim06/11 — coverage V1 đã đóng:** [kết quả](../../docs/NINO_SIM_COVERAGE_RESULT_2026-11-06.md); thiếu metadata qualification_condition ở tick đầu.1launch/0replay/update/eval,không retry hoặc chạy bù. Correction riêng kiểm offline,chưa V2/hardware.

> **Sim06/11 — coverage runner/preflight:** [implementation](../../docs/NINO_SIM_COVERAGE_IMPLEMENTATION_2026-11-06.md); sampler/replay/optimizer/evaluator và GUI đã kiểm91tests. Profile Critic/coverage có preflight offline đạt, study chưa release. Scientific training/Gazebo/hardware mới0; kết quả cũ vẫn ưu tiên classical/B0.

> Cập nhật06/11: evaluation-only mới đã đóng, dùng ba checkpoint TD3 có sẵn; không train thêm. Xem [kết quả](../../docs/NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md) và [protocol](../../docs/NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md). Chưa promote/hardware.

> Cập nhật06/11: pilot TD3 RELIABLE với lifecycle từng episode đã đóng; xem [kết quả](../../docs/NINO_SIM_RELIABLE_TD3_RESULT_2026-11-06.md) và [protocol](../../docs/NINO_SIM_RELIABLE_TD3_PROTOCOL_2026-11-06.md). Chưa promote hoặc mở training/hardware mới.

> **Cập nhật06/11 — candidate joint RELIABLE:** fixturepaired1000messages +1handshake/pause100ms đạtcompatibility, cảBE/RELIABLE1000/1000; candidateB0stop6/8 đạt2launches/280ticks. GUI hai nút cógate +QC/metric;khóa stageđãđóng. Chưa optimizerload/training hoặc rootcauseproof, partialTD3700ticks giữ. Tiếp learnerfresh103D/1D protocol riêng. [Kết quả](../../docs/NINO_SIM_JOINT_RELIABILITY_RESULT_2026-11-06.md).

> **Cập nhật06/11 — joint diagnostic đã đóng2/2:**200zero ticks/612checks đủsupport; hai observer trùng15.220source stamps, payloadfield không lệch. Chưa tái hiện50ms, nguyênnhânunknown; khôngtraining/hardware hoặc reopenpartialTD3. GUI có profile và bảngage/parity/error. Tiếp tốiđa mộtcandidateQoSjointRELIABLE riêng, chưa áp/chạy. [Kết quả](../../docs/NINO_SIM_JOINT_BOUNDARY_RESULT_2026-11-06.md).

> **Cập nhật06/11/2026 — TD3 common103D/1D đã train partial:**700ticks/636critic +318actor updates,5training episodes đạt task/stop. Episode6 thiếu joint support50ms tại half-tick zero; batch đóng, seed22/33 +10eval chưa chạy. GUI có profile riêng và partial/error review, khóa retry. Chưa có learned-benefit comparison hoặc hardware. Xem [kết quả](../../docs/NINO_SIM_COMMON_TD3_RESULT_2026-11-06.md).

> **05/11 — wrapper103D/1D đã đạt Gazebo:**4/4launches,560ticks,replay560rows,actor/optimizer0. [Kết quả](../../docs/NINO_SIM_EQUAL_GAZEBO_RESULT_2026-11-05.md). Bước tiếp: fresh TD3 common-only pilot theo draft mới; chưa train hoặc resume V3.

> **05/11 — contract cùng preview đã đạt offline:**103D/1D common-only, shared window và requested replay;840bước fixture tổng hợp,optimizer/Gazebo0. Không resume V3. [Kết quả](../../docs/NINO_SIM_EQUAL_INFORMATION_RESULT_2026-11-05.md). Bước tiếp: kiểm wrapper mới trong Gazebo theo protocol riêng, chưa chạy.

> **05/11 — stop-time transfer đã xong:** 6/6 lượt,840ticks,actor/optimizer0. Common cổ điển có RMSE v thấp hơn cả3 B0 trên native và hai GT-header grids; giữ candidate, chưa promote. [Kết quả](../../docs/NINO_SIM_STOP_TRANSFER_RESULT_2026-11-05.md). Tiếp: contract TD3/cổ điển cùng thông tin, chưa mở train mới.

> **05/11 — đối chứng common cổ điển đã xong:** 6/6 lượt,840 tick,optimizer0. Whole-task RMSE v thấp hơn B0/frozen common ở cả hai lượt; giữ candidate có planned stop, chưa promote. [Kết quả và bước tiếp](../../docs/NINO_SIM_CLASSICAL_COMMON_RESULT_2026-11-05.md).

> **GUI train TD3:** smoke64, nhập timesteps, train/resume checkpoint, log/lỗi/kết quả và TensorBoard local. [Hướng dẫn](../nino_pi/TD3_TRAINING_GUI.md).

> **05/11 — frozen-axis ablation đã xong:** 6/6 lượt, 840 evaluation ticks, không optimizer. Bỏ residual vi sai giảm lệch đường, nhưng common-only vẫn tệ hơn B0 về RMSE vận tốc toàn lượt do pha hạ tốc. Giữ B0; [kết quả, GUI và đối chứng cổ điển kế tiếp](../../docs/NINO_SIM_AXIS_ABLATION_RESULT_2026-11-05.md).

> **05/11 — TD3 V3 đã train và đánh giá:** guided baseline + zero-init + nominal reward; 512 train/496 updates, 8 eval. Tất cả marker/stop đạt, clear TD3 tracking tệ hơn B0; có một B0 gờ vượt gate được giữ. Chưa promote; [kết quả và hướng tiếp](../../docs/NINO_SIM_GUIDED_TD3_V3_RESULT_2026-11-05.md).

> **05/11 — screen guided clear/gờ 6 mm đã xong:** 4/4 marker + stop, 560 transition, residual zero. Gờ RMSE path 3,09–4,28 mm; chưa train TD3 mới. GUI hiển thị từng lượt; [kết quả và contract V3 kế tiếp](../../docs/NINO_SIM_GUIDED_CONTACT_RESULT_2026-11-05.md).

> **05/11 — V3 đã kiểm:** estimator wheel+IMU → follower → residual zero → PI đã chạy trong Gazebo. 8/8 marker + stop; RMSE path guided 13,09–13,84 mm, constant 93,06–93,65 mm. Không train thêm TD3. [Kết quả và bước tiếp](../../docs/NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md).


> **04/11 — nhánh sim đã chạy:** B0 ba môi trường → TD3 h5 256 transition/240 optimizer updates → B0/B1/TD3 evaluation. Không cần real dataset để train sim. Checkpoint chưa promote; xem [kết quả và điểm dừng](../../docs/NINO_SIM_BRANCH_RESULT_2026-11-04.md).

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
