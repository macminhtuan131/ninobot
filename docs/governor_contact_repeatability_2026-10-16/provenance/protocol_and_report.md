# Repeatability — đo PI timing và caster support trước correction

**Hoàn tất 16/10/2026:** 3 lượt Full PI đo timing và 10 lượt đối chứng,
tổng **13/13 arrival và dừng ổn định 2 s**. Không chọn correction PI/reset
vì telemetry chưa chứng minh lỗi đó. Governor cho tín hiệu giảm rung sau
tiếp xúc lặp lại, nhưng tăng slip trung bình; giữ làm candidate nghiên cứu,
chưa promote, chưa chạy predictor/PPO/Optuna. Các simulator của batch đã đóng.

## Protocol trước simulation

Tiếp tục theo Deep Research: đo timing/actuator và contact fidelity trước
predictor, phân biệt natural caster variability với lỗi reset/scheduling.

Trace cũ có diagnostics 50 Hz dù wheel PI cấu hình 500 Hz. First-visible
command xuất hiện 2–18 ms sau control boundary, nhưng sampling 20 ms không
đủ chứng minh command thực sự trễ từng ấy. Chưa coi đây là nguyên nhân.

1. Thêm read-only telemetry tổng hợp **mọi** PI callback trong status window:
   raw dt min/max/sum, số callback dùng dt fallback, số interval >4 ms,
   joint-state age và timestamp nhận cmd_vel. Status vẫn 50 Hz.
2. Ba cold-start Full PI trên cùng capsule E1, seeds 76320–76322. Tất cả
   physics/geometry/controller gains/reset/governor/scoring giữ nguyên.
   Seed thay đổi không tự randomize geometry/dynamics đang tắt.
3. Audit initial/reset state, precontact caster rolling **và observed force
   support**, first impact, PI cadence/freshness. Missing contact stream
   không được suy ra caster mất tải; lực từng point không phải net force.
4. Chỉ chọn **một** correction nếu dữ liệu chứng minh lỗi cụ thể. Nếu timing
   không có vấn đề quan sát được, bác bỏ giả thuyết timing và không sửa PI
   theo phỏng đoán. Không ép unloaded caster quay theo ground speed.
5. Nếu có correction, dùng tối đa ba Full repeats và ba sensor-candidate
   repeats tiếp theo với cùng ngân sách/scoring để quyết định; không đổi
   reward/threshold/profile, không tiếp tục quét nếu kết quả vẫn không ổn định.

> >4 ms là diagnostic hai lần period PI danh nghĩa, không phải chuẩn an toàn.
> Không claim identical snapshot, sim-to-real hay H1/H3 từ screen này.

## Trạng thái

Ba telemetry runs đã hoàn tất, arrival/stop 3/3. PI khoảng 499.76–500.00 Hz,
không dt fallback/invalid/future joint sample. Một lượt có hai interval 6 ms;
hai lượt còn lại max 3 ms. Joint-state age thường 2 ms, max 3–4 ms. Đây chưa
là bằng chứng cần sửa PI hoặc reset theo phỏng đoán.

Caster support thay đổi: precontact median rolling ratio trái/phải khoảng
0.657/0.995, 1.000/0.428, 0.999/0.428. Có đầy đủ observed floor-wrench samples
ở cửa sổ này, gồm các khoảng lực báo cáo gần 0 và các khoảng ≥1 N. Không coi
mọi slow caster là slip; chưa xác định phần nào do cơ khí/thực tế hay numerical.

### Ba lượt đo timing ban đầu — Full PI, không đổi controller

| Seed | PI callbacks/s sim | Max raw dt (ms) | Fallback/invalid | Max tuổi joint (ms) | Post RMS (m/s²) | Post peak (m/s²) |
|---|---:|---:|---:|---:|---:|---:|
| 76320 | 499.76 | 6 | 0/0 | 4 | 2.960 | 19.058 |
| 76321 | 500.00 | 3 | 0/0 | 3 | 15.408 | 155.604 |
| 76322 | 500.00 | 3 | 0/0 | 3 | 2.188 | 9.453 |

Đo timing trên status window sau 0.1 s đầu episode; telemetry ghi nhận mỗi
PI callback rồi xuất tổng hợp theo diagnostics 50 Hz. Tất cả arrival/stop
3/3, không future joint timestamp. Không suy ra hardware latency từ đây.
Thời gian status nhận lệnh bắt đầu trùng control boundary trong ba lượt này;
first-visible status không phải thời điểm motor đã đáp ứng.

