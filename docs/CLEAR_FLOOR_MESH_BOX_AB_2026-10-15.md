# Đối chứng collision mesh và hộp phẳng — 15/10/2026

**Theo dõi:** [screen một cáp trên nền hộp, ngày 16/10](SINGLE_CABLE_BOX_SCREEN_2026-10-16.md).

## Kết luận

**Đổi riêng collision sàn sạch sang một hộp có độ dày đã loại bỏ các
manifold caster có pháp tuyến đứng trái dấu trong log và làm chuyển động
ổn định hơn ở cả ba seed được kiểm tra.** Robot, PI, estimator, ramp, reward,
control timing và physical scoring giữ nguyên.

Đây là bằng chứng mạnh rằng **representation/contact của sàn mesh trong
cấu hình mô phỏng hiện tại góp phần gây lỗi**. Chưa tách được tác động của
mesh không có độ dày với khác biệt thuật toán collision mesh/box của engine;
không kết luận mọi mesh đều sai hoặc đã chứng minh một bug tổng quát của DART.
Những cải thiện dưới đây là sửa mô phỏng, **không phải thành tích RL**.

## 1. Thay đổi duy nhất và kiểm tra đối chứng

| Thành phần | Mesh tham chiếu | Hộp đối chứng |
|---|---|---|
| Collision | Hai tam giác phẳng, winding +Z | Box 10 × 7 × 0.1 m |
| Mặt sàn | z=0 | z=0; tâm hộp tại (3, 0, -0.05) |
| Diện tích đỡ | x=[-2,8], y=[-3.5,3.5] | Giống mesh |
| Visual | Mesh sàn cũ | Giữ nguyên visual đó |
| Ma sát, walls, goal, physics | Cấu hình hiện tại | Giữ nguyên |
| Robot và wheel PI | Caster damping 0.001; PI cũ | Giữ nguyên |

World mới là `factory_floor_clear_box_contact_lab.sdf`; source world mesh
không bị ghi đè. Static tests xác nhận toàn bộ cây SDF giống nhau sau khi bỏ
riêng `terrain_collision/pose` và `terrain_collision/geometry`.

Provenance cho cả ba cặp seed đã đạt:

- **URDF SHA-256 trùng khớp**, không chỉ so tên profile.
- Resolved evaluation config giống nhau sau khi bỏ metadata khai báo
  `simulation_model.floor_collision_control` của candidate.
- Parent-world SHA-256 trong candidate khớp world mesh logger đã ghi.
- Physics 1 ms, control interval 0.1 s, PI toàn tốc và zero residual torque.
  Không nới sensor/clock checks. Ba lượt box có max clock error ≤6.40e-14 s,
  max motion sensor lag ≤0.035 s.

So sánh dùng các cold start cùng seed, **không phải restore cùng snapshot**.
Mesh là ba lượt đã lưu trước đó; không chạy lại để chọn một baseline thuận lợi.

## 2. Kết quả từng seed

Physical RMSE lấy từ ground truth độc lập. Slip là metric longitudinal
wheel-slip của dự án trong mô phỏng, không là phép đo slip thực đã hiệu chuẩn.

| Seed | Floor | Physical arrival | Thời gian (s) | Physical RMSE (cm) | Vertical RMS (m/s²) | Vertical peak (m/s²) | Slip RMS | Max abs pitch (°) | Dừng 2 s |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 76000 | Mesh | Có | 16.90 | 0.865 | 8.127 | 226.833 | 0.07763 | 3.173 | Đạt |
| 76000 | Box | Có | 16.50 | 0.324 | 0.932 | 6.980 | 0.00974 | 0.043 | Đạt |
| 76001 | Mesh | Có | 18.30 | 1.959 | 2.959 | 49.605 | 0.29071 | 2.803 | Đạt |
| 76001 | Box | Có | 16.50 | 0.309 | 0.666 | 5.056 | 0.00377 | 0.050 | Đạt |
| 76002 | Mesh | Có | 17.80 | 0.687 | 2.920 | 23.849 | 0.21688 | 2.674 | Đạt |
| 76002 | Box | Có | 16.50 | 0.310 | 1.203 | 9.840 | 0.01642 | 0.041 | Đạt |

Trung bình mô tả của ba seed: vertical RMS 4.669 → 0.934 m/s²; slip RMS
0.19508 → 0.00998. Các số này không là confidence interval hoặc bằng chứng
tổng quát hóa. Rung còn biến thiên trên box; không tuyên bố mô phỏng hoàn hảo.

Sai số đích vật lý của box là **0.19828 / 0.19843 / 0.19850 m**, vẫn trong
ngưỡng 0.20 m nhưng sát biên. Giữ nguyên arrival scoring; screen ba seed chưa
chứng minh arrival robustness ở mọi tình huống. Cả ba stop window đều có
coverage/feedback hợp lệ và đạt cùng diagnostic 2 s đã dùng ở baseline.

## 3. Cơ chế contact và phản hồi motor

| Seed | Peak lực điểm caster, mesh → box (N, trường được ghi) | Manifold caster có normal_z gần +1 và -1, mesh → box | Sample motor gần dừng khi target dương, mesh → box |
|---|---:|---:|---:|
| 76000 | 222626.9 → 40.79 | 62 → 0 | 1 → 0 |
| 76001 | 276101.4 → 40.33 | 171 → 0 | 5 → 0 |
| 76002 | 281522.0 → 39.19 | 124 → 0 | 27 → 0 |

