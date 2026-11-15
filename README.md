> **14/11 — dọn dữ liệu sau đánh giá:** giải phóng **3,37 GiB**; xóa 36 file raw của 12 lượt thành công đã đánh giá và nén lossless 206 stream lịch sử. Giữ checkpoint/replay 10k–15k–20k, training trace, dữ liệu lỗi và qualification hiện tại. Evaluation còn 753 file khớp manifest và 36 file đã xóa có receipt; không còn là full raw archive. [Báo cáo retention và kết quả từng episode](docs/NINO_SIM_EPISODE_RETENTION_2026-11-14.md).

> **14/11 — đã đánh giá frozen B0/10k/15k/20k:**24slot,23QCvalid,3.648decisions;789file vàaction deterministic khớp trước retention. B0=5/6,10k=5/6,15k=4/6;20k=4pass/1fail/1unknown. Gap54ms cũ có ngay trong diagnosticsPI; jobtrain giữfailed. GiữB0, chưa train dài thêm; ưu tiên goal-stop/odometry và startup wheel freshness. [Kết quả và hướng tiếp](docs/NINO_GOAL100_GAP_AND_FROZEN_CHECKPOINT_EVALUATION_2026-11-14.md). Các cập nhật dưới là lịch sử.

> **12/11 — review Goal100 research20k và dọn dữ liệu:** đã train đủ20.000transitions/10.000critic/5.000actor;113/126episode train đạt,1đoạn censored. Job **failed raw QC** vì gap drive54ms tại episode57; chưa evaluation B0/TD3. Đã dọn3,779GiB raw lặp và checkpoint thừa, giữ10k/15k/20k, full trace/replay và raw failures/QC. [Báo cáo, biểu đồ và cách đọc chất lượng train](docs/NINO_TRAINING_REVIEW_AND_RETENTION_2026-11-12.md). Các cập nhật dưới là lịch sử.

> **10/11 — Goal100 đã chạy Gazebo và smoke TD3:**7launch/970ticks,384train/368critic/184actor; deterministic dev evaluation tới goal và dừng2s. B0 giữ2/3success và một path failure; chưa learned benefit. Studio có engineGoal100 và nút **chỉ điền** research20k. **Đã dừng trước train dài.** [Kết quả, gate correction và bước tiếp](docs/NINO_UNKNOWN_STEP_GAZEBO_AND_TD3_SMOKE_2026-11-10.md). Các cập nhật dưới là lịch sử.

> **10/11 — Sim TD3 / task gờ không biết:** checkpoint common103_v2 seed11 đã tới **50k**; job failed evaluation, chưa promote. Task goal mới có physical scorer, estimator goal-stop, sensor-only100D/common1D và Gym interface đã kiểm software; **chưa Gazebo integration hoặc train task mới trong lượt chuẩn bị đó**. [Bằng chứng chuẩn bị](docs/NINO_UNKNOWN_STEP_SOFTWARE_PREPARATION_2026-11-10.md).

> **09/11 — sửa lỗi train common103_v2:** startup Gazebo episode200 timeout,27.999 training transitions/28.000 environment transitions; checkpoint20k được giữ. Thêm startup diagnostics/re-registration có giới hạn và lưu terminal replay trước reset;121tests +2startup zero-only đạt. [Bản resume20k và giới hạn](docs/NINO_TD3_STARTUP_REPAIR_2026-11-09.md). Chưa chạy lại campaign trong lượt sửa lỗi đó; engine cũ chưa phải task unknown-step goal.

