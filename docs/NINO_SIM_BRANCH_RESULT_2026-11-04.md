# Kết quả triển khai nhánh sim trước — 04/11/2026

## Quyết định

**Đã triển khai và chạy xong:** B0 feasibility → TD3 h5 256 transition →
fresh-launch B0/B1/TD3 evaluation trên actual Nino URDF/caster và wheel PI
trong Gazebo. Không cần real dataset để thực hiện các job này.

**Chưa promote checkpoint.** TD3 tăng progress/return trong một lượt nhưng
chạy reference nhanh hơn, lệch ngang lớn hơn và chưa dừng tại horizon 10 s.
Trước khi mở train dài, cần sửa định nghĩa task/reward và đo đủ stop phase,
đồng thời giữ vấn đề repeatability/contact của baseline trong phạm vi sim.
Không đặt thêm gate “phải thu xong real data mới train TD3”.

## 1. Những gì đã xây và chạy

- `residual_sim_pilot.py`, `residual_sim_pilot_v1.yaml`,
  `residual_sim_pilot.sh`: ba job hữu hạn, file lock, deadline, dependency,
  source/world hashes, raw/trace, replay/actor audit và giữ failures.
- GUI **Xây project → NHÁNH SIM**: ba nút theo dependency, progress/log,
  hủy job, xem kết quả và bảng metric. Không cần Pi/collector/RC.
- Baseline/shaping/physics giữ nguyên: policy 100 ms, physics 1 ms,
  cruise 0,2 m/s, wheel-linear acceleration bound 0,1 m/s², torque residual
  tắt, wheel PI Kp 0,3/Ki 0,1, torque cap 4 Nm, effort slew 10 Nm/s.
- History 20×5=100D; action common/differential wheel-linear, projection
  giữ nguyên. TD3 MLP 32×32, warmup 16, batch 32, replay 2048 là profile
  **pilot**, không phải bộ hyperparameter tối ưu hoặc train hội tụ.

Protocol: [NINO_SIM_BRANCH_PROTOCOL_2026-11-04.md](NINO_SIM_BRANCH_PROTOCOL_2026-11-04.md).

## 2. Baseline feasibility hiện hành

| Scenario | Body x cuối | Qua marker x=0,95 m? | Quan sát |
|---|---:|---|---|
| Solid-box sạch, hall factory | 1,4684 m | Có | Body→executed-ref RMSE 0,00594 m/s |
| Solid-box + rigid cylinder C1 Ø6 mm | 1,4579 m | Có | Được chọn cho pilot, chưa là envelope đã xác nhận độ lặp |
| Factory mixed nguyên bản, C1 Ø22 mm | 0,3080 m | Không | Wheel-speed spikes tới khoảng 11,65 rad/s; lượt này chưa có C1 manifolds |

World mixed gốc không bị sửa, không thêm box dưới mesh chứa hõm/rãnh. Hai
world controlled là file mới chỉ tái sử dụng hall, Nino và backend. Không
gọi chúng là vượt xong factory E1 6,45 m hoặc mô phỏng dây mềm.

**Giới hạn cơ chế:** mixed mới nhất chậm trước C1, nên không thể quy toàn
bộ failure cho gờ 22 mm. Lượt mixed trước có bracket–C1 manifolds; các lượt
khác nhau và phải giữ riêng. Mesh/contact/backend/reset vẫn cần phân biệt.

**Repeatability còn yếu:** lượt B0 gờ 6 mm trước correction dừng ở x≈0,6802 m;
lượt hiện hành tới 1,4579 m. Correction RPC/clock không chứng minh là nguyên
nhân cải thiện traversal. Fresh launch không khôi phục toàn bộ physical state,
seed 701 không chứng minh Gazebo noise/contact state giống nhau. Không gộp
các revision hoặc biến chúng thành nhiều training seed độc lập.

## 3. TD3 đã train thật trong simulator

Artifact:
`~/nino_research/sim_branch_pilot_v1/20261104T080431003518Z_sim-train/`.

- 256 transition, learner seed 7, tối đa ba episode.
- **240 optimizer updates**, actor parameter L1 change ≈47,0357.
- Replay kiểm **256/256** observation/action/next-observation/reward và
  done/timeout semantics. Action trong replay là proposal trước projection;
  requested/accepted/final/target/feedback giữ trong trace riêng.
- Actor NumPy so SB3: max inference error **1,1921×10⁻⁷**.
- Có `model.zip`, replay, actor export, ABI/config/provenance; không resume
  checkpoint thất bại trước và không cho actor xuất torque/PWM/CAN.

Đây là bằng chứng optimizer/inference/physics integration và pilot behavior,
không phải convergence, novelty, H1/history benefit hay sim-to-real.

## 4. Evaluation mới: một rollout mỗi arm

Scenario `box_c1_6mm`, cùng source nominal/shaping/horizon; mỗi arm có một
fresh launch. B1 dùng yaw P gain 0,6 cố định, **chưa được tuned**. Evaluation
TD3 deterministic, không exploration noise. Không có CI/claim thống kê.

| Metric | B0 | B1 yaw | TD3 h5 |
|---|---:|---:|---:|
| Body x cuối, m | 1,4557 | 1,2043 | 1,6221 |
| Tới marker 0,95 m, s | 6,60 | 8,10 | 6,20 |
| Lateral RMSE, mm | **2,977** | 59,535 | 8,927 |
| Yaw RMSE, rad | **0,00793** | 0,17608 | 0,04911 |
| Body→executed-ref RMSE, m/s | **0,02670** | 0,08300 | 0,03001 |
| Body→nominal-ref RMSE, m/s | **0,07817** | 0,11693 | 0,08666 |
| Mean executed v, steady 3–8 s, m/s | 0,2000 | 0,2000 | **0,2235** |
| Body v cuối, m/s | **0,00183** | 0,03649 | 0,03707 |
| Return | 14,2363 | 11,4958 | 15,8902 |