Ở seed 76321, mẫu IMU lớn nhất chiếm **98.06%** tích phân gia tốc bình phương
post-contact theo phép tính trapezoidal hiện hành. Khoảng mẫu đều 20 ms.
Đây là bằng chứng metric nhạy với một mẫu lớn, **chưa chứng minh aliasing**
hoặc contact giả. Giữ nguyên mẫu và scoring; không lấy contact force đã
downsample để tái dựng impulse hoặc suy ra nguyên nhân của spike.

Raw: `rl_runs/governor_pi_timing_probe_2026-10-16/`.
Audit: [PI timing, caster support và độ tập trung IMU](governor_pi_timing_probe_2026-10-16/result.json).

## Phần tiếp: randomized controller order, không correction controller

Vì chưa xác định lỗi timing, giữ toàn bộ PI/reset/physics/governor và chạy
một batch **5 blocks × 2 controllers = 10 episodes**, seeds 76400–76404.
Thứ tự Full/Moderate trong từng block lấy từ RNG seed **76450**, lưu nguyên
schedule trước chạy. Mỗi episode cold start. Geometry/dynamics giữ cố định;
đây là ngẫu nhiên hóa thứ tự/assignment, không phải physical randomization.

- Config `factory_floor_contact_repeatability.yaml`: same sensor governor,
  vertical-only trigger false, target Moderate 0.85, cùng hold/ramp/gates.
  Full không có adaptive event; dùng cùng source/telemetry cho hai nhánh.
- Mỗi block có cả hai controller nhưng **không cùng snapshot**. Không loại
  episodes theo caster speed/support, first impact hay quality.
- Báo từng native outcome, prefix trước action, callback timing, precontact
  observed support/rolling, post-contact và toàn tuyến.
- So chênh lệch theo block, effect direction và độ biến thiên. Có thể dùng
  exact sign-flip/randomization statistic trên 5 blocks; với N=5 không dùng
  p-value nhỏ giả hoặc coi frame là các lần lặp độc lập.
- Quality/arrival/scoring giữ nguyên. Nếu prefix/support distributions khác,
  giữ confound/uncertainty trong kết luận thay vì "sửa" bằng lọc data.
- **Dừng sau batch này**, không đổi thêm threshold/hold/reward. Chỉ cân nhắc
  dataset H1/tuning khi có lợi ích đáng tin so với repeatability và sensing
  thực thi được. Không yêu cầu thêm simulate vô hạn để cố tìm một winner.

## Kết quả batch ngẫu nhiên thứ tự — 10/10 đã hoàn tất

Một cáp cứng dạng capsule, bán kính 11 mm, tâm x=2.90 m; E1, nền hộp solid,
physics 1 ms. Tất cả nguồn PI/governor, URDF và world có cùng SHA trong batch.
Resolved config chỉ khác `governor.parameters.profile`: Full hoặc Moderate.
Không đổi gains, reset, robot geometry, damping, ramp, reward hay scoring.
Đây là cold-start repeat ở geometry/dynamics cố định, **không phải physical
randomization, identical-state replay hay test generalization**.

Cửa sổ post-contact giữ như trước: first recorded contact +0.05 s tới khi
body qua x=3.40 m. Tọa độ chỉ dùng evaluator, không đưa vào governor.
Slip²/m có đơn vị s/m, không phải năng lượng cơ học J; cần GT trong sim,
không phải phép đo slip tuyệt đối từ IMU/encoder trên robot thật.

| Chỉ số trung bình, mỗi nhóm 5 lượt | Full PI | Sensor governor | Chênh lệch governor |
|---|---:|---:|---:|
| Physical arrival / dừng ổn định 2 s | 5/5 / 5/5 | 5/5 / 5/5 | Không có failure/unavailable |
| Completion time (s) | 16.72 | 17.24 | +3.11% |
| Physical path RMSE (mm) | 4.594 | 4.547 | −1.03% |
| Post-contact vertical RMS (m/s²) | 4.014 | 1.712 | −57.35% |
| Post-contact sampled peak (m/s²) | 31.786 | 11.024 | −65.32% |
| Post-contact slip²/m (s/m) | 0.14270 | 0.15294 | **+7.18%** |
| Whole-route vertical RMS (m/s²) | 1.864 | 1.356 | −27.26% |
| Whole-route slip RMS | 0.08384 | 0.08517 | **+1.58%** |

Phần trăm là ratio của group means. Không gộp ba timing probes vào đối chứng.

### Hiệu ứng theo từng block

