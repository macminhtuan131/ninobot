# Gate sau reset và bốn lượt PI repeatability — 17/10/2026

## Quyết định sau batch

**Đã tích hợp gate, kiểm tra lỗi và chạy đúng 4/4 attempts đã chốt.**
Tất cả đạt gate sau reset, physical arrival, dừng 2 simulation seconds,
native replay và reporting. Không retry, không thay episode, không có
governor candidate mới; các simulator của batch đã đóng.

**Chưa mở can thiệp mới hoặc chọn tham số.** Approach speed/pose đạt các
flag thô, nhưng PI chạy lặp cùng seed vẫn khác crossing RMS 2.74–3.36 lần
và GT crossing slip tới 23.7%. Gate đã xác nhận đứng yên sau reset, chưa
chứng minh contact outcomes đủ lặp lại cho một đợt chọn tham số nhỏ.

Delay 200 ms tiếp tục bị loại; default 0 ms. Không sửa thêm detector, PI,
ramp hay geometry. Không khẳng định một lỗi cơ khí/vật lý duy nhất từ các
chênh lệch này, không mở thêm vòng thử tham số hoặc tự tăng số lượt.

## 1. Tích hợp gate: thay đổi initialization, không thay controller/scoring

Config mới opt-in:

```yaml
reset_standstill_gate:
  enabled: true
  revision: post_reset_zero_standstill_v1
```

Không bật gate trong config cũ. Gate chỉ cho phép hợp đồng PI evaluation có
governor; không tự bật trong PPO hoặc deployment thật.

Vị trí: sau reset/teleport, reset drive, mọi mutation/layout, sensor refresh,
pause và epoch flush; **trước** episode clock và lệnh tiến đầu tiên.

- Giữ motion command v/ω bằng zero, residual torque zero; không đổi PI gain,
  acceleration/torque bounds hoặc gọi lại reset drive.
- Mỗi lần chỉ yêu cầu 20 ms physics; xác nhận clock thật và callback đã về.
  Không retry multi-step, không extrapolate hoặc advance thêm để chữa dữ liệu thiếu.
- Mọi ground/odom/joint/IMU/drive stamp phải **sau boundary reset mới**, không
  ở tương lai; motion age ≤40 ms, drive age ≤100 ms, có wheel state hợp lệ.
- Yêu cầu liên tục **0.5 s**: body và driven-wheel linear speed ≤0.01 m/s,
  yaw rate ≤0.03 rad/s; requested/executed v/ω bằng zero.
- Robot còn chuyển động thì quiet timer bắt đầu lại, **không reset robot lại**.
  Tối đa 250 bước ×20 ms = **5 s mô phỏng**. Thiếu/stale/invalid feedback
  gây lỗi riêng, không được dùng để cộng quiet time.
- Native episode clock bắt đầu sau release. Thời gian gate được lưu riêng,
  không nhập vào native time hoặc che dưới một rollout/action.
- Nếu gate lỗi, evaluation lưu `reset_standstill_001.json` và failure/summary;
  task outcome chưa quan sát phải giữ unavailable, không bịa arrival failure/success.

Code mới: `src/nino_rl/nino_rl/reset_standstill.py`; nối qua
`ros_interface.py`, `ros_env.py`; `evaluation.py` lưu report cả khi reset lỗi.
GT ở đây là **diagnostic initialization trong simulation**, không phải input
governor và không phải chứng minh gate này dùng nguyên dạng trên robot thật.

Nguồn trước sửa được giữ tại
`governor_post_reset_gate_2026-10-17/implementation_before/`.

## 2. Kiểm tra trước simulation

**37 focused tests đạt**, gồm:

- Pre-reset ground/joint stamp, future IMU hoặc stale drive không được nhận.
- Nonfinite/missing feedback, thiếu wheel state, command/executed command
  khác zero không được tính đứng yên.
- Quiet timer phải đủ 0.5 s liên tục; chuyển động giữa chừng bắt đầu lại timer.
- Fake lockstep đứng yên release sau 26 bước /0.52 s; luôn gửi zero.
- Fake robot còn chuyển động dừng lỗi sau đúng 250 bước /5 s; missing drive
  dừng ngay, không retry/reset; report lỗi vẫn serialize được.
- Các tests readiness cũ và governor core vẫn đạt.

Đây là nhóm tests liên quan, không tuyên bố toàn bộ repository test suite xanh.
[Log tests](governor_post_reset_gate_2026-10-17/tests.log).

