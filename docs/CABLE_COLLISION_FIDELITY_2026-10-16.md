# Đối chứng cylinder/capsule ở cáp đơn

## Lý do và protocol trước khi chạy

Trong batch oracle H2, contact bracket–cáp có một số điểm y≈±1.9989 m trong
khi robot gần y=0. Một số contact caster–cáp báo lực điểm hàng nghìn N nhưng
tổng lực có dấu nhỏ hơn nhiều. Các con số này là dấu hiệu cần audit,
**không phải lực tổng lên robot hoặc bằng chứng đã xác định lỗi solver**.
Contact trên mặt trụ cong có thể có các normal khác nhau; không dùng quy tắc
normal đối nhau của sàn phẳng để tự kết luận cylinder contact sai.

Theo Deep Research, cần kiểm tra fidelity liên quan quyết định trước predictor.
Đây là **một** đối chứng vật lý có căn cứ; không mở thêm sweep vô hạn.

- Parent: `factory_floor_cable_box_contact_lab.sdf`.
- Candidate: `factory_floor_cable_box_capsule_contact_lab.sdf`.
- Chỉ collision C1: cylinder → capsule, radius 0.011 m, phần trụ dài 4 m,
  pose/friction/visual giữ nguyên. Capsule có hai đầu tròn, tổng dài 4.022 m;
  tại vùng E1 robot vượt, tiết diện tròn giữ nguyên. Không gọi hai world là
  hình học hoàn toàn giống nhau tại đầu cáp.
- Full PI, seeds 76210–76212, một cold start/seed. Đối chiếu ba Full cylinder
  đã chạy trong H2. Không thay robot, caster, sàn box, PI, sensing, ramp,
  control/physics interval hoặc scoring. Không có oracle can thiệp ở Full.
- Ghi world/URDF/core hash, contact identity/positions/wrench, IMU và motor.
  Chỉ arrival thành công mà thiếu contact không được coi là vượt cáp hợp lệ.
- So vị trí contact với pose robot và envelope chẩn đoán rộng; header contact
  ROS không khai frame_id, nên việc diễn giải vị trí world phải ghi rõ giả thiết
  và kiểm tra với contact sàn gần robot. Không coi force điểm là net impulse.
- Đánh giá arrival, stop 2 s, tracking, approach, whole/post-contact metrics,
  độ biến thiên ba lượt. Candidate chỉ là diagnostic, chưa tự thay map chính.

## Điểm dừng

Nếu ba Full capsule đều đến đích/dừng, có contact cáp hợp lệ và không còn
điểm quá xa envelope, chỉ lặp **Moderate oracle** ba cold starts cùng seeds
76210–76212 trên candidate này. Giữ target 0.85, ramp và hold/release nguyên
như vòng trước. Đây là một vòng refinement sau correction vật lý, không thêm
profile hoặc tìm reward. Moderate được giữ vì Pulse có outlier rung lớn ở
vòng trước; đây là lựa chọn trên development data, không validation unseen.

Nếu contact không hợp lý vẫn còn hoặc kết quả không ổn định, giữ H2 chưa
đạt về lợi ích lặp lại, dừng predictor/PPO/Optuna. Nếu giảm được anomaly,
cần xác nhận tiếp bằng đo đạc/đối chiếu cơ khí trước tuyên bố sim-to-real.
Không thêm vật cản, terrain randomization hay học máy trong vòng này.

## Trạng thái

Protocol trên được ghi trước khi chạy. SDF capsule đã qua parser và invariant
test chỉ đổi primitive C1. Batch Full PI đã hoàn tất; refinement Moderate
oracle đang được ghi riêng, không trộn vào bảng đối chứng vật lý bên dưới.

## Kết quả Full PI — cùng seeds, robot và governor core

Tất cả sáu lượt có contact cáp, arrival vật lý và dừng ổn định 2 s. Hash URDF
và governor core giống nhau. Capsule metadata xác nhận đúng parent hash của
world cylinder; invariant test xác nhận chỉ C1 collision đổi primitive.