| Seed | Post RMS Full → governor | Post peak Full → governor | Slip²/m Full → governor | Time Full → governor (s) |
|---|---:|---:|---:|---:|
| 76400 | 2.230 → 1.969 | 16.162 → 12.378 | 0.08523 → 0.09175 | 16.6 → 16.9 |
| 76401 | 2.474 → 1.837 | 12.063 → 15.443 | 0.22593 → 0.32812 | 16.9 → 18.6 |
| 76402 | 3.451 → 1.327 | 21.749 → 6.190 | 0.06712 → 0.12683 | 16.6 → 16.9 |
| 76403 | 8.988 → 1.551 | 87.307 → 6.993 | 0.15249 → 0.07741 | 16.7 → 16.9 |
| 76404 | 2.925 → 1.874 | 21.650 → 14.118 | 0.18271 → 0.14060 | 16.8 → 16.9 |

- RMS giảm **5/5** cặp; peak giảm **4/5**; slip²/m giảm **2/5**.
- Không lấy mean slip +7.18% để che mức tăng **45.23%** ở 76401 hoặc
  **88.96%** ở 76402. Candidate không cải thiện đồng thời mọi tiêu chí.
- Exact sign-flip hai phía cho post RMS là 0.0625, dưới giả thiết exchangeability
  trong block; đây cũng là p nhỏ nhất có thể với 5 blocks. Chỉ exploratory,
  không điều chỉnh nhiều metric, không coi hàng nghìn frame là các lần lặp.
  **Không đặt một gate p<0.05 bất khả thi cho screen năm block này**, cũng
  không coi p-value hoặc mean lớn là bằng chứng sim-to-real.

![Các cặp Full PI và governor](governor_contact_repeatability_2026-10-16/paired_blocks.png)

## Timing, contact và giới hạn suy luận

### PI không phải correction được chọn

Trong 10 lượt: PI **499.88–500.00 callbacks/s sim**, raw dt lớn nhất 5 ms,
**0 fallback, 0 invalid dt, 0 future joint sample**. Max observed joint age
6 ms. Đây là dữ liệu đo, không phải chứng nhận mọi scheduling/actuator đều
hoàn hảo. Tuy nhiên, không có căn cứ từ batch để sửa gains, tăng timer rate
hoặc thêm settling tùy ý.

Audit đã xử lý JointState lặp timestamp: giữ measurement được ghi cuối cùng
tại mỗi timestamp cho thống kê caster; ghi riêng số duplicate, không nhân
chúng thành thêm lần lặp. Native scoring không thay đổi.

### Governor thực thi được nhưng body slowdown đầu tiên không do governor

- Cả 5 governor episodes có **1 event**, không precontact event, đều phục hồi
  về scale 1.0. Event sau first recorded contact khoảng **101–103 ms**.
- Motor target giảm ≥10% sau **314–331 ms**, trước first recorded driven-wheel
  contact trong cả 5 lượt. Recovery về scale 1.0 sau khoảng **1.903–2.801 s**.
- Body đã giảm ≥10% sau **14–27 ms**, **trước** governor action. Đó là phản
  ứng tiếp xúc thụ động; không được báo nó thành actuator response latency
  hoặc chứng minh governor đã phanh được ngay trong 14 ms.
- First recorded obstacle contact là **caster bracket** trong cả 10 lượt:
  9 lượt bên trái, riêng Full seed 76403 bên phải. Không mặc định caster
  rolling surface chạm trước. Cần đối chiếu fork
  clearance và thứ tự contact thật trước sim-to-real; chưa sửa mesh theo
  giả thuyết và chưa kết luận đây chắc chắn là lỗi collision.

### Prefix/contact state vẫn không đồng nhất

Approach speed median gần nhau: Full 0.39630 và governor 0.39600 m/s. Nhưng
first-50-ms peak Full nằm trong **4.01–8.76**, governor **4.06–60.27 m/s²**.
Spike 60.27 ở seed 76402 xảy ra trước governor action; giữ nguyên trong
whole-route score và negative control, không quy thành lỗi governor.

Precontact rolling ratio median trái/phải phần lớn gần **1.00/0.65**; riêng
76401 governor gần **0.656/0.828**, khác Full **0.998/0.655**. Quan sát force
support có coverage ở các cửa sổ này, nhưng tải thay đổi theo thời gian.
Caster joint/force là diagnostic đặc quyền, không phải đầu vào triển khai.
Không suy ra low rotation luôn là slip hoặc ép caster quay theo v/r.

Spatial audit không ghi nhận sampled cable point ngoài đĩa body bán kính
0.75 m trong cả 10 lượt. Điều này duy trì kết quả đối chứng capsule, **không
xác nhận toàn bộ contact dynamics đã đúng**. IMU vẫn 50 Hz; không tái dựng
impulse hoặc độ rộng xung dưới 20 ms từ stream đó.