TD3 tăng reference steady khoảng 11,7% và x cuối khoảng 11,4% so B0 trong
lượt này. Vì vậy progress/return cao hơn không chứng minh cải thiện ở cùng
tốc độ/throughput. Lateral và nominal tracking kém hơn B0; yaw/stop cũng
không cho căn cứ promote. Sampled vertical acceleration proxy thấp hơn B0
trong lượt TD3, nhưng chưa có phép so contact risk/damage có coverage hoặc
độ lặp đủ để kết luận lợi ích này.

### Stop phase là một vấn đề của thiết kế task

Source baseline về zero ở elapsed 8 s; projection vẫn có ramp từ reference
trước đó. TD3 có thể đưa reference lên khoảng 0,24 m/s: với bound 0,1 m/s²,
thời gian hạ reference đơn thuần có thể tới khoảng 2,4 s, chưa kể body lag.
Cửa sổ hiện chỉ còn 2 s. Ở sample cuối:

- B0 accepted/final reference = 0, body v ≈0,00183 m/s.
- TD3 accepted/final reference vẫn ≈0,02412 m/s, body v ≈0,03707 m/s.

Không phải actor tự tạo residual từ baseline zero: source cho residual zero,
nhưng reference có lịch sử và ramp. **Timeout không được gọi là đã dừng hoặc
task success.** Không kéo dài cửa sổ rồi thay kết quả hiện tại thành pass.
Protocol tiếp theo phải định nghĩa stop completion/maximum stop budget và
chi phí thời gian trước khi chạy.

## 5. Hai lỗi engineering đã sửa, tất cả artifact giữ lại

| Attempt | Kết quả |
|---|---|
| Baseline `075008377630Z` | Hoàn thành revision đầu; 6 mm không tới marker |
| Train `075446718330Z` | Lỗi GetParameters response timeout, **0 transition**; partial model/replay giữ riêng |
| Baseline `075725817397Z` | Clear-floor hoàn thành; lỗi float future tại reset case tiếp |
| Baseline `075951409906Z` | Revision hiện hành hoàn thành ba scenario |
| Train `080431003518Z` | 256 transition/240 updates, replay/export audit đạt |
| Evaluate `080705305625Z` | B0/B1/TD3 mỗi arm 100 transition, giữ toàn bộ outcome |

Các tên rút gọn đều có prefix ngày `20261104T` trong root pilot. RPC chỉ
được retry tối đa một lần vì là read-only; physics multi-step vẫn một request
và yêu cầu clock/iteration hoàn thành chính xác. Clock được chuẩn hóa theo
nanosecond; future thật +1 ns vẫn fail. Không sửa gain/current/reward để làm
TD3 hoặc B0 thắng. Fingerprint revision trước/sau khác nhau, không vá hash cũ.

## 6. Measurement và artifact

- Native scoring 100 ms; GT/IMU khoảng 50 Hz, wheel source nhanh hơn.
- Các thống kê gap trong `summary.json` bao gồm startup/settling. Analysis
  derived tính lại riêng policy window để tránh quy gap startup thành gap
  scoring. Giữ source clock và callback receipt monotonic riêng.
- Contact giữ manifold/name/count, không có loaded-force threshold; không
  là force/risk label. GT chỉ phục vụ reset/reward/evaluation, không vào actor.
- Toàn bộ file được kê trong manifest của mọi attempt đã được kiểm SHA256;
  analysis/plots nằm ngoài các thư mục experiment, raw không sửa.

Root experiment: `~/nino_research/sim_branch_pilot_v1`.
Derived analysis: workspace triển khai
`artifacts/sim_branch_pilot_2026-11-04/analysis.json`, `pilot_trace.png`.
Không có hardware session/SSH/flash trong cập nhật này.

Kiểm chứng: **34 test simulation/reference và 14 test GUI đạt**; bốn package
ROS build đạt, Pi/RL đã repackaged vào workspace. Ba job hiện hành có **1828/1828
physics requests completed, 0 retry**; 18 parameter readbacks trong các job này
đều hoàn thành. Đã lưu snapshot 48 source/config/asset files. GUI đọc đúng ba
artifact hiện hành, progress 100% và ba dòng metric, không tự khởi chạy job.
Xem [JSON kiểm chứng](NINO_SIM_BRANCH_VERIFICATION_2026-11-04.json).

## 7. Công việc tiếp theo trong sim

1. **Chuẩn hóa task/reward/stop v2 trước train dài.** Phân biệt tracking đúng
   nominal profile với tự nâng tốc độ; so speed/time-matched classical baseline.
   Episode cần đánh giá tới accepted zero và body outcome trong stop budget
   đã định trước, không chỉ timeout 10 s.
2. **Đo độ lặp baseline tại 6 mm và kiểm pre-contact mixed.** Thu thêm caster
   state nếu interface đã có, giữ cấu hình/tải/ramp/physics; đặt một protocol
   hữu hạn theo câu hỏi, không randomization rộng để che model mismatch.
3. **Sau khi task/baseline rõ:** mở pilot train v2/multi-seed và h1/h5/h8
   ablation trong ngân sách riêng. Real data không là prerequisite cho bước
   này; nó cần cho calibration/model discrepancy và deployment song song.

Checkpoint hiện tại tiếp tục ở trạng thái **không promote**. Kết quả nhỏ
mẫu không chứng minh TD3 không thể có ích; nó cho thấy chưa nên đồng nhất
return/progress với chất lượng chuyển động hoặc bỏ qua baseline mạnh.