Post-contact window: first+0.05 s đến body x=3.40 m. Đơn vị RMS/peak m/s²,
slip²/m s/m. “Điểm xa” dùng diagnostic disk bán kính rộng 0.75 m quanh pose
robot, giả sử contact positions ở world. Floor contacts nằm trong khoảng
0.25 m trong khi cable points bất thường cách robot khoảng 2.01 m.

| Seed | Collision | Thời gian (s) | Post RMS | Post peak | Slip²/m | Điểm cáp ngoài disk |
|---|---|---:|---:|---:|---:|---:|
| 76210 | Cylinder | 16.9 | 9.016 | 94.175 | 0.28708 | 4 |
| 76210 | Capsule | 16.7 | 2.182 | 12.396 | 0.14993 | 0 |
| 76211 | Cylinder | 16.8 | 6.035 | 86.950 | 0.22350 | 10 |
| 76211 | Capsule | 16.7 | 1.858 | 10.753 | 0.13911 | 0 |
| 76212 | Cylinder | 16.9 | 2.289 | 13.702 | 0.29013 | 11 |
| 76212 | Capsule | 16.6 | 2.398 | 11.566 | 0.07401 | 0 |

Lực điểm lớn nhất được ghi trong ba lượt cylinder khoảng 20,647 / 7,071 /
201 N; capsule khoảng 112 / 136 / 141 N. Không gọi đây là net force hay
impulse. Đặc biệt cylinder 76210 có điểm caster–cáp 20,647 N nhưng tổng
signed z của manifold tại thời điểm ấy chỉ khoảng −33 N.

### Kết luận được phép

- Primitive collision ảnh hưởng rõ đến contact/impact trong điều kiện đã thử.
  Capsule không ghi nhận point ngoài disk ở ba Full runs và giảm biến thiên
  peak. Không kết luận đã xác định duy nhất nguyên nhân bên trong engine.
- Slip²/m giảm ở cả ba cặp; RMS không giảm ở mọi seed. Đây là thay đổi mô hình
  mô phỏng, **không phải thành tích governor/RL**.
- Candidate được giữ riêng để kiểm tra H2 một lần nữa, chưa thay mọi cáp trên
  mixed map, chưa sửa robot/caster và chưa chứng minh tương đương cáp thật.
- Arrival seed 76212 capsule có endpoint khoảng 0.198 m, gần ngưỡng 0.20 m;
  scoring được giữ nguyên, không làm tròn để thay đổi kết luận.

Gazebo vẫn có segfault khi shutdown sau khi evaluation hoàn tất; logger đã
đóng và stop window đã đủ. Đây là lỗi hạ tiến trình, không phải crossing failure.

## Artifact và chạy lại

- [So sánh/provenance/contact geometry](governor_cable_capsule_AB_2026-10-16/result.json).
- [CSV từng lượt](governor_cable_capsule_AB_2026-10-16/comparison.csv).
- Raw: `rl_runs/governor_cable_capsule_AB_2026-10-16/`.
- Generator: `src/nino_description/scripts/create_cable_capsule_control.py`.
- World/config candidate giữ `validated: false` cho phạm vi tổng quát.

Sau build/source trong ROS domain/partition riêng, output mới:

```bash
python src/nino_rl/scripts/run_clear_floor_repeat.py \
  --variant cable_box_capsule --profiles full --seeds 76210 76211 76212 \
  --output rl_runs/cable_capsule_AB_repeat_NEW
```

Định nghĩa length của capsule đã kiểm tra ở header Gazebo Math cài trên máy:
`gz/math7/gz/math/Capsule.hh`, phần length chỉ gồm đoạn trụ, hai nửa cầu nằm
ngoài đoạn đó. Vì vậy tổng chiều dài candidate là 4.022 m; chỉ vùng giữa
đường đi E1 có cùng hình học địa phương với cylinder.