## Quyết định sau ngân sách đã chốt

1. **Giữ candidate sensor governor và mọi dữ liệu.** Kết quả mới cung cấp tín
   hiệu lặp lại về giảm post-contact RMS; kết quả ba seed cũ vẫn được giữ,
   không thay thế hay chỉ chọn batch thuận lợi để tuyên bố thắng.
2. **Không sửa thêm PI/contact/reset hoặc reward trong vòng này.** Không có
   correction mới nào được dữ liệu timing chứng minh. Không force caster.
3. **Chưa promote sang predictor/PPO/Optuna hoặc robot thật.** H2 có bằng
   chứng cục bộ về cửa sổ command và quality trade-off; chưa có Pareto benefit
   đầy đủ, equal-time comparison, H1 hay generalization. Đây không phải bằng
   chứng rằng mọi governor/predictor đều vô ích.
4. **Bước phân biệt tiếp theo là đối chứng PI chạy đều gần cùng thời gian**,
   giữ governor hiện tại cố định, trước khi thêm thuật toán. Cần đo thời gian
   thực của baseline và báo nếu chưa khớp; không gọi speed estimate là đã
   time-matched. Profile 0.394 m/s cũ vẫn chỉ là candidate chưa chạy, không
   tự khẳng định phù hợp mean 17.24 s của batch này.
5. **Batch này dừng ở 13 episode tổng cộng**, không mở thêm simulation/tuning
   để đuổi theo một p-value hay chọn lại threshold sau khi xem kết quả. Nếu
   phép đối chứng tiếp theo không cho lợi ích ngoài đi chậm, ưu tiên governor
   cổ điển hoặc dừng predictive cho operating envelope này theo Deep Research.

Không cần PPO thắng để cho phép mọi tuning. Hiện việc chặn predictor/RL dựa
trên phép so sánh chưa tách được speed trade-off, biến thiên contact/sampling
và slip tail, không dựa đơn thuần vào việc “RL chưa thắng PI”.

## Artifact và tái lập phân tích, không chạy simulation

- [Kết quả crossing/native và từng episode](governor_contact_repeatability_2026-10-16/result.json).
- [PI timing, observed caster support, IMU sampling](governor_contact_repeatability_2026-10-16/pi_support.json).
- [Spatial audit contact](governor_contact_repeatability_2026-10-16/contact_geometry.json).
- [Phân tích block, protocol và statistic](governor_contact_repeatability_2026-10-16/block_analysis.json).
- [Timeline seed đầu tiên, chọn theo protocol](governor_contact_repeatability_2026-10-16/timing_first_repeat.png).
- Raw runs giữ nguyên: `rl_runs/governor_contact_repeatability_2026-10-16/`.
  Source/config/native outcomes và raw hashes lưu trong `provenance/`.

```bash
cd ~/ninorobot
source .venv/bin/activate
export PYTHONPATH=src/nino_control:src/nino_rl:$PYTHONPATH
python src/nino_rl/scripts/summarize_contact_oracle_h2.py \
  --screen rl_runs/governor_contact_repeatability_2026-10-16 \
  --output docs/governor_contact_repeatability_2026-10-16
python src/nino_rl/scripts/audit_pi_contact_repeatability.py \
  --screen rl_runs/governor_contact_repeatability_2026-10-16 \
  --output docs/governor_contact_repeatability_2026-10-16/pi_support.json
python src/nino_rl/scripts/audit_cable_contact_geometry.py \
  --screen rl_runs/governor_contact_repeatability_2026-10-16 \
  --output docs/governor_contact_repeatability_2026-10-16/contact_geometry.json
python src/nino_rl/scripts/summarize_contact_repeatability.py \
  --screen rl_runs/governor_contact_repeatability_2026-10-16 \
  --crossing docs/governor_contact_repeatability_2026-10-16/result.json \
  --timing docs/governor_contact_repeatability_2026-10-16/pi_support.json \
  --geometry docs/governor_contact_repeatability_2026-10-16/contact_geometry.json \
  --output docs/governor_contact_repeatability_2026-10-16/block_analysis.json
```

Software verification: build `nino_control`/`nino_rl` hoàn tất; 9 focused tests
pass cho telemetry, failure/missing preservation, randomized schedule và
small-sample statistics. Matplotlib Axes3D warning không chặn figure 2D.
Gazebo có shutdown crash sau khi thu xong dữ liệu ở một số lượt; native
evaluation/stop và logger hoàn tất vẫn được giữ, không gán crash đó thành
crossing failure. Không sửa timing checks để hoàn tất batch.
