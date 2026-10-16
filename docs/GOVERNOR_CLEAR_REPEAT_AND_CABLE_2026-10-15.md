# E1 sàn sạch: ba lần khởi động mới và quyết định giữ bài một cáp

**Kết quả tiếp theo:** [đối chứng mesh/box đã hoàn thành](CLEAR_FLOOR_MESH_BOX_AB_2026-10-15.md).
Bản ghi dưới đây giữ nguyên dữ liệu và quyết định tại thời điểm audit mesh;
kết quả box không thay thế hoặc sửa lại các episode mesh cũ.

**Ngày:** 15/10/2026. **Trạng thái:** hoàn thành ba PI evaluation sàn sạch;
giữ phép so sánh governor một cáp sau audit contact. Không chạy PPO, predictor
hoặc Optuna. Không đổi controller, estimator, reward hoặc physical scoring.

## 1. Kết luận

Correction caster damping `0.001` đã lặp lại được **physical arrival và dừng
ổn định ở cả 3 seed**. Tuy nhiên, kết quả này chỉ xác nhận khả năng hoàn thành
chuyển động trong screen nhỏ. Nó **chưa xác nhận chất lượng contact/đo rung đủ
ổn định để so sánh governor**: có near-stop ngắn, peak IMU thay đổi lớn, và
manifold caster–mesh có lực điểm rất lớn theo các pháp tuyến ngược nhau.

Không dùng arrival 3/3 để bỏ qua các trace này; cũng không đổi kết quả arrival
thành thất bại. Quyết định giữ nghiên cứu chất lượng là đánh giá độ tin cậy của
thí nghiệm, không phải một tiêu chí physical success mới được thêm sau khi chạy.

## 2. Protocol đã chạy

- World `factory_floor_clear_contact_lab.sdf`; fixed E1, không cáp/pothole/mounds.
- Ba cold start riêng, seed **76000, 76001, 76002**. Map/dynamics không được
  randomize: ba seed không phải ba bản đồ hoặc ba profile vật lý khác nhau.
- Damping hai trục bánh caster `0.001 N·m·s/rad`, logger xác nhận URDF thực tế.
- PI toàn tốc, governor profile `full`, residual torque bằng 0. Giữ swivel,
  geometry, PI gains, torque limits và estimator như profile sửa trước.
- Physics step 1 ms, control interval 0.1 s. Không nới sensor/clock checks.
- Mỗi episode chỉ có một seed; sau arrival, tiếp tục ghi ít nhất 2 giây
  **simulation time** với lệnh dừng rồi mới đóng phiên mô phỏng.
- Stop diagnostic giữ ngưỡng đã khai báo: coverage hợp lệ, feedback bánh hợp
  lệ, command bằng 0, |roll/pitch| <5°, tốc độ cuối <0.01 m/s. Diagnostic này
  độc lập với arrival score, không phải tiêu chuẩn an toàn phần cứng.

Gazebo GUI cũ được đóng để tránh duplicate-world guard. Ba lần startup bị
guard chặn trước đó được giữ trong `rl_runs/governor_clear_repeat_2026-10-15/`;
không tính chúng là physical episodes/failures. Các lượt thực có dữ liệu nằm
trong `rl_runs/governor_clear_repeat_2026-10-15_retry/`.

## 3. Arrival, tracking và dừng

Số đo vị trí dưới đây lấy từ **ground truth độc lập**, không lấy cột endpoint
ước lượng được CLI in ra khi kết thúc.

| Seed | Physical arrival | Thời gian (s) | Sai số đích vật lý (m) | Physical RMSE (cm) | Max abs roll (°) | Max abs pitch (°) | Dừng 2 s |
|---|---|---:|---:|---:|---:|---:|---|
| 76000 | Có | 16.90 | 0.18645 | 0.865 | 0.349 | 3.173 | Đạt |
| 76001 | Có | 18.30 | 0.18477 | 1.959 | 0.845 | 2.803 | Đạt |
| 76002 | Có | 17.80 | 0.18494 | 0.687 | 0.359 | 2.674 | Đạt |

Không có rollover hoặc localization interruption trong ba evaluation.
Max clock error ≤4.09e-14 s; max motion sensor lag ≤0.011 s.