> **09/11 — mục tiêu đã chọn: gờ KHÔNG BIẾT TRƯỚC, vượt được và bám quỹ đạo.** Thay hướng preview giảm rung đã biết; IMU/encoder/history/reference vào controller, GT/contact/metadata gờ chỉ scoring. Rung/slip phụ. Task spec và Studio cập nhật; chưa runtime/task outcome hoặc budget mới. [Hướng và các bước tiếp](docs/NINO_UNKNOWN_STEP_TASK_DIRECTION_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **09/11 — chuẩn bị hướng motion quality trên tuyến đã biết:** classical preview 0,20→0,18 m/s so B0 và chạy chậm đều ≈0,1877 m/s khớp thời gian tham chiếu. Metric gia tốc tại IMU và draft đã kiểm fixture; chưa body time-match/runtime/physics. **0/6 lượt được cấp; mục tiêu/ngưỡng chưa accepted.** E2 vẫn đóng6/6, giữ classical. [Draft và bước offline tiếp](docs/NINO_KNOWN_ROUTE_MOTION_QUALITY_DRAFT_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **09/11 — audit stop8 đã đóng:**560 native rows đúng công thức/source; GT tại native clocks tái lập native. Common− GT−5.6%/native+0.92% là sampling sensitivity, chưa thấy lỗi công thức giải thích bất đồng. **Giữ classical, đóng nhánh promote hiện tại;6/6 allocation vẫn đóng,6slot block1 chưa cấp.** Studio đã cập nhật. [Audit và hướng tiếp](docs/NINO_FIXED6MM_SAMPLING_AUDIT_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **09/11 — stop8 đã đóng, E2 dùng6/6 allocation:** authority hai chiều đạt nhưng quality sampling-sensitive:common+ GT ISE+21.8%;common− GT−5.6%/native+0.92%. Giữ classical,6slot block1 chưa cấp, chưa train. [Kết quả và audit offline tiếp](docs/NINO_FIXED6MM_STOP8_RESULT_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **09/11 — E2 reader v2 kiểm lại offline đạt:** giữ group timestamp mơ hồ và unknown strict v1;0 query authority cần group này. Cell đầu có signed wheel/body persistence0.760s âm/0.620s dương, primary không đổi.0Sim/train mới;3/3 allocation vẫn đóng,9slot chưa cấp. [Kết quả và cell stop8 tiếp theo](docs/NINO_FIXED6MM_TIMESTAMP_REANALYSIS_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **09/11 — E2-03 đã chạy, cell3/3 đóng UNKNOWN:** task/replay đạt, nhưng reader strict gặp4 wheel payload cùng source stamp; chưa xác minh authority dương. GT primary giảm55.18% chỉ mô tả. Studio cập nhật issue/next offline correction;9slot còn lại chưa cấp. [Kết quả và điểm dừng](docs/NINO_FIXED6MM_POSITIVE_RESULT_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **09/11 — E2-01/02 đã đóng2/2:** cặp common−0.005 sau manifold qua caliper; ISE tracking GT giảm44.02%/43.79% mô tả, chuỗi hai bánh/body trước drive contact đạt. Chỉ một cell dùng oracle, chưa chứng minh TD3/governor sensor-only;10slot còn lại chưa cấp. Studio cập nhật tiến độ và kiểm evidence. [Kết quả và điều kiện tiếp theo](docs/NINO_FIXED6MM_FIRST_PAIR_RESULT_2026-11-09.md). Các cập nhật dưới là lịch sử.

> **08/11 — E2-01 neutral Gazebo đã đóng:** 140/140 task ticks, task/stop/closure và native replay đạt;39/39 file khớp hash. Prefix1/1 đã hết,11 slot còn lại chưa cấp. Chưa có nonzero residual contrast hoặc benefit. [Kết quả và bước tiếp](docs/NINO_FIXED6MM_NEUTRAL_RESULT_2026-11-08.md). Các cập nhật dưới là lịch sử.

> **08/11 — E2 runtime đã kiểm offline:** adapter oracle, cutoff receipt, PI readback, QC từng slot và runner có ledger/review đã có. Neutral parity stop6/8 đạt trên fixture; release mẫu vẫn false/0, chưa chạy Gazebo mới. [Kết quả và neutral slot kế tiếp](docs/NINO_FIXED6MM_AUTHORITY_RUNTIME_2026-11-08.md). Các cập nhật dưới là lịch sử.

> **08/11 — E2 đã chuẩn bị offline:** gờ6mm, Ki0.10, ba profile common sau first C1 manifold oracle. Đã audit sáu raw E1 và kiểm reference preview; 12 lượt đề xuất, 0 allocated, chưa runtime/physics mới. [Protocol và bước tiếp](docs/NINO_FIXED6MM_AUTHORITY_PREPARATION_2026-11-08.md).

> **08/11 — E1 v2 đã đóng:** 280 train steps, 264 critic/132 actor updates, 2 full episodes và 6/6 development evaluations đạt integration. Đã sửa một lỗi map/trace epoch, dọn raw train sau audit; chưa xác nhận TD3 hơn classical hoặc mở campaign dài. [Kết quả và bước tiếp](docs/NINO_COMMON103_V2_INTEGRATION_RESULT_2026-11-08.md). Các cập nhật dưới đây là lịch sử.

> **08/11 — review PI/prestop/v2:** v2 mới có smoke64, 0 episode hoàn chỉnh; prestop vẫn unknown. Đã sửa metric, campaign disk/retention, observer/map v2 và outline Studio; chưa chạy thêm Gazebo/train. [Kết quả và ba bước tiếp theo](docs/NINO_PROJECT_REASSESSMENT_2026-11-08.md). Các cập nhật dưới đây là lịch sử.

> **08/11 — đã dọn run lịch sử:** xóa khoảng 9,44 GiB trong `rl_runs`; giữ dữ liệu Sim hiện tại ở `~/nino_research`, checkpoint 20k/25k/30k và bag thật. [Phạm vi và kiểm chứng](docs/NINO_LEGACY_RUNS_CLEANUP_2026-11-08.md).

> **08/11 — đã bỏ rough/rocky course:** giữ factory/flat; đã tách helper dùng chung và kiểm tương thích checkpoint TD3 20k/25k/30k. [Phạm vi xóa và kiểm chứng](docs/NINO_COURSE_RETIREMENT_2026-11-08.md).

> **08/11 — nâng cấp Chuẩn hóa TD3, Causal 10 Hz Pipeline & Studio QC:** bổ sung ma trận thực nghiệm `E1–E3`, khóa thứ tự tune 4 bước, cấm chọn checkpoint theo training reward đơn thuần, 7 cổng an toàn triển khai (`td3_experiment_matrix.py`), căn chỉnh nhân quả 10 Hz kèm mask thiếu dữ liệu (`causal_alignment.py` + `causal_frames.parquet`), chia tập theo nguyên phiên và mở rộng QC tự động (clock drift, gap `>2x`, command chain, `h1/h5/h8`); giữ nguyên toàn bộ hash lịch sử và `hardware_authority = 0`. [Chi tiết chuẩn hóa 08/11](docs/NINO_TD3_DATA_STUDIO_STANDARDIZATION_2026-11-08.md).

> **08/11 — chọn nhánh Sim offline:** đã chuẩn bị draft probe common correction trong0,5s trước source stop, neutral-reference parity và matrix12lượt đề xuất; **0allocated, chưa runner/batch/train mới**. Studio có outline Sim riêng với hardware. [Protocol và điểm dừng](docs/NINO_SIM_PRESTOP_AUTHORITY_DRAFT_2026-11-08.md).

> **07/11 — đối chiếu wheel/body đã xong:** bốn raw bags,95.459messages,100file khớp hash; V2 có final tiến/feedback nhưng operator báo không tiến, body còn unknown. Chuẩn bị một diagnostic có video, chưa cấp motion slot hoặc mở ba repeats. [Kết quả và bước tiếp](docs/NINO_WHEEL_BODY_GAP_REVIEW_2026-11-07.md).

> **07/11 — phân tích offline20k/25k/30k đã đóng:** 1.680eval packet và30.000train rows; mapping/reward khớp, actor cải thiện phase mở nhưng classical vẫn tốt hơn và critic chưa calibration. Chốt giữ classical cho clear-box/planned-stop; không tự cấp run mới. [Báo cáo](docs/NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md).

> **07/11 — continuation30k hoàn tất:** tổng20.000critic/10.000actor updates,6/6eval đạt task/stop; TD3 velocity RMSE cao hơn classical5,08–8,62% native, GT grids cùng chiều. [Đánh giá30k](docs/NINO_COMMON_TD3_30K_ASSESSMENT_2026-11-07.md).

> **07/11 — Studio thêm map và thống kê live:** scene SDF, pose/vệt GT/estimator, bảng episode/checkpoint và nhận xét Laya CPU riêng. [Cách dùng và giới hạn metric](docs/NINO_STUDIO_MAP_EPISODES_LAYA_2026-11-07.md).

> **07/11 — Studio đọc tiến độ train đang chạy:** tự tìm worker local khi mở lại GUI, hiển thị bước thêm/global, log và checkpoint; đóng observer không dừng worker ngoài GUI. [Correction và kiểm chứng](docs/NINO_STUDIO_LIVE_TRAINING_2026-11-07.md).

> **Lịch sử 07/11 — TD3 continuation20k→30k:** đã hoàn tất và review; ưu tiên classical cho envelope hiện tại. [Bàn giao và việc tiếp theo](docs/NINO_CLASSICAL_BASELINE_HANDOFF_2026-11-07.md).

> **07/11 — pilot TD320k hoàn tất:** 20.000transitions,10.000critic/5.000actor updates;6eval task/stop đạt. Chưa chứng minh hơn classical; [đánh giá và đề xuất continuation10k](docs/NINO_COMMON_TD3_20K_ASSESSMENT_2026-11-07.md).

> **Lịch sử 07/11 — pilot TD3 research20k:** đã hoàn tất, sau đó continuation tới30k. common103D/1D, cùng seed11, baseline Ki0,10. [Log lịch sử](docs/NINO_COMMON_STUDIO_TRAINING_RUN_2026-11-07.md).

> **07/11 — TD3 common103D/1D trong Studio:** smoke Gazebo64steps đạt,
>48critic/24actor updates; pilot20.000steps chuẩn bị, đang thiếu dung lượng
>đĩa (~7GiB cần/~5GiB còn). [Kết quả và bước tiếp](docs/NINO_COMMON_STUDIO_PILOT_2026-11-07.md).

> **Studio07/11:** training đã ở tab **Train TD3 · Sim** trong cùng Nino Studio; shortcut training cũ cũng mở Studio. Có smoke/timesteps/checkpoint/TensorBoard, điều hướng tới tham số và kiểm ngân sách vượt warmup. Trainer hiện là100D/2D, không tương thích checkpoint A103D/1D. [Hướng dẫn và cách chọn/tune tham số](docs/NINO_STUDIO_TRAINING_INTEGRATION_2026-11-07.md).

> **Đính chính TD3 — 07/11:** checkpoint A đã train1.024transitions thật (960critic/480actor updates), nhưng là pilot ngắn một seed; chưa đủ kết luận thuật toán. Ưu tiên chuẩn bị pilot training có ngân sách với baseline frozen. Validation Ki0,15 là nhánh riêng. [Chi tiết](docs/NINO_TD3_TRAINING_SCOPE_CORRECTION_2026-11-07.md).

> **Cập nhật07/11 — validation stop6s đã chuẩn bị offline:** 68software tests,18GUI tests; 4cell/560decisions coordinator synthetic và560transitions wrapper parity. **0Gazebo mới, release=false,0slot đã cấp**; chưa promote Ki hoặc trainTD3. Tiếp review/release riêng tối đa4lượt/560ticks. [Protocol/kết quả](docs/NINO_SIM_PI_STOP6_VALIDATION_PREPARATION_2026-11-07.md). Các cập nhật bên dưới giữ lịch sử.

> **Cập nhật 07/11 — PI screen Gazebo đã đóng4/4:** 560native ticks; Ki0,15 giảm native velocity RMSE21,7%/19,5%, GT grids cùng chiều. Path RMSE cao hơn nhưng <0,46mm trong screen này. Candidate chưa promote; tiếp validation riêng stop6s, chưa budget/train/hardware mới. [Kết quả](docs/NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md). Nội dung bên dưới giữ lịch sử.

> **Cập nhật 07/11 — PI runner/protocol đã kiểm offline:** 44 tests runner đạt; 4cell/560decisions synthetic, closure/timing/summary là fixture. Đã chuẩn bị ledger, source/install gates và release record có pins; **release=false/0slots**, chưa chạy Gazebo hoặc train. [Protocol/kết quả](docs/NINO_SIM_PI_SCREEN_RUNNER_PROTOCOL_2026-11-07.md). Các đoạn bên dưới giữ lịch sử.

> **Cập nhật 07/11 — PI screen đạt parity offline:** 49 software tests; 3.600 callbacks kernel và 560 transitions wrapper synthetic. Ki0,10 giữ đúng kernel cũ; candidate0,15 chưa có outcome Gazebo. Tiếp bounded runner/protocol/release riêng cho tối đa4lượt/560ticks; chưa cấp slot hoặc train. [Kết quả](docs/NINO_SIM_PI_SCREEN_OFFLINE_RESULT_2026-11-07.md). Các đoạn bên dưới giữ lịch sử.

> **Cập nhật mới nhất07/11 — Dynamics audit hoàn tất:** 1.260native rows giữ nguyên;8/9rawquery đầy đủ,1unknown do payload cùngstamp. Classical target→encoder RMS5,00–5,53mm/s; encoder→body0,040–0,400mm/s. Ưu tiên draft screen wheel PI trong Sim; chưa đổi gain/chạy thêm/train. [Kết quả](docs/NINO_SIM_DYNAMICS_AUDIT_RESULT_2026-11-07.md). Nội dung dưới giữ lịch sử.

> **Cập nhật 07/11 — Correction hold/update đã kiểm offline:** 44 test phần mềm, 143 quyết định synthetic và 1.260 shadow; 14 kiểm tra GUI đạt. Gain-ID và motion benefit còn unknown; không có Gazebo/training/hardware mới. Tiếp chẩn đoán lag/bias từ 9 run đã seal trước khi quyết định protocol riêng. [Tiến độ và việc còn lại](docs/NINO_SIM_STATUS_AND_TODO_2026-11-07.md). Các đoạn dưới giữ lịch sử.

> **Mới nhất06/11 — Gain baseline Gazebo đã đóng9/9:** 1.260ticks;283hashes/3.834support checks đạt,0actor/train. Causal/fixed native: +23,0% tại1; +29,8% tại0,98; −15,3% tại1,02. SoB0 còn sampling-sensitive ở1/0,98; chưa promote/learner. Tiếp correction estimator cổ điển offline. [Kết quả](docs/NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Backend/context gain đạt parity offline:** 41 software tests; 4.800 callbacks kernel và 840 transitions wrapper fixture, 0 Gazebo/train mới. Cùng gain=1 giữ observation/reward/reference/terminal, context ABI mới chặn checkpoint cũ. Tiếp runner/release baseline qualification riêng. [Kết quả](docs/NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Benchmark đã chốt offline:** giữ cổ điển cho clear known-stop; câu hỏi mới chỉ về gain common cố định chưa biết. Đã kiểm causal encoder candidate và phân rã 840 hàng cũ; 0 physics/training mới. Tiếp backend/context riêng, parity gain=1 trước qualification baseline. [Quyết định](docs/NINO_SIM_BENCHMARK_DECISION_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Mới nhất 06/11 — Eval reset-ready đã đóng 6/6:** 840 eval ticks, 0 train/optimizer. A seed11 có native velocity RMSE cao hơn cổ điển 71,5%/88,8%; hai GT grids cùng chiều. 199 hashes/2.561 support checks đạt. Giữ cổ điển cho clear known-stop; chốt benchmark trước training mới. [Kết quả](docs/NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md). Real cutoff vẫn 02/11; các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](docs/NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Coverage V2 đã đóng:** A seed11 hoàn tất, C seed11 partial; **1.864 replay /1.736 critic /868 actor updates,0eval**,15launches;49slot còn lại đóng. Lỗi initial drive readiness/permission, không phải thiếu joint của observer. Candidate correction chỉ kiểm offline; [kết quả](docs/NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Cập nhật06/11 — Coverage V2:** runner mới đã nối metadata vào full train path; preflight qua GUI **80 tests đạt**, GUI **54 tests đạt**, build2package. Chưa release physics hoặc có scientific train/eval mới. V1 vẫn đóng; [kết quả V2](docs/NINO_SIM_COVERAGE_V2_IMPLEMENTATION_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Sim06/11 — coverage V1 đã đóng:** [kết quả](docs/NINO_SIM_COVERAGE_RESULT_2026-11-06.md); thiếu metadata qualification_condition ở tick đầu.1launch/0replay/update/eval,không retry hoặc chạy bù. Correction riêng kiểm offline,chưa V2/hardware.

> **Sim06/11 — coverage runner/preflight:** [implementation](docs/NINO_SIM_COVERAGE_IMPLEMENTATION_2026-11-06.md); sampler/replay/optimizer/evaluator và GUI đã kiểm91tests. Profile Critic/coverage có preflight offline đạt, study chưa release. Scientific training/Gazebo/hardware mới0; kết quả cũ vẫn ưu tiên classical/B0.

> Cập nhật06/11: evaluation-only mới đã đóng, dùng ba checkpoint TD3 có sẵn; không train thêm. Xem [kết quả](docs/NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md) và [protocol](docs/NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md). Chưa promote/hardware.

> Cập nhật06/11: pilot TD3 RELIABLE với lifecycle từng episode đã đóng; xem [kết quả](docs/NINO_SIM_RELIABLE_TD3_RESULT_2026-11-06.md) và [protocol](docs/NINO_SIM_RELIABLE_TD3_PROTOCOL_2026-11-06.md). Chưa promote hoặc mở training/hardware mới.

> **Cập nhật06/11 — candidate joint RELIABLE:** fixturepaired1000messages +1handshake/pause100ms đạtcompatibility, cảBE/RELIABLE1000/1000; candidateB0stop6/8 đạt2launches/280ticks. GUI hai nút cógate +QC/metric;khóa stageđãđóng. Chưa optimizerload/training hoặc rootcauseproof, partialTD3700ticks giữ. Tiếp learnerfresh103D/1D protocol riêng. [Kết quả](docs/NINO_SIM_JOINT_RELIABILITY_RESULT_2026-11-06.md).

> **Cập nhật06/11 — joint diagnostic đã đóng2/2:**200zero ticks/612checks đủsupport; hai observer trùng15.220source stamps, payloadfield không lệch. Chưa tái hiện50ms, nguyênnhânunknown; khôngtraining/hardware hoặc reopenpartialTD3. GUI có profile và bảngage/parity/error. Tiếp tốiđa mộtcandidateQoSjointRELIABLE riêng, chưa áp/chạy. [Kết quả](docs/NINO_SIM_JOINT_BOUNDARY_RESULT_2026-11-06.md).

> **Cập nhật06/11/2026 — TD3 common103D/1D đã train partial:**700ticks/636critic +318actor updates,5training episodes đạt task/stop. Episode6 thiếu joint support50ms tại half-tick zero; batch đóng, seed22/33 +10eval chưa chạy. GUI có profile riêng và partial/error review, khóa retry. Chưa có learned-benefit comparison hoặc hardware. Xem [kết quả](docs/NINO_SIM_COMMON_TD3_RESULT_2026-11-06.md).

> **05/11 — wrapper103D/1D đã đạt Gazebo:**4/4launches,560ticks,replay560rows,actor/optimizer0. [Kết quả](docs/NINO_SIM_EQUAL_GAZEBO_RESULT_2026-11-05.md). Bước tiếp: fresh TD3 common-only pilot theo draft mới; chưa train hoặc resume V3.

> **05/11 — contract cùng preview đã đạt offline:**103D/1D common-only, shared window và requested replay;840bước fixture tổng hợp,optimizer/Gazebo0. Không resume V3. [Kết quả](docs/NINO_SIM_EQUAL_INFORMATION_RESULT_2026-11-05.md). Bước tiếp: kiểm wrapper mới trong Gazebo theo protocol riêng, chưa chạy.

> **05/11 — stop-time transfer đã xong:** 6/6 lượt,840ticks,actor/optimizer0. Common cổ điển có RMSE v thấp hơn cả3 B0 trên native và hai GT-header grids; giữ candidate, chưa promote. [Kết quả](docs/NINO_SIM_STOP_TRANSFER_RESULT_2026-11-05.md). Tiếp: contract TD3/cổ điển cùng thông tin, chưa mở train mới.

> **05/11 — đối chứng common cổ điển đã xong:** 6/6 lượt,840 tick,optimizer0. Whole-task RMSE v thấp hơn B0/frozen common ở cả hai lượt; giữ candidate có planned stop, chưa promote. [Kết quả và bước tiếp](docs/NINO_SIM_CLASSICAL_COMMON_RESULT_2026-11-05.md).

> **GUI train TD3:** smoke64, nhập timesteps, train/resume checkpoint, log/lỗi/kết quả và TensorBoard local. [Hướng dẫn](src/nino_pi/TD3_TRAINING_GUI.md).

> **05/11 — frozen-axis ablation đã xong:** 6/6 lượt, 840 evaluation ticks, không optimizer. Bỏ residual vi sai giảm lệch đường, nhưng common-only vẫn tệ hơn B0 về RMSE vận tốc toàn lượt do pha hạ tốc. Giữ B0; [kết quả, GUI và đối chứng cổ điển kế tiếp](docs/NINO_SIM_AXIS_ABLATION_RESULT_2026-11-05.md).

> **05/11 — TD3 V3 đã train và đánh giá:** guided baseline + zero-init + nominal reward; 512 train/496 updates, 8 eval. Tất cả marker/stop đạt, clear TD3 tracking tệ hơn B0; có một B0 gờ vượt gate được giữ. Chưa promote; [kết quả và hướng tiếp](docs/NINO_SIM_GUIDED_TD3_V3_RESULT_2026-11-05.md).

> **05/11 — screen guided clear/gờ 6 mm đã xong:** 4/4 marker + stop, 560 transition, residual zero. Gờ RMSE path 3,09–4,28 mm; chưa train TD3 mới. GUI hiển thị từng lượt; [kết quả và contract V3 kế tiếp](docs/NINO_SIM_GUIDED_CONTACT_RESULT_2026-11-05.md).

> **05/11 — V3 đã kiểm:** estimator wheel+IMU → follower → residual zero → PI đã chạy trong Gazebo. 8/8 marker + stop; RMSE path guided 13,09–13,84 mm, constant 93,06–93,65 mm. Không train thêm TD3. [Kết quả và bước tiếp](docs/NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md).


> **Nhánh sim 04/11 đã triển khai:** [B0 → TD3 h5 → evaluation](docs/NINO_SIM_BRANCH_RESULT_2026-11-04.md). GUI có tab NHÁNH SIM và bảng kết quả; không đợi real dataset.

> **04/11 — [Nino Real Data Studio v7](src/nino_pi/REAL_DATA_STUDIO.md):** recorder chỉ đọc + QC/export; [chuẩn hóa TD3 và định hướng](docs/NINO_TD3_DATA_STUDIO_STANDARDIZATION_2026-11-04.md). Các smoke trước giữ nguyên là bằng chứng lịch sử, không là deployment.

# Nino: contact-informed speed adaptation over low floor obstacles

> **Cập nhật 04/11 — [History / Governor / TD3 / GUI v5](docs/NINO_RESIDUAL_IMPLEMENTATION_2026-11-04.md):** đã có environment chạy, optimizer smoke TD3/PPO, portable actor và kiểm ROS/Gazebo fixture. Xem tab **Xây project** để kiểm artifact hiện hành. Train nghiên cứu và learned residual trên robot vẫn chưa mở; dữ liệu thật chưa được thu thêm trong cập nhật này. Các mục có ngày trước bên dưới giữ bối cảnh lịch sử.

> **Hướng hiện hành03/11:** [motion contract → SysID → B0/B1 → bounded velocity residual TD3/PPO](docs/NINO_RESEARCH_DIRECTION_2026-11-03.md). [GUI v4 thu bằng nút bấm](src/nino_pi/GUIDED_COLLECTION.md). Các training/config bên dưới là workflow lịch sử; YAML residual mới chưa được phép train/deploy.

## Current research scope — 17 October 2026

- [Post-reset standstill gate and four PI-only repetitions](docs/GOVERNOR_POST_RESET_PI_REPEATABILITY_2026-10-17.md).
  37 focused tests passed;4/4 gate, arrival/2sstop and reporting passed.
  Each gate confirmed0.5s standstill after reset and released at0.52s.
  Coarse approach balance passed, but same-seed crossing RMS differed2.74–3.36x
  and crossing slip up to23.7%. No further intervention or parameter selection.

- [Approach/contact and complete-sequence protocol preparation](docs/GOVERNOR_APPROACH_SEQUENCE_PLAN_2026-10-16.md).
  Offline tool read all six saved traces; four tests passed. Prepared a
  post-reset standstill gate and four PI-only repeatability attempts, not run.
  Online gate integration remains pending. Keep detector and reject200ms delay;
  preserve legacy scoring, all retriggers, failures and contact/recovery tails.
- [Offline seed77320 second-trigger audit](docs/GOVERNOR_SECOND_TRIGGER_AUDIT_2026-10-16.md).
  Wheel error reached 6.317 times threshold after right-wheel floor/cable
  load transitions and measured wheel reversal against a forward target.
  Keep detector; no correction or new episodes. Slip differences already
  existed before any reduced command, so delay causality remains unproven.
- [Six-case 200 ms brake-delay experiment](docs/GOVERNOR_BRAKE_DELAY_2026-10-16.md).
  Delay implemented opt-in; default remains 0 ms. All six arrival/2 s stop,
  reporting and timing checks passed. Candidate quality was mixed across
  seeds and mean tracking failed the existing limit; reject this candidate.
  No retries, extra delay sweep, tuning, predictor or PPO. Earlier entries
  below record status at the end of each historical experiment.
- [Eight-case 6 mm / 22 mm height screen: contact regime and braking-phase slip](docs/GOVERNOR_HEIGHT_SCREEN_2026-10-16.md).
  All eight arrival/2 s stop and reporting gates passed. First loaded contact
  changed from caster wheel (6 mm, 4/4) to bracket (22 mm, 4/4). Governor lowered
  crossing RMS in 4/4 pairs but slip in only 2/4; no promotion or tuning.
  Saved-case audit locates excess slip in braking. One 200 ms onset-delay
  hypothesis is prepared, not implemented or run; no automatic parameter sweep.
- [Two clean-floor cold starts: execute the frozen governor ramp](docs/MATCHED_RAMP_RESPONSE_2026-10-16.md).
  Both 12 s / 120-step maneuvers completed. Body reached 90% of braking change
  in 239–254 ms and recovery change in 254–279 ms. This separates plant response
  from obstacle impacts; it is not arrival/H2 quality or hardware validation.
  Keep PI/ramp fixed; a bounded two-height contact screen is prepared, not run.
- [Offline contact-to-command/body timing: separate contact slowdown from governor response](docs/GOVERNOR_CONTACT_TIMING_2026-10-16.md).
  In both governor repeats, body slowing began before the reduced command;
  fixed PI also slowed. Commands precede later driven-wheel contacts, but
  this does not identify motor latency or prove repeatable control benefit.
  Five timing tests passed; no new simulation, tuning or runtime changes.
- [Offline caster mechanical reference and hardware measurement sheet](docs/CASTER_MECHANICAL_REFERENCE_2026-10-16.md).
  Nominal clearance 9.03 mm / caster Ø32 mm confirmed from captured URDF/STL;
  real measurements are still missing. Corrected stale hardware documentation:
  modeled mass is 5.591 kg, not 4.689 kg. No physics/controller change or new run.
- [Four frozen governor/PI cold starts: repeatability and bracket-contact audit](docs/GOVERNOR_FROZEN_REPEATS_2026-10-16.md).
  All four arrival/2 s stop and reporting gates passed. Governor crossing
  RMS improved in both pairs, but whole-route RMS changed direction and
  large peaks were variable in both arms. No repeated RECOVER-specific deficit
  established. First named bracket manifolds have zero force; loaded samples
  follow 11–13 ms later. Match nominal 9 mm bracket clearance/Ø32 mm caster to
  hardware before changing physics or governor. No extra trials or learning.
- [Startup/feedback readiness correction: one sequential instrumentation pair](docs/GOVERNOR_READINESS_FIX_2026-10-16.md).
  Both arrivals/2 s stops passed; native replay and timestamp checks passed,
  with 6/15 ms drive feedback age and at least five diagnostics per action.
  Ride quality remains unresolved: governor recorded a 163.5 m/s² vertical
  peak during RECOVER near driven-wheel cable exit. Saved-trace audit completed;
  no broader validation, extra trials, predictor or PPO was started.
- [Bounded classical Optuna v2: 40 attempts, validation unavailable](docs/GT_GOVERNOR_OPTUNA_V2_2026-10-16.md).
  Six fixed target/max-hold candidates; equal 0.400 m/s cruise and a new fixed
  GT-timestamp objective. Candidate 0.90/1.0 s was selected before validation.
  35 attempts verified arrival/2 s stop; five had unavailable native outcomes,
  including two recorded startup feedback failsafes. Preserve every attempt;
  no default promotion, retry, PPO or predictor. Next is startup/feedback
  readiness repair, not more trials. Earlier bullets retain their historical scope.
- [Original GT timestamp slip audit: no new simulation](docs/gt_timestamp_slip_audit_2026-10-16/REPORT.md).
  Joint velocities aligned at unchanged GT samples. All 16 frozen cases retained:
  governor mean whole RMS +3.86%, crossing slip²/m +4.89%. Matched edge support
  gives nearly identical results; arbitrary grid choice does not explain the
  overall deficit. Native metrics, controller and study decision are unchanged.
- [Frozen governor: runtime instrumentation and four-scenario confirmation](docs/FROZEN_GOVERNOR_CONFIRMATION_2026-10-16.md).
  Completed exactly 18 arrivals/2 s stops. Native replay/timestamp checks pass;
  governor is 2.33% faster but mean whole slip RMS is 3.40% higher and sampled
  vibration RMS 4.58% higher on 16 confirmation episodes. Four of eight pairs
  reverse slip ranking with a 10 ms grid shift. Hold tuning; preserve all outcomes.
- [Slip timestamp telemetry and shared offline reporting](docs/SLIP_TIMESTAMP_REPORTING_2026-10-16.md).
  Exact native snapshot values/stamps are now logged with control traces;
  native metrics and study scores are unchanged. Route/crossing/phase reports
  share one 50 Hz pipeline. All six saved cases match the prior audit; legacy
  snapshot replay is explicitly unavailable. Nine offline tests pass; no simulator run.
- [Offline whole-route slip by phase, with common sampling](docs/governor_phase_slip_2026-10-16/REPORT.md).
  Six saved validation episodes audited; no new simulation or parameter change.
  Common-grid 50 Hz RMS was lower with governor in 3/3 pairs (mean −15.72%),
  but a 10 ms grid shift reduced the mean difference to −4.83%. Most slip
  was at the cable; recovery/cruise did not explain the native +7.32%.
  Preserve native scores; reconcile sensor timestamps/reporting before tuning.
- [Classical governor tuning: bounded crossing time/slip screen](docs/CLASSICAL_GOVERNOR_TUNING_2026-10-16.md).
  Completed 18/18 arrival/2 s stop checks. Selected scale 0.90/max hold 1.0 s
  on development, then froze it for three separate validation pairs: time
  −2.91%, local slip²/m −35.67%, tracking gate passed. Whole-route recorded
  slip RMS rose 7.32%, so keep a research candidate; no default/deployment
  promotion, impact claim, PPO or predictor. [Offline readiness audit](docs/governor_tuning_readiness_2026-10-16/REPORT.md).
- [Latest: frozen governor versus constant PI near the same completion time](docs/GOVERNOR_TIME_MATCHED_PI_2026-10-16.md).
  Ten additional arrival/2 s stop checks passed. Measured mean times were
  17.16 s versus 17.52 s: +2.098%, outside the declared 2% matching band.
  Governor post-contact RMS/peak/slip were lower in only two of five pairs;
  large sampled impacts occurred in both arms. No candidate promotion or
  predictor/PPO/Optuna. Next is a saved-trace audit, not another parameter sweep.
- [PI timing and randomized-order contact repeatability](docs/CONTACT_REPEATABILITY_TIMING_2026-10-16.md).
  Thirteen additional arrival/2 s stop checks passed. PI timing did not support
  another controller correction. The fixed sensor governor lowered post-contact
  RMS in all five pairs, with higher mean slip and completion time. Keep it as a
  research candidate; a time-matched PI comparison is still missing. No predictor,
  PPO, Optuna or hardware promotion was started; the bounded batch is complete.
- [Earlier governor continuation: collision correction, oracle authority and sensor-only quality failure](docs/GOVERNOR_CONTINUATION_2026-10-16.md).
  Eighteen arrival episodes and three clean-floor maneuvers completed. Capsule
  collision removed sampled distant-contact anomalies in the isolated E1 test;
  the sensor-only candidate fixed early triggers but did not pass quality.
  Predictor, PPO and Optuna remain held; no candidate promoted to deployment.
- [Reactive governor v1, contact logging and H2 experiment commands](docs/NINO_REACTIVE_GOVERNOR_V1_2026-10-14.md).
  IMU/encoder/drive-feedback governor implemented; predictive/RL extensions
  remain conditional on measured control authority and useful information.
- [Corrected clear-floor PI/contact baseline and replay evidence](docs/CLEAR_FLOOR_STABILITY_FIX_2026-10-15.md).
- [Three clear-floor repeats: arrival/stop pass, contact-quality review still held](docs/GOVERNOR_CLEAR_REPEAT_AND_CABLE_2026-10-15.md).
- [Mesh/solid-box comparison: contact artifact absent in three matched clear-floor box runs](docs/CLEAR_FLOOR_MESH_BOX_AB_2026-10-15.md).
- [Single cable on box floor: three arrivals, vibration/slip trade-off and precontact-trigger confound](docs/SINGLE_CABLE_BOX_SCREEN_2026-10-16.md).

The application goal is factory-floor navigation with low obstacles. The next
research gate is **repeatable sensor-only benefit across contact states**, using IMU,
drive-wheel encoders and requested/executed command history above wheel PI.
Obstacle positions, absolute pose, path progress, terrain preview and simulated
caster states are excluded from the sensor-only supervisor input.
Local post-contact authority has a positive oracle screen on one capsule
obstacle; wider feasibility and useful predictive information are unproven.

- [Restored six-cable flat corridor with actual carved adaptive potholes/grooves](docs/FACTORY_FLOOR_CONTACT_LAB_2026-10-13.md).
- [New map preview](docs/factory_floor_lab_preview.png).
- Four connected flat goal halls now surround the cable corridor: one goal
  each at E1 (6.45, 0), W1 (-1, 0), N1 (3.20, 2.75), S1 (3.20, -2.75).
  The current straight PI/smoke configs still target E1. The separate
  `factory_floor_routes_pi_check.yaml` enables straight E1, L-shaped N1/S1,
  and the clockwise W1 return loop for PI checks; route training is pending.
- [Drawn factory route preview](docs/factory_floor_routes_preview.png).
- Open after building: `ros2 launch nino_rl factory_floor_training.launch.py variant:=mixed headless:=false`.
- Start mechanism checks with `variant:=clear`, then isolated `cable`, `pothole`
  and `groove`. The mixed map is prepared for later integration, not validated.
- Static map PI config: `src/nino_rl/config/factory_floor_pi_check.yaml`.
- Runtime adaptive 1→6 mechanics: `src/nino_rl/config/factory_floor_curriculum.yaml`.
  The viewing world now uses an independent factory terrain template:
  four shallow bowls, one groove, six cables, a short cable and a local bump.
  Edit the terrain catalogue in `src/nino_description/config/factory_floor_lab.yaml`.
  Runtime resets replace the catalogue with the selected stage's sampled items.
  Both preserve the 6.45 m goal and 4 m corridor; the adaptive config replaces
  one continuous terrain mesh each reset: level ground with carved holes,
  and cables above it. Potholes are sampled between the actual angled cables.
  New sensor-only learning/data contracts are
  still required; no PPO or Optuna is started.

- [Earlier sensor-only reactive PI screening specification and commands](docs/FLAT_PROPRIOCEPTIVE_RESEARCH_2026-10-13.md).
- Specification: `src/nino_rl/config/flat_proprioceptive_research.yaml`.
- Preparation: `python src/nino_rl/scripts/prepare_flat_reactive_research.py`.
- Dry plan: `python src/nino_rl/scripts/run_flat_reactive_screen.py`.

**Rough training/tuning and combined-policy switching are deferred.** Their
maps, checkpoints, studies and results are preserved. The coordinate-triggered
flat schedule is a historical diagnostic, not evidence of sensor-only adaptation.
The new bundle is PI screening only; it blocks legacy PPO evaluation/training.
PPO and Optuna are not started by preparation or planning.

The cable obstacle model is a **rigid circular cylinder**, not a deformable cable.
New potholes/grooves are carved below a level floor with shared visual/collision
meshes; their crossing feasibility is not yet established. The earlier reactive
screen below retains its own cable-only map and immutable contract.
The caster-damping alternative is an unvalidated physical candidate, kept
separate from the original robot. The first screen compares full-speed and
reactive PI on three single-obstacle development layouts, twice each, with a
new simulator for each episode. Later quality claims require time-matched PI,
held-out scenarios and independent training seeds.

## Supported simulation scope

Factory/flat only. The abandoned terrain course and its commands/assets were removed on 08/11/2026.

## Legacy flat course with a success-gated curriculum

Use `combined_flat_curriculum.yaml` for a new PPO run, after stopping the old
flat Optuna tuner. It does not change the original flat study.
Stage 0 removes all cables and adaptive items to check physical goal
arrival. Stages 1–6 add the six cables one at a time, stages 7–9 widen their
angle range to ±10°, ±20°, and ±30°, and stages 10–15 add one adaptive item
at a time. The start and goal remain fixed. A stage advances after at least
75% ground-truth goal successes in its last 30 active-stage episodes. One in
five training episodes replays the preceding stage; replay outcomes do not
advance the current stage. Both the stage and its success window are saved in
normal PPO checkpoints.

In the flat simulator terminal, use the flat launch command above. In a second
terminal, use the same flat ROS domain and Gazebo partition, then check the
empty stage with the PI baseline before committing to a long training run:

```bash
ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/combined_flat_curriculum.yaml \
  --flat-stage 0 --episodes 12 --output rl_runs/flat_clear_baseline
```

If that check shows physical goal failures or large odometry drift, fix the
state estimate first. Otherwise, tune reward and PPO settings on **stage 1**
(one almost straight cable). Each trial trains its own model from the old
actor and evaluates that same fixed stage; it does not progress through all
16 stages. Use a new study directory so the original flat Optuna results stay
untouched:

```bash
python src/nino_rl/scripts/tune_split_optuna.py --section flat \
  --config src/nino_rl/config/combined_flat_curriculum_optuna.yaml \
  --device cuda --trials 8 --timesteps 30000 --eval-episodes 12 \
  --output rl_runs/flat_curriculum_optuna
```

The tuner writes `best_trial.yaml` (still locked to stage 1),
`best_curriculum.yaml` (unlocked for the full course), and `best_model.txt`
(path to the selected stage-1 model). Validate that model on new evaluation
seeds before the long run. If all trials still fail on one cable, inspect the
pose drift before increasing the trial budget.

The 2026-10-04 arrival checks found that stopping at the outer edge of the
20 cm odometry goal circle could leave the physical robot short. The opt-in
`combined_flat_curriculum_goal_margin.yaml` profile aims within 5 cm in
odometry while keeping physical success at 20 cm. It uses trial 6's tuned
PPO/reward settings and the unlocked curriculum. The old 1.5M actor scored
10/12 physical successes on one cable with this profile; the tuned actor
scored 8/12. These are nominal-course checks, not validation of the final
six-cable, six-item stage. See the [pretraining check report](docs/RL_PRETRAINING_CHECK_2026-10-04.md).

Start with a 50k-step curriculum pilot using this profile and the old actor.
The changed navigation contract requires `--init-model` rather than
`--resume`. Inspect physical success and stage advancement before extending
the pilot; the 2,048-step pipeline check remained at stage zero:

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_curriculum_goal_margin.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 50000 --checkpoint-every 10000 \
  --output rl_runs/flat_curriculum_goal_margin
```

To evaluate an intermediate checkpoint at a selected stage, pass
`--flat-stage 0` through `--flat-stage 15` to `ros2 run nino_rl evaluate`.
Without that option, evaluation uses the final six-cable, six-item stage. Use
fresh evaluation seeds and inspect physical success as well as odometry drift.

After the first 50k pilot, the clear-floor comparison measured 17/24 successes
for its actor, 12/24 for the old actor, and 22/24 for the PI baseline. Five
pilot goal misses kept moving at about 0.19–0.22 m/s after overshooting despite
the minimum approach reference. The opt-in
`combined_flat_curriculum_arrival_guard.yaml` profile tapers residual wheel
torques in the final 0.5 m of estimated path travel. See the
[arrival diagnosis and next training command](docs/FLAT_ARRIVAL_GUARD_2026-10-04.md).
Initialize that changed profile from the 50k pilot actor with `--init-model`;
its critic and optimizer start fresh. Localization drift remains unresolved.

The 2026-10-07 two-cable evaluation scored 11/24 physical successes for the
952,343-step final PPO and 23/24 for PI. Before extending that run, use the
[speed-only evaluation commands](docs/FLAT_SPEED_ONLY_CHECK_2026-10-07.md)
to retain PPO speed scaling while disabling its additive torque corrections.
This evaluates the saved policy with `--speed-only`; its weights are frozen.

The completed speed-only diagnostic scored 20/24 successes but averaged
28.61 s on successful episodes, missing the 22 s target. The new
`combined_flat_speed_yaw_pilot.yaml` profile uses two PPO outputs (speed and
bounded yaw reference) through PI, with zero additive torque. It also tightens
the estimated stop margin and raises minimum approach speed. Start a new
contract with `--init-speed-model` to reuse only the old actor's features and
speed output; the yaw head, critic and optimizer start fresh. See the
[20k pilot, Laya and matching PI comparison commands](docs/FLAT_SPEED_YAW_PILOT_2026-10-07.md).

## 1. Prepare Ubuntu and the NVIDIA GPU

Use Ubuntu **24.04**, its system Python **3.12**, and an NVIDIA-capable machine.
Run these commands on the machine that will actually train, not a separate
laptop without the GPU. Skip driver installation if `nvidia-smi` already works.

```bash
sudo apt update
sudo apt install git curl locales software-properties-common \
  python3-venv python3-pip build-essential ubuntu-drivers-common
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
ubuntu-drivers devices
sudo ubuntu-drivers install
sudo reboot
```

After reboot, `nvidia-smi` must list the intended GPU (for example RTX 4080).
Resolve driver/Secure Boot issues before installing RL dependencies. Installing
`nvidia-utils` alone does not install a working kernel driver. See
[Ubuntu's NVIDIA driver guide](https://documentation.ubuntu.com/server/how-to/graphics/install-nvidia-drivers/).

## 2. Install ROS 2 Jazzy, Gazebo, Nav2 and RViz

If `/opt/ros/jazzy/setup.bash` already exists, skip the ROS repository setup.
Otherwise enable Universe and install the official ROS apt-source package:

```bash
sudo add-apt-repository universe
NINO_ROS_APT_VERSION=$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
curl -fL -o /tmp/nino-ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${NINO_ROS_APT_VERSION}/ros2-apt-source_${NINO_ROS_APT_VERSION}.noble_all.deb"
sudo dpkg -i /tmp/nino-ros2-apt-source.deb
sudo apt update
sudo apt upgrade
sudo apt install ros-jazzy-desktop ros-dev-tools
```

Install the robot dependencies:

```bash
sudo apt install python3-rosdep python3-colcon-common-extensions \
  ros-jazzy-ros-gz ros-jazzy-ros-gz-interfaces ros-jazzy-gz-ros2-control \
  ros-jazzy-xacro ros-jazzy-robot-state-publisher ros-jazzy-controller-manager \
  ros-jazzy-effort-controllers ros-jazzy-joint-state-broadcaster \
  ros-jazzy-ros2controlcli ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox ros-jazzy-robot-localization ros-jazzy-rviz2 \
  ros-jazzy-tf2-ros
source /opt/ros/jazzy/setup.bash
```

Use the [official Jazzy installation guide](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
if repository packaging changes. `ros-jazzy-ros-gz` supplies the compatible
Gazebo integration; do not install Gazebo Classic for this project.

## 3. Get the source and apply the patch

For a fresh checkout:

```bash
cd ~
git clone --branch add_rl https://github.com/macminhtuan131/Ninobot_controlled_with_torque.git ninorobot
cd ~/ninorobot
```

For an existing checkout, enter its directory and check `git status`. Preserve
local edits before changing branches. The supplied patch was made against
`d015b8239648c64974e5badd041aa87f3a5a0fdc` on `add_rl`.

```bash
git rev-parse HEAD
git apply --check ~/Downloads/ninobot-rl-improvements.patch
git apply ~/Downloads/ninobot-rl-improvements.patch
```

Use the actual download path. If the check reports conflicts, stop and reconcile
the branch/local changes; do not force the patch or discard your work.
Skip applying the patch if these changes are already in your checkout.

Initialize rosdep once (skip `init` if already initialized), then resolve the
packages required by this training workspace:

```bash
sudo rosdep init
rosdep update
rosdep install --from-paths src/nino_description src/nino_control src/nino_rl \
  src/linorobot2/linorobot2_navigation --ignore-src --rosdistro jazzy -r -y
```

## 4. Create the Python environment and install CUDA PyTorch

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade --force-reinstall torch==2.13.0 \
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r src/nino_rl/requirements.txt
python -m pip check
python -c 'import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))'
```

The CUDA 12.6 wheel above is an explicit example from the
[official PyTorch version matrix](https://pytorch.org/get-started/previous-versions/).
Use a compatible NVIDIA driver. A `+cpu` wheel or `torch.version.cuda == None`
is wrong for this workflow. The system CUDA toolkit is not required just to use
these wheels. `--system-site-packages` is necessary for ROS Python modules;
`python3-venv` prevents the `ensurepip is not available` error.

## 5. Build with the venv interpreter

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-up-to nino_rl
source install/setup.bash
ros2 run nino_rl check_cuda
```

Expect `CUDA khả dụng: True`, the correct GPU, and a successful CUDA matrix
multiplication. Always use **`python -m colcon` inside the venv** so installed
Python entry points can import PyTorch. Do not move the venv after building.

For every new terminal, run these four lines first:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
```

## 6. Start simulation and check it

Set the endpoint and forward controller in `src/nino_rl/config/ppo.yaml`:

```yaml
goal_tolerance_m: 0.10
navigation:
  start_pose: [0.0, 0.0, 0.0]
  goal_pose: [6.0, 0.0, 0.0]
  straight_speed_m_s: 0.75
  minimum_approach_speed_m_s: 0.03
  goal_slowdown_distance_m: 0.50
```

The robot is successful only while its center is inside the 10 cm endpoint
circle and its heading is within 12 degrees of the path direction. Merely
crossing the goal plane no longer counts, so overshoots and lateral misses are
failures. The direct command always has
`angular.z = 0`; the residual policy may apply differential wheel correction to
counter drift while following the straight reference. The curriculum cable is
at `x=4 m`, leaving 2 m for recovery and drift measurement before the 6 m goal.
With `headless:=false`, Gazebo displays the goal as a bright green disc, pole,
and flag. The marker is visual-only and cannot collide with the robot or LiDAR.

Training starts with one adaptive hazard. One more is added after five
consecutive successful episodes. Any failure breaks the streak, and adding a
hazard clears the streak. The cap is eight adaptive hazards plus the single
phase cable. Rolling results and the
current hazard count are stored in every regular, final, and interrupted
checkpoint. The established pothole-like patches, low stepped bumps, short
transverse cables, and road-groove surrogates are randomized per episode inside
the four-metre training zone. Every center is uniformly sampled between the
left and right wheel-center lines (approximately ±17.1 cm). The 35 cm post geometry is classified as a blocking
route-planning obstacle and is never sampled or rewarded as a wheel-control
challenge. Adaptive geometry remains at full height in every phase: in
particular, the pothole basin keeps its 30 mm relief. The phase cable changes
diameter and skew; its tilt sign is randomized every episode, including the
easiest phase's ±5-degree cable.

The road groove uses two gently sloped, 20 mm-high shoulders around a 100 mm
floor-level transverse channel. This creates a physical relative drop for the
wheels. Gazebo cannot subtract a runtime hole from the hall floor, so it is a
local raised-road surrogate rather than below-world geometry.

Speed is a learned continuous action: PPO scales the 0.75 m/s straight
reference from 0 to 100% on every 0.1 s policy step. A 20 Hz downward-looking
LiDAR fan provides a fresh, deployable preview of low cable/terrain relief, in
addition to the forward safety LiDAR. Successful arrival before the 15 s target
earns a proportional bonus, while impact, slip, torque, timeout, and path terms
prevent "always full speed" from being the only useful strategy. TensorBoard
records mean/min/max speed scale and mean ground speed for every episode.

The other two actions are common and differential residual effort. They map
bijectively onto bounded left/right wheel torque, so PPO can increase one wheel,
decrease the other, or change both independently while the 500 Hz PI loop keeps
the requested wheel velocity stable. Acceleration is not a competing actuator
mode: it is the physical result of bounded torque, velocity targets, and the
controller's wheel-acceleration/slew limits.

Traversable challenges use one-shot privileged reward flags that are not added
to the actor observation. Flags require a powered wheel's swept footprint to
intersect the region, rather than merely passing a bump under the chassis.
This is a geometric crossing estimate, not a physical contact-force sensor.
Entering a challenge can earn at most +2 over the
whole episode, clearing its local forward edge at most +8, and a successful
goal earns up to another +90 in proportion to the fraction cleared. These
totals are divided across the episode's challenge count, so adding hazards does
not inflate the maximum return. Oscillation cannot collect a flag twice, and a
collision, rollover, timeout, off-path, or wrong-direction step earns no new
challenge bonus. Episode reports and TensorBoard include chosen/cleared counts
and fractions under `challenge_*` fields.

At phase 1, the randomized pothole is a 0.60 m round, 30 mm-deep relative basin with smooth
approximately 12.5-degree entry/exit ramps and a roughly 3 mm leading edge. It
is sized to admit the 16 mm caster wheels while still requiring useful drive
effort. Gazebo cannot subtract a randomly spawned shape from the existing flat
floor, so this is an annular raised-basin surrogate rather than a literal hole
below the hall floor; a true excavated hole would require replacing the floor
with a pre-cut mesh or heightmap.

Terminal A:

```bash
ros2 launch nino_rl training_sim.launch.py headless:=true
```

For visual debugging, stop that launch and restart with `headless:=false`.
Do not launch both copies. This training launch
starts the effort controller, sensors and Gazebo reset services. It does not
start Nav2, AMCL, a map server, or a planner.
It refuses to start if the same Gazebo world is already running; this prevents
multiple `/clock` and IMU publishers from corrupting lockstep training.
Wait for the simulator and controllers. Terminal B:

```bash
ros2 control list_controllers
ros2 param get /effort_drive accept_torque
ros2 topic hz /imu/data
```

Both `joint_state_broadcaster` and `wheel_effort_controller` must be active;
`accept_torque` must be `True`. Stop the topic-rate command with Ctrl-C.
The nominal IMU frequency is 50 Hz in simulation time. The training command
performs the mandatory 12-point preflight, including actuation, before learning.
Use `training_sim.launch.py`, not the standalone description launch, for RL.

## 7. Smoke-test, then train phase 1

Keep Terminal A running. Terminal B:

```bash
ros2 run nino_rl train --device cuda --phase 1 --timesteps 4096 --check-env
```

This is a plumbing test, not enough training to learn a useful policy. Once it
works, start the real run:

```bash
ros2 run nino_rl train --device cuda --phase 1 --timesteps 500000 \
  --checkpoint-every 25000
```

The run prints its directory, e.g. `rl_runs/20260917-123456-123456/`. It contains
`ppo.yaml`, software/device metadata, `monitor.csv`, `episodes.jsonl`, TensorBoard logs,
`checkpoints/nino_ppo_*_steps.zip` and `nino_ppo_final.zip` when finished.
Rollouts are 2048 steps, so SB3 can exceed the requested step count to complete
a rollout. Training is already active while those steps are collected; the
first PPO optimizer table does not appear until the first rollout completes.
Watch the live `EPISODE END` lines for collection progress. A 500000-step run
needs at least 50000 simulated seconds at 10 Hz,
plus reset/update overhead; actual wall time depends on Gazebo throughput.

Terminal C:

```bash
tensorboard --logdir rl_runs --port 6006
```

Judge learning using `episode/success`, `episode/timeout_failure`, and
`episode/endpoint_distance_m` together. `episode_reward/*` shows whole-episode
reward totals, while `reward_terms/*` shows per-step averages. The corrected
timing should keep `episode/max_clock_error_seconds` near zero and
`episode/max_motion_sensor_lag_seconds` below 0.04 s. Individual records are
saved in `episodes.jsonl`, including the termination reason and curriculum phase.
Revision 28 needs a fresh run; older models learned under different timing and
reward semantics. Restart the simulator after rebuilding so both lidar masks
exclude the decorative goal beacon.

Progress now measures reduction in actual endpoint distance, including lateral
misses and overshoot. The speed reference stays low after passing the goal;
more than 0.30 m longitudinal overshoot ends the forward-only task with
`goal_missed` and a failure penalty. An in-circle heading error retains a small
forward reference so PPO still has differential steering authority. Initial
Gaussian standard deviations are `[0.20, 0.12, 0.05]` for speed/common torque/
steering; each remains trainable. Watch `policy/std_*` and
`episode/goal_missed_failure` alongside the other outcomes.

Open `http://localhost:6006`. Inspect success, path RMSE/P95, completion,
heading RMSE, impact RMS, torque, reward terms and PPO KL/entropy together.
Gazebo uses lockstep training: every action advances exactly 50 two-ms physics
steps (0.1 simulated seconds), then waits for fresh sensor and torque feedback while
paused. Optimizer wall time therefore cannot consume the mission deadline.
CUDA memory usage alone is not evidence of successful learning.

A Ctrl-C or runtime transport failure saves `nino_ppo_interrupted.zip` if a
model exists; its unfinished rollout is discarded on resume. Fix the transport
problem before continuing. Resume only compatible v2 runs with their saved config:

```bash
ros2 run nino_rl train --device cuda --phase 1 --timesteps 500000 \
  --config rl_runs/YOUR_RUN/ppo.yaml \
  --resume rl_runs/YOUR_RUN/checkpoints/nino_ppo_25000_steps.zip
```

`--timesteps` is additional training. A saved but never-updated model is still
untrained. Training seeds are set by `seed` in the YAML; use separate configs
with different seeds for repeatability checks.

## 8. Evaluate baseline and PPO automatically

Stop the trainer; keep the same training simulation running. Run these commands
**sequentially**, using the real model/config paths printed by training:

```bash
ros2 run nino_rl evaluate_baseline --phase 1 --episodes 20 --seed 10000 \
  --config rl_runs/YOUR_RUN/ppo.yaml --output rl_runs/baseline-p1
ros2 run nino_rl evaluate --device cuda --phase 1 --episodes 20 --seed 10000 \
  --config rl_runs/YOUR_RUN/ppo.yaml --model rl_runs/YOUR_RUN/nino_ppo_final.zip \
  --output rl_runs/ppo-p1
```

Each command prints a timestamped report directory. It contains `summary.json`,
`episodes.csv`, a config/metadata snapshot, and for every completed episode:
`episode-001/trajectory.csv`, `actual.csv`, `reference.csv`, `metrics.json`, and
`trajectory.png`. `trajectory.csv` contains `time_s,x_m,y_m,yaw_rad,frame_id`
and can be loaded directly by pandas, a spreadsheet, or MATLAB. The PNG overlays
the fixed straight reference and the measured robot trajectory.
Automatic metrics
include time-weighted path/cross-track RMSE, P95/max path error, heading RMSE,
endpoint error, completion, backtracking, success, timing, slip, torque and IMU
impact. Incomplete evaluations are marked and cannot be compared as full runs.

```bash
ros2 run nino_rl compare_evaluations \
  --baseline rl_runs/baseline-p1/BASELINE_STAMP/summary.json \
  --candidate rl_runs/ppo-p1/PPO_STAMP/summary.json \
  --output rl_runs/comparison-p1.json
```

Compare **success first**, then errors/comfort and successful completion time.
A stopped or failed robot can have low RMSE. Reports separate all episodes from
successful episodes. The comparator checks phase, seeds, count, perturbation
mode and task config. Matching seeds reproduce the terrain draws; they do not
make asynchronous ROS/Gazebo execution bitwise deterministic.

`--randomized` on **both** evaluators tests full-strength residual/sensor
perturbations. These are not physical friction/mass changes.
The baseline receives zero residual torque, including under randomized testing.

## 9. Run all six cable phases automatically

Every phase has exactly one cable at 4 m. Training progresses from easy to hard;
only cable diameter and absolute angle define phase difficulty. The sign of a
nonzero angle is randomized so the policy does not favor one wheel.

Run one continuous training job with the default configuration:

```bash
ros2 run nino_rl train --device cuda --timesteps 600000 --check-env
```

Omit `--phase`: specifying it deliberately locks the run to one phase.
Steps 0–99,999 use phase 6, then phases 5, 4, 3, and 2 each receive
100,000 steps; phase 1 starts at step 500,000. Terrain changes on the first
episode reset after a boundary, so an active crossing is never interrupted.
The phase remains 1 after the schedule finishes. Resume preserves absolute
step progress and the hazard success streak. API checks do not advance the
schedule. PPO may finish its final rollout beyond the requested step budget.

| Phase | Difficulty | Diameter | Absolute angle |
|---|---|---:|---:|
| 1 | Hardest | 15 mm | 45 degrees |
| 2 | Very hard | 13 mm | 36 degrees |
| 3 | Hard | 11 mm | 27 degrees |
| 4 | Medium | 9 mm | 18 degrees |
| 5 | Easy | 7 mm | 9 degrees |
| 6 | Easiest | 5 mm | 0 degrees |

Domain randomization is disabled by default so the phase comparison is based
only on size and angle. Use `--randomized` during evaluation only when you
specifically want a robustness test.

Suggested initial gate: at least 19/20 held-out successes, no rollover/collision,
acceptable P95 path error (e.g. <0.25 m for this hallway), and no material comfort
regression versus baseline. These are proposed acceptance criteria, not measured
results. Use additional seeds for a final test, distinct from development seeds.

```bash
ros2 run nino_rl train --device cuda --timesteps 300000 \
  --config rl_runs/YOUR_RUN/ppo.yaml \
  --resume rl_runs/YOUR_RUN/checkpoints/nino_ppo_300000_steps.zip
```

Evaluate each phase using the same phase/seeds for baseline and PPO. The phase
schedule is step-based and does not wait for evaluation success. Keep several checkpoints; the final
one is not automatically best. Evaluate them on the same development seeds,
then test the chosen model on new seeds. Do not run an evaluation callback
against the same live world while the trainer is collecting a rollout.

## 10. Compare against your own ideal path or timed trajectory

A geometric reference CSV uses `x_m,y_m,frame_id`. An actual trace uses
`time_s,x_m,y_m,yaw_rad,frame_id`; yaw is optional. All coordinates must use the
same frame. The automatically exported files already follow this format.

```bash
ros2 run nino_rl trajectory_metrics \
  --actual rl_runs/ppo-p1/PPO_STAMP/episode-001/actual.csv \
  --reference rl_runs/ppo-p1/PPO_STAMP/episode-001/reference.csv \
  --mode path --output rl_runs/path-score.json --plot rl_runs/path-overlay.png
```

To compare with a scheduled ideal trajectory, give the reference a strictly
increasing `time_s` column as well, then use `--mode timed --max-gap 0.5`.
`position_rmse_m` compares interpolated positions at common simulation times;
there is no timestamp shift, rigid alignment, or extrapolation. Clock origins
must match. Exported time is relative to the first odometry sample; the episode
metrics record `clock_origin_sim_s` for converting absolute simulator timestamps. Long gaps, duplicate timestamps and frame mismatches are rejected.
Coverage is reported so an early-ending run cannot hide unobserved reference
time. Choose the gap limit according to your sampling rate, not to conceal loss.

A geometric straight path has no desired timestamps. Its default automatic score is therefore
**path RMSE**, not timed position RMSE. Poses are wheel odometry transformed by
localization, not external ground truth. For physical accuracy studies, export
motion-capture or correctly transformed simulator ground-truth poses instead.
Nearest-segment progress is ambiguous on self-crossing paths; use timed scoring
for such experiments. Do not concatenate several episode clocks into one CSV.

The scoring tools also work without ROS:

```bash
PYTHONPATH=src/nino_rl python -m nino_rl.trajectory_metrics --help
```

## Troubleshooting and scope

| Symptom | Action |
|---|---|
| `ensurepip` missing | Install `python3-venv`, recreate the incomplete venv |
| Torch `+cpu` / CUDA false | Install the CUDA wheel in the same venv; check driver; run `check_cuda` |
| Cannot import `rclpy` | Source Jazzy and use system Python 3.12 + `--system-site-packages` |
| `ros2 run` cannot import Torch | Rebuild Python packages with active venv and `python -m colcon` |
| Zero torque preflight | Use training launch, active effort controller, `accept_torque=True` |
| IMU coverage timeout | Check `/clock`, `/imu/data` stamps and load; the bounded wait handles delivery races but does not fabricate samples |
| Resume contract error | Use matching post-update run/config, or start a new run |
| No `/cmd_vel` subscriber | Rebuild `nino_control`, restart the simulation, and rerun preflight |

This patch does not introduce SWAE, a 3D terrain map, an ESKF, Isaac Lab,
asymmetric privileged critics, or unvalidated slope balancing. The existing
terrain-preview input is now driven by the simulated downward LiDAR. Hardware
deployment requires an equivalent calibrated producer; simulation alone cannot
establish transfer performance. See the design note for the selection rationale
and exact reward.