## 3. Protocol chạy và bảo toàn contract

Theo [kế hoạch đã chuẩn bị](GOVERNOR_APPROACH_SEQUENCE_PLAN_2026-10-16.md):

1. Seed 77400, lần 1.
2. Seed 77401, lần 1.
3. Seed 77401, lần 2.
4. Seed 77400, lần 2.

Tất cả **PI full 0.4 m/s**, cold start riêng, tuần tự domain 107/partition
`nino_pi_standstill_107`. Không governor intervention hoặc parameter search.
Gờ capsule cứng 6 mm/radius 3 mm, x=3.10 m, góc +8°, floor box; world/hash
khớp protocol. Robot, PI, detector, ramp, physical scoring giữ nguyên.

Một seed chung chuẩn hóa scenario, không khôi phục nguyên trạng thái caster,
PI integrator và contact engine để tạo identical-state branches.

Runner: `src/nino_rl/scripts/run_governor_pi_repeatability.py`.
Raw: `rl_runs/governor_pi_repeatability_2026-10-17/attempt_01` đến `attempt_04`.
Prepared protocol và source/config/hash được snapshot **trước kết quả**.

## 4. Gate và reporting đã đạt gì?

| Kiểm tra | Kết quả |
|---|---|
| Gate sau reset | 4/4, mỗi lượt chờ 0.52 simulation s |
| Quiet window | 0.50 s liên tục/lượt |
| Observations của gate | 26/lượt, tổng 104 |
| Stamp sau reset, requested/executed zero | Đạt ở mọi gate sample |
| Physical arrival + dừng 2 s | 4/4 |
| Native slip replay / timestamp checks | 4/4 / 4/4 |
| Drive age trong action | 0–20 ms |
| Drive diagnostics/action | Ít nhất 4 |
| GT coverage whole route / crossing | 100% / 100% |
| Source/provenance trong batch | Giữ nguyên; cùng world/robot/PI/core/timing hash |
| Files bảo vệ | **1.265 file không đổi** |

Opt-in initialization code có revision mới; không gọi nó là source giống hệt
runtime lịch sử. Source snapshots, configs cũ và study scores vẫn được giữ.

Native time mỗi lượt là 16.60 s. Gate 0.52 s là setup bổ sung, báo riêng;
tổng từ boundary gate đến terminal khoảng 17.12 s, chưa tính toàn bộ startup
Gazebo/ROS trước boundary đó.

## 5. Số liệu PI-only: không chọn bỏ spike hoặc lượt xấu

| Seed | Lặp | Time (s) | Physical RMSE (mm) | Whole vertical RMS (m/s²) | Whole peak (m/s²) | Crossing RMS (m/s²) | GT crossing slip²·s/m |
|---|---:|---:|---:|---:|---:|---:|---:|
| 77400 | 1 | 16.60 | 3.088 | 3.349 | **80.973** | **6.246** | 0.018930 |
| 77401 | 1 | 16.60 | 6.830 | 1.227 | 9.844 | 2.069 | 0.019054 |
| 77401 | 2 | 16.60 | 3.567 | 2.570 | **67.103** | **6.954** | 0.023567 |
| 77400 | 2 | 16.60 | 3.861 | 1.425 | 13.638 | 2.281 | 0.017532 |

Crossing cũ vẫn first manifold +50 ms → body qua plane cách gờ 0.50 m.
Slip²·s/m là chỉ số bình phương tỷ lệ trượt tích phân/chia quãng đường,
không phải năng lượng cơ học J hoặc slip đã hiệu chuẩn thật.

| Cặp PI–PI cùng seed | Crossing RMS lớn/nhỏ | Whole peak lớn/nhỏ | GT crossing slip lớn/nhỏ |
|---|---:|---:|---:|
| 77400 | **2.738×** | 5.937× | 1.080× |
| 77401 | **3.361×** | 6.817× | **1.237×** |

Đây là observed ranges từ hai lượt/seed, **không phải variance estimate hoặc
confidence interval**. Không dùng chênh lệch single-run 10–15% làm bằng chứng
controller có ích khi ngay baseline cùng seed còn thay đổi như vậy.

Whole peak của 77401/lần1 xảy ra trước cáp; peaks lớn ở 77400/lần1 và
77401/lần2 lần lượt khoảng +62 ms và +717 ms sau first contact. Không gom
tất cả whole peaks thành cùng một loại impact. Crossing RMS vẫn chênh rõ,
nên vấn đề không được giải thích chỉ bằng việc whole peak nằm ngoài crossing.