Mỗi stop window có 100 pose và 100 drive samples, coverage pose 1.98 s;
vận tốc cuối lần lượt 0.000724 / 0.000838 / 0.000759 m/s. Không ghi chassis
contact trong các cửa sổ này. Khoảng im lặng của contact plugin không tự
chứng minh lift-off hoặc hoàn toàn không có contact.

### Caster và motor

Tỷ lệ lăn danh nghĩa là `abs(omega_caster)*0.016 / v_body`. Chỉ xét chạy
thẳng với v>0.25 m/s, |yaw rate|<0.05 rad/s, swivel alignment<0.15 rad và GT
gần joint sample trong 0.05 s. Tập có lực contact dương dùng thêm điều kiện
|force_z|≥1 N trong 0.015 s. Đây là **bộ lọc diagnostic**, không là giới hạn
phần cứng hoặc một phép đo slip thực đã hiệu chuẩn.

| Seed | Caster trái, median có force | Caster phải, median có force | Sample motor gần dừng khi target>2 rad/s, trái/phải |
|---|---:|---:|---:|
| 76000 | 0.998 | 0.941 | 1 / 0 |
| 76001 | 0.998 | 0.988 | 2 / 3 |
| 76002 | 0.993 | 0.994 | 1 / 26 |

"Gần dừng" trong cột cuối là |actual|<10% target, diagnostic sample-level,
không đồng nghĩa cả robot bị stall. Seed 76001 có một đoạn gần đứng lại ở
x≈6.02 m rồi tự phục hồi; seed 76002 cũng có nhịp giảm vận tốc gần đích.
Không suy luận nguyên nhân duy nhất từ các mẫu này.

Nếu không lọc theo force, median caster phải lần lượt **0.281 / 0.577 /
0.654**. Không được gọi ngay đây là caster bị kẹt: tập đó có thời điểm không
ghi được lực đỡ đủ rõ, bánh có thể thiếu tải, và force/contact sampling có
giới hạn. Cũng không coi việc lọc force đã chứng minh mọi contact đều đúng.

## 4. Vấn đề contact/quality còn tồn tại

| Seed | Vertical RMS (m/s²) | Vertical peak (m/s²) | Wheel-slip RMS của dự án |
|---|---:|---:|---:|
| 76000 | 8.127 | 226.833 | 0.07763 |
| 76001 | 2.959 | 49.605 | 0.29071 |
| 76002 | 2.920 | 23.849 | 0.21688 |

Các peak IMU lớn nhất xuất hiện ở elapsed **16.694 / 17.050 / 16.933 s**,
gần đoạn tiếp cận đích, không phải chỉ là transient lúc reset. IMU Gazebo
đang publish 50 Hz, còn physics chạy 1 kHz; sampling/aliasing của xung contact
là một giả thuyết phải kiểm tra, chưa phải nguyên nhân đã được chứng minh.

### Không nhầm lực từng điểm contact với lực tổng lên robot

| Seed | Component tại cực đại | Thời điểm (s) | Max abs force_z một điểm (N, trường được ghi) | Tổng force_z có dấu cùng manifold sample (N) |
|---|---|---:|---:|---:|
| 76000 | Caster trái | 16.601 | 222626.9 | -35.0 |
| 76001 | Caster trái | 17.088 | 276101.4 | +31.1 |
| 76002 | Caster phải | 16.003 | 281522.0 | -5083.8 |

Ở seed 76000, ba force_z được ghi là khoảng **+50707, -222627, +171885 N**;
các normal_z tương ứng gần **+1, -1, +1**. Chúng gần triệt tiêu. Vì vậy:

- 223–282 nghìn N **không phải lực tổng đã xác nhận tác lên robot**.
- Tổng có dấu ở bảng cũng chỉ là tổng trường wrench của một reported
  manifold sample, không là whole-body force đo độc lập hoặc contact impulse.
- Có contact positions ở cả hai phía gần z=0, penetration khoảng 0.4–1.5 mm.
  Collision pair là caster wheel với `factory_contact_floor::terrain`, không
  phải cáp, tường hoặc goal marker. Goal marker không có collision.