Các count contact chỉ tính **manifold được logger lấy mẫu**, không phải mọi
physics step. Điều kiện diagnostic là cùng manifold có normal_z<-0.9 và
normal_z>0.9. Box có khoảng 2972–2976 sampled caster manifolds mỗi episode;
không thấy pattern hai chiều đó trong dữ liệu đã ghi.

Peak lực điểm không bằng lực tổng lên robot. Ở mesh, lực điểm lớn theo các
normal ngược nhau có thể gần triệt tiêu; không gọi 223–282 nghìn N là lực
tổng đã xác nhận. Tổng wrench có dấu của một manifold cũng không tự là
whole-body force hoặc impulse. Candidate box làm thay đổi chính pattern
contact này, đồng thời giảm pitch, motor tracking error và IMU peaks.

Max wheel tracking error trong các sample target>2 rad/s giảm từ
6.70 / 7.29 / 9.11 xuống **0.86 / 0.83 / 0.84 rad/s**. Không có sample motor
gần dừng theo cùng phép kiểm tra. Các tỷ lệ lăn caster vẫn cần đọc cùng
contact/load evidence; không suy ra slip chỉ từ tốc độ quay khi bánh thiếu tải.

## 4. Một lượt khởi tạo bị gián đoạn được giữ nguyên

Lần đầu chạy box seed 76002 gặp
`Assisted odometry cannot interpolate across an IMU gap` **trước khi episode
bắt đầu**, không có control trace hoặc physical outcome. Lỗi gốc được giữ tại:

`rl_runs/governor_clear_box_AB_confirm_2026-10-15/seed_76002_full/`.

Lượt này không bị biến thành success hoặc physical failure. Chạy lại cùng
config/seed trong ROS domain riêng đã hoàn tất. Báo cáo có **ba completed
episodes cho ba seed, cùng một pre-episode measurement abort**, không phải
"mọi lần khởi động đều thành công". Chưa sửa hoặc nới estimator trong đối chứng.

Gazebo vẫn có segfault ở giai đoạn shutdown của Contact system; log được
giữ. Nó không được tính thành crossing failure hoặc bằng chứng governor có ích.

## 5. Phạm vi sử dụng kết quả

Có cơ sở dùng **solid box làm sàn phẳng tham chiếu** cho các kiểm tra contact
tiếp theo. World mới chỉ là clear-floor control, không chứa cáp hoặc hõm.
Các world mixed/pothole/groove và model robot gốc vẫn giữ nguyên.

Để tiếp tục bài một cáp, cần một world giữ đúng vật cản đó trên nền collision
đã sửa, sau đó so PI full/moderate/pulse và kiểm tra trigger trước contact.
**Bài một cáp không được tự động chạy trong đối chứng này.** Predictor, PPO
và Optuna vẫn chưa chạy.

Với sàn có depression thật, không dùng hộp phẳng lấp vùng hõm. Cần thử một
representation có thể giữ hình học âm, ví dụ solid mesh kín với mặt dưới và
thành biên, rồi kiểm tra contact lại. Box control chưa chứng minh cách đó đã
hoạt động hoặc toàn bộ factory map đã được sửa.

## 6. Tái chạy

Profile mới: `src/nino_rl/config/factory_floor_clear_box_pi_check.yaml`.
Nó kế thừa PI profile hiện tại và chỉ thêm metadata của floor control.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=192
export NINO_ROS_DOMAIN_ID=192
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_clear_box_192

python src/nino_rl/scripts/run_clear_floor_repeat.py \
  --variant clear_box --seeds 76000 76001 76002 --profiles full \
  --output rl_runs/clear_box_recheck
```

Runner tạo output mới, từng cold start riêng và ghi thêm cửa sổ stop theo
simulation time. Để xem GUI mà không tự chạy robot:

```bash
ros2 launch nino_rl factory_floor_governor.launch.py \
  variant:=clear_box headless:=false caster_wheel_damping:=0.001 \
  config:=src/nino_rl/config/factory_floor_clear_box_pi_check.yaml \
  output_directory:=rl_runs/clear_box_view/contact
```

## 7. Dữ liệu và kiểm tra

- Raw box seed 76000: `rl_runs/governor_clear_box_AB_2026-10-15/`.
- Raw box seed 76001 và startup abort 76002:
  `rl_runs/governor_clear_box_AB_confirm_2026-10-15/`.
- Raw box seed 76002 hoàn tất:
  `rl_runs/governor_clear_box_AB_seed76002_retry_2026-10-15/`.
- Raw mesh: `rl_runs/governor_clear_repeat_2026-10-15_retry/`.
- JSON/CSV và audit nhỏ: `docs/governor_mesh_box_AB_2026-10-15/`.
- Generator candidate: `src/nino_description/scripts/create_clear_floor_box_control.py`.
- So sánh tái tạo được bằng `src/nino_rl/scripts/compare_clear_floor_collision.py`.
- **21 tests passed**, gồm kiểm tra một thay đổi vật lý, mặt trên/diện tích
  sàn, parent hash, PI/config parity, audit và startup logic. Build
  `nino_description`/`nino_rl` và `git diff --check` đạt.
- Các phiên Gazebo/evaluator của phép thử đã đóng.