## 6. Approach/caster và toàn chuỗi tiếp xúc

Cả 4 run và hai cặp cùng seed đạt các flag/caliper approach đã chuẩn bị:

- Median body speed khoảng 0.39739–0.39760 m/s.
- Chênh median speed trong cặp ≤0.000137 m/s.
- Chênh median lateral ≤0.555 mm; chênh wrapped yaw ≤0.181°.
- Không tipping/localization failure được ghi nhận trong bốn episode hoàn tất.

Caster floor-load classification theo sampled positive-depth/nonzero-force
rule vẫn thay đổi loaded/mixed giữa các run. Caster-right rolling median
khoảng 1.28–4.58 rad/s. Các con số là privileged diagnostics, không chứng
minh caster bị trượt hoặc xác định damping/geometry sai. Loaded fraction của
sample không đồng nghĩa tỷ lệ chịu tải vật lý chính xác liên tục.

Tool giữ mọi contact/recontact và đánh giá đến recovery, không dừng ở một
manifold đầu tiên. PI full có 0 governor events; không có sự khác biệt do
governor retrigger trong batch này.

- Contact-end sau first contact khoảng **1.982–2.050 s**.
- Concurrent recovery confirmation khoảng **2.282–2.350 s**; đây là xác nhận
  sau contact-end, không phải ước lượng actuator latency.
- Fixed 3 s GT-slip/IMU reports đủ coverage cả bốn run. RMS ở fixed window
  cũng chênh rõ; không dùng window mới để sửa score cũ.
- Negative control GT-slip 0→50 ms có support hợp lệ ở cả bốn run. Integral
  seed77400 là 0.004596/0.004332 s; seed77401 là 0.004502/0.006706 s.
  Các khác biệt có trước mọi governor intervention; không quy thành thành
  tích/lỗi của một candidate chưa chạy.

## 7. Chốt bước 5: không chọn can thiệp mới trong budget này

**Readiness đã được xác nhận trong bốn cold starts; chất lượng contact chưa
đủ lặp lại để mở một đợt chọn tham số nhỏ dựa trên một lượt mỗi trial.**
Không đòi mô phỏng hoàn toàn tất định, cũng không kết luận predictive control
bất khả thi. Nhưng hiện chưa tách được repeatability, sampling/contact phase
và trạng thái tiếp xúc thành hiệu ứng controller đủ đáng tin.

- Correction có căn cứ đã thực hiện là **gate initialization sau reset**.
  Nó không tự làm contact outcomes lặp lại.
- **Không chọn thêm correction robot/PI/detector/geometry** từ bốn lượt này:
  dữ liệu chưa xác định được một nguyên nhân duy nhất. Không tăng hold, đổi
  delay hoặc giảm obstacle để tạo một lượt đẹp hơn.
- **Candidate tiếp theo: chưa chọn. Ngân sách simulation can thiệp bổ sung
  trong công việc này: 0.** Dừng theo điểm dừng đã chốt, không tự tăng repeats.
- Chưa có căn cứ chốt smallest worthwhile effect cho nhà máy: cần yêu cầu
  rung/độ trượt hoặc production-time cụ thể, cùng thiết kế replication đủ
  phân biệt effect với biến thiên. Không bịa ngưỡng 10–15% hay power estimate
  từ n=2, không chọn metric P95 thay peak sau khi thấy kết quả thuận lợi.
- Nếu tiếp tục, dùng chính bốn trace frozen để kiểm tra cơ chế/contact phase
  hoặc measurement fidelity có khả năng thay đổi quyết định. Không mở rộng
  thành audit vô hạn; nếu không có nguyên nhân/căn cứ ứng dụng mới, giữ dừng
  nhánh can thiệp nhỏ hiện tại và chưa mở H1 predictor/PPO/Optuna.

## Artifacts

- [Quyết định cuối](governor_pi_repeatability_2026-10-17/final_decision.json).
- [Cặp PI–PI và mọi metric](governor_pi_repeatability_2026-10-17/PI_pairs.json).
- [Gate và reporting verification](governor_pi_repeatability_2026-10-17/verification.json).
- [Ledger/rows giữ đủ 4 lượt](governor_pi_repeatability_2026-10-17/episodes.json).
- [Hash 150 input files](governor_pi_repeatability_2026-10-17/input_sha256.json).

Không huấn luyện, không predictor, không Optuna, không sim-to-real claim.