- STL của clear floor gồm **2 tam giác phẳng**, winding đều hướng +Z và
  không có tam giác suy biến. Không tìm thấy bằng chứng mesh asset bị đảo
  winding trong phép kiểm tra này.

**Suy luận cần kiểm chứng:** contact trên mặt mesh không có độ dày có thể
tạo các constraint theo hai phía/normal trái dấu. Đây là giả thuyết cụ thể
về manifold/solver, chưa chứng minh DART/Bullet hoặc mesh là nguyên nhân duy
nhất của peak IMU và wheel tracking error. Không sửa reward hoặc tăng torque
dựa riêng trên peak force từng điểm.

## 5. Trạng thái bài một cáp — không có comparison hoàn tất

Sau khi ba motion checks đạt, đã khởi động PI full trong world một cáp,
seed **76200**, dự kiến so với `moderate` (0.85) và `pulse` (0.70 rồi phục hồi).
Khi audit contact đầy đủ phát hiện vấn đề trên, lượt full được dừng có chủ ý
**trước contact dương đầu tiên được ghi**:

- Trace cuối: 4.6 s, physical x≈1.64770 m.
- Không có completed episode, không có crossing outcome khả dụng.
- `summary.json` giữ `complete=false`, `success=null`, interruption được ghi
  là `KeyboardInterrupt`. Không tính nó thành physical arrival failure.
- `moderate` và `pulse` **chưa chạy**. Chưa có dữ liệu để kết luận slowdown có
  kịp trước next contact hoặc có cải thiện crossing quality.

Raw nằm trong `rl_runs/governor_single_cable_screen_2026-10-15/`;
`decision.json` ghi rõ lý do giữ screen, `contact_analysis.json` trả
unavailable thay vì gán crossing/impact thiếu bằng 0.

## 6. Một phép thử tiếp theo được đề xuất

**Đối chứng clear-floor collision mesh với mặt hộp phẳng có độ dày**, mặt trên
vẫn z=0, giữ robot/damping/PI/estimator/control interval/physics step/start/
goal và physical scoring. Bắt đầu bằng seed 76000; đây là candidate diagnostic,
**chưa được tạo hoặc chạy trong lượt này**. Không thay collision của map
pothole/mixed, không xóa depressions khỏi map nghiên cứu.

Đối chiếu manifold normals, wrench có dấu, GT motion, IMU và wheel feedback
ở cùng pha approach/stop. Nếu opposing constraints và các xung biến mất trên
mặt hộp thì có căn cứ sửa representation/collision. Nếu không, tập trung vào
đồng bộ sensor, cách force được export và đáp ứng PI; không tự tăng damping,
đổi reward hoặc chạy thêm policy.

Chỉ khi phép đo contact/quality có thể giải thích và lặp lại mới tiếp tục
ba profile một cáp. Không đặt ngưỡng % lợi ích mới sau khi xem kết quả này.

## 7. Công cụ, dữ liệu và kiểm tra

- `src/nino_rl/scripts/run_clear_floor_repeat.py`: chạy cold start riêng,
  kiểm tra URDF/controller sẵn sàng, đợi stop theo sim time và dọn đúng
  process group do script tạo. Có thêm mode cable và lưu plan/source snapshot
  cho các lượt sau; không resume hoặc ghi đè output cũ.
- `audit_clear_floor_stability.py`: thêm rolling có điều kiện contact,
  wheel response, thời điểm/normal/wrench có dấu tại force peak.
- `audit_single_cable_screen.py`: chuẩn bị phân tích contact→command→body
  slowdown, event-window acceleration/slip; chạy trên lượt bị dừng và trả
  unavailable đúng vì chưa có contact.
- **14 tests passed**: clear-floor audit, governor analysis và foundations.
  Python compile và `git diff --check` đạt. Không thay safety/timing checks.
- Các phiên mô phỏng/evaluator do lượt này quản lý đã đóng.

Kết quả nhỏ và JSON audit lưu tại `docs/governor_clear_repeat_2026-10-15/`.
Raw JSONL/CSV vẫn nằm trong `rl_runs/`; không chuyển các raw lớn vào Git.
