# Sim task/reward/stop v2 — protocol trước khi chạy

Ngày 04/11/2026. User đã yêu cầu tiếp tục nhánh sim; không phụ thuộc real
dataset, không SSH, flash, enable hoặc command robot thật. V1 giữ nguyên.

## Câu hỏi và quyết định

Reward tracking theo một profile cố định có tránh được cách lấy progress bằng
tăng tốc ở v1, trong khi hoàn thành cả pha đi và dừng? Đây là pilot chức năng,
không phải kiểm định TD3 hội tụ hoặc generalization. Một learner seed 7.

1. **Baseline:** clear box và box + C1 rigid cylinder Ø6 mm ở x=0,65 m,
   mỗi điều kiện hai fresh launches. Mixed 22 mm không chạy lại; v1 đã cho
   thấy biến thiên và vấn đề trước tiếp xúc, chưa có giả thuyết mới đủ cụ thể.
2. **Chọn môi trường:** chỉ chọn 6 mm nếu cả hai B0 tới mốc x≥0,95 m và
   dừng đạt. Nếu không, chọn clear khi cả hai clear đạt. Clear fail hoặc lỗi
   measurement/physical envelope: dừng trước learning, giữ artifact.
3. **Train:** checkpoint mới, tối đa 512 transition, h5 100D, profile smoke
   MLP 32×32, replay 2048, warmup 16, LR 0,0003; không resume v1. Tối đa
   bốn episodes, episode cuối có thể chưa hết task. Không gọi là train hội tụ.
4. **Evaluate:** B0, B_speed_control, TD3_h5, TD3_h5, B_speed_control, B0.
   Hai fresh launches/arm, thứ tự đối xứng chỉ giảm confound thứ tự; không
   phải counterfactual cùng physical state hoặc nhiều training seeds.

Tối đa 1.912 transition cho ba stage, 14 fresh launches, 1.800 s wall/stage.
Không tự thêm lượt hoặc retry multi_step. Failure được giữ, không thay bằng
success cũ. Tối đa một correction phần mềm có nguyên nhân cụ thể; revision
mới phải giữ artifact cũ và công bố khác biệt trước khi chạy lại stage.

## Task, reward và dừng

- Nguồn chuẩn: zero 0–0,5 s; +0,2 m/s từ 0,5 đến 8 s; zero sau đó.
- Wheel-linear ramp 0,1 m/s², residual per-wheel ≤0,04 m/s. PI/geometry/
  collision và actor ABI giữ như v1, không đổi gain hoặc torque/current.
- B0 target reward được tạo bằng **một composer zero residual riêng** từ
  đầu episode. Reference này không dùng previous accepted của policy.
- Reward không có positive progress. Mỗi bước dt=0,1 s:
  `−dt[(e_v/0,2)² + 0,2(e_yaw/0,5)² + 0,5(y/0,05)² +
  0,01||a||² + 0,02] − 0,001||a−a_prev||²/dt`.
  GT body/y chỉ vào nhãn reward/evaluation, không vào observation.
- B_speed_control dùng common residual cố định +0,02348807 m/s, chính là
  mean boost quan sát v1, qua cùng projection. Đây là đối chứng diagnostic
  cho giải thích “đi nhanh hơn”; chưa là baseline tuned hay speed/time match
  chính xác với TD3 v2. Không gọi progress cao hơn là tracking tốt hơn.
- Cửa sổ cố định **14 s cho mọi arm**, không thưởng bằng kết thúc sớm.
  6 s pha dừng > 2,4 s giảm reference cực đại + 2 s quiet + 1 s allowance.
  Allowance là đề xuất sim, không là bảo đảm actuator/body response.
- Quiet đòi cùng lúc: accepted wheel reference ≤1e−6 m/s, GT speed norm
  <0,01 m/s, |GT yaw rate|<0,05 rad/s, cả wheel |speed|<0,15 rad/s.
  Cần quiet liên tục 2 s ngay trước deadline, sau source zero.
- Task success = đã đạt x≥0,95 m + quiet đạt + không physical failure.
  Đứng yên/mắc ở gờ không là success. Phạt cuối task: thiếu mốc −5;
  chưa dừng −10. Physical failure −10, true terminal ngay.
- Deadline 14 s thuộc **định nghĩa task**, success/miss đều true terminal;
  không phải external time-limit truncation để bootstrap. Cutoff 512 của
  training có thể nằm giữa episode và không tự tạo terminal giả.
- Observation chưa thêm thời gian/pose: vẫn partial observability, h5 chỉ
  0,4 s lịch sử. Không tuyên bố Markov đầy đủ hoặc policy đã biết deadline.

## Dữ liệu / reporting

Primary: body-v RMSE so **nominal shaped profile độc lập**, với task success
và stopping làm điều kiện; lateral/yaw RMSE là constraint mô tả. Secondary:
body→executed RMSE, marker time, final x/speed, wheel error, reference
modification, source zero/shaped zero/continuous body-stop timing.

Ghi raw IMU, drive wheels, drive telemetry, GT, contact manifolds và caster
joint positions/velocities nếu JointState thực sự cung cấp. Caster chỉ là
audit nhãn, không sửa reset hoặc trở thành privileged policy feature.
Thiếu caster field phải ghi unknown, không đoán hướng caster từ seed.
Contact manifold không là loaded force/slip/damage. Coverage/gaps phải tách
startup khỏi cửa sổ task, không suy loss-free từ count.

Không có effect tối thiểu được chấp nhận; báo từng lượt và range hai lượt,
không CI, không gộp evaluation seeds thành training seeds. Effect nhỏ,
arm outcomes trái chiều hoặc grid-sensitive → unknown. Không promote policy
hoặc mở hardware từ pilot này. Nếu B0 không repeat được qua gờ, ưu tiên
clear-floor task + cơ chế caster/contact trước generalization/ablation.

## Artifacts và GUI

Root mới: `~/nino_research/sim_task_v2`. Ba action `sim-v2-baselines`,
`sim-v2-train`, `sim-v2-evaluate`, config/protocol, raw traces, result,
checkpoint task ID + actor ABI, dependency manifest SHA và source fingerprint.
V1 ở `~/nino_research/sim_branch_pilot_v1` giữ để xem lịch sử.

GUI chỉ bấm chạy job local, hiển thị phase, task success/stop, RMSE và log;
không cần copy commands hoặc thu data thật trước. Hủy giữ partial artifacts.
