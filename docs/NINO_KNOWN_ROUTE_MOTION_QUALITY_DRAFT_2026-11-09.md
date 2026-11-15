> **ĐÃ THAY HƯỚNG theo lựa chọn người dùng 09/11:** gờ không biết trước, vượt được và bám quỹ đạo. [Hướng hiện hành](NINO_UNKNOWN_STEP_TASK_DIRECTION_2026-11-09.md). Nội dung dưới giữ lịch sử đề xuất, chưa có lượt MQ nào được cấp.

# Hướng Sim tiếp: classical preview và chất lượng chuyển động tại IMU

Ngày 09/11/2026. **Đề xuất tạm thời, chưa release và chưa phải kết quả Sim.**
Tiếp [audit đã đóng](NINO_FIXED6MM_SAMPLING_AUDIT_2026-11-09.md).

## 1. Quyết định làm tiếp

**[Đ] Ưu tiên giảm rung trên tuyến có gờ cứng đã biết**, so classical giảm
tốc theo vị trí với classical chạy chậm đều có thời gian tương đương.
Đây là cách đặt câu hỏi mới theo nhu cầu vận chuyển, thay vì tiếp tục dùng
velocity tracking để suy ra giảm rung. Mục tiêu và trade-off chưa được
người dùng chấp nhận; không coi chúng là yêu cầu nhà máy hoặc mức an toàn.
Nếu người dùng chọn tracking hoặc slip, cần thay draft trước release.

**[N]** Common± sau tiếp xúc ở E2 có quyền tác động nhưng lợi ích tracking
chưa nhất quán; allocation vẫn đóng 6/6, sáu slot block1 chưa cấp. TD3 có
training lịch sử và v2 integration; chưa có bằng chứng vượt classical cho
câu hỏi mới. Không đổi verdict, reward, metric hoặc ledger cũ.

**[S]** Preview có thể tác động trước transient đầu mà governor sau chạm
không kịp tác động. Đó là giả thuyết cơ chế, chưa phải kết quả: giảm tốc
cũng có thể kéo dài rung hoặc làm traversal khó hơn. Đối chứng chậm đều
kiểm tra liệu lợi ích chỉ đến từ giảm tốc toàn tuyến. Chưa có claim mới
thuật toán, dây mềm, pothole/groove hoặc sim-to-real.

## 2. Câu hỏi và ba arm đề xuất

World: box phẳng, một cylinder cứng Ø6 mm tại x=0,65 m; không randomization.
Giữ Ki=0,10, Kp=0,3, gain=1, geometry, caster, yaw follower, limits và physics
1 ms như nền hiện có. **Không sửa gain/current hoặc train actor.**

| Arm | Reference dự kiến | Vai trò |
|---|---|---|
| B0 | Cruise 0,20 m/s | Classical danh nghĩa |
| P | 0,20→0,18 m/s từ progress 0,35 m; phục hồi từ 1,00 m | Classical preview theo tuyến đã biết |
| S | Khoảng 0,187713 m/s đều | Đối chứng chậm, khớp thời gian **tham chiếu** của P trên đoạn đo |

Đề xuất gia/giảm tốc reference 0,10 m/s², warmup 0,5 s, source stop 10 s,
task horizon 16 s. Các số này là tham số thử **Sim**, chưa là motion limits
đã chấp nhận cho robot thật. Shaping/actuator lag thực tế vẫn phải ghi.

Tính động học tham chiếu từ rest cho đoạn progress 0,20..1,30 m:

- B0: 5,50 s; P: 5,86 s; tăng khoảng 6,55%.
- S được giải **trước khi thu dữ liệu**: 1,10/5,86≈0,187713 m/s.
- P tới cuối đoạn lúc 8,36 s trong mô hình lệnh, trước source stop 10 s.

Đây không phải mô phỏng tiếp xúc hay dự đoán thân xe. **Body time-matching
chưa được xác minh.** Khi có dữ liệu, P/S lệch thời gian quá giới hạn thì
không được gọi là matched comparison, không sửa S sau khi xem quality.

Progress controller phải đến từ estimator nhân quả và map đã biết, dùng
cùng gốc tuyến +X ban đầu với world; không dùng GT pose/contact/caster làm
input. Thiếu source estimator hợp lệ → chưa sẵn sàng, không fallback GT.
Các actuator targets/limits được readback riêng, không suy từ reference.

## 3. Metric prospective: đo cái gì và giới hạn claim

**[Đ] Primary:** RMS gia tốc đứng tại **điểm IMU** trên cùng đoạn vật lý
progress 0,20..1,30 m. Với sensor/body axes đã đối chiếu và convention
specific-force +g khi đứng yên:

```text
a_z_at_IMU = f_z − g cos(roll) cos(pitch)
RMS = sqrt(integral(a_z_at_IMU² dt) / supported_duration)
```

**[T]** REP-145 quy định accel theo sensor frame, là specific force và chỉ
+g theo Z khi trục Z hướng lên ở trạng thái nghỉ. Không được coi mọi
`linear_acceleration.z` đã bỏ trọng lực.
[REP-145](https://reps.openrobotics.org/rep-0145/).

**[N/T]** Xacro hiện đặt IMU không quay so thân, rate 50 Hz; backend lưu
gyro/accel sáu phần tử và GT roll/pitch, chưa lưu full orientation/frame
trong packet raw này. API Gazebo mô tả accel trong local frame. Vì vậy
runtime mới phải đối chiếu **expanded URDF/frame và gravity của world**,
kiểm +g ở settling trước tính metric. Gravity trong draft giữ `null`,
không điền mặc định cho đủ schema.
[Gazebo IMU API](https://gazebosim.org/api/sensors/9/classgz_1_1sensors_1_1ImuSensor.html).
API tham khảo không xác nhận version/binary Nino đang chạy. Tra cứu 09/11/2026.

GT roll/pitch chỉ hỗ trợ **scoring trong Sim**, không vào controller. Metric
giữ hiệu ứng rotation/lever arm tại IMU; không chuyển thành gia tốc trọng
tâm, lực va chạm, contact impulse, hư hại hàng hoặc slip. 50 Hz hữu hạn
bandwidth; sampled peak không phải đỉnh lực vật lý. Không gắn chuẩn ISO
hoặc tuyên bố cảm biến đã anti-alias nếu chưa kiểm.

### Window, clock và support

- Gốc tuyến/frame cố định trước run; scoring dùng lần GT source đầu vượt
  mỗi biên không gian. Lưu hai mẫu bao quanh từng crossing, khoảng bất định
  thời gian/vị trí; không nội suy để tạo độ phân giải. Thiếu crossing,
  reversal/loop hoặc interval bất định che lấp time gate → UNKNOWN.
- Primary tích phân ZOH theo **hợp các source events IMU/attitude và thời
  điểm hết freshness**, cắt đúng biên cửa sổ. Không lặp một giá trị lỗi
  thành zero hoặc query tương lai; không sửa reader ambiguity hiện có.
- Đề xuất supported duration ≥98%, source age và gap ≤40 ms. Các test metric
  hiện kiểm tích phân/mask; chúng **chưa nghiệm thu extractor crossing,
  source-gap QC toàn run hoặc sensor convention Gazebo**.
- Sensitivity dùng cùng observable IMU trên grid causal 20 ms, dịch +10 ms
  và native100 ms với trọng số cắt đúng biên. Mỗi namespace riêng; khác dấu
  → UNKNOWN. Không lấy native velocity ISE cũ làm metric rung mới.
- Không đổi filter, trừ mean từng run, loại spike hoặc cửa sổ sau kết quả.
  Primary này là **contract mới cho dữ liệu tương lai**, không rescore E2
  thành một thành tích rung vừa được chứng minh.

Secondary: gyro roll/pitch RMS, sampled peak, command→target→wheel→body,
cross-track RMSE/max, crossing duration, task/continuous stop, saturation,
interventions và mọi failure. Reward không là bằng chứng lựa chọn controller.

## 4. Trade-off và điểm dừng đề xuất

Các ngưỡng dưới **chưa accepted**, chỉ là đề xuất để review trước release:

| Điều kiện | Đề xuất |
|---|---:|
| RMS P giảm so B0 và S | ≥10% trong từng block |
| Thời gian đoạn P tăng so B0 | ≤10% |
| Body crossing time P/S lệch | ≤2%, phải xét crossing uncertainty |
| Max cross-track | ≤0,04 m |
| Dừng liên tục sau task | ≥2 s |

**Go:** data hợp lệ, cả hai block cùng chiều, sensitivity không đổi dấu và
đạt constraints → chỉ đề cử classical preview cho xác nhận tiếp. Hai lặp
không đủ power hay bằng chứng tổng quát hóa; không gọi learned benefit.

**No-go:** P không hơn S hoặc vi phạm time/task/path → giữ classical đơn
giản hơn, không dùng TD3 để cứu một cơ chế chưa có lợi ích.

**Unknown:** coverage, crossing, estimator, time-match hoặc sensitivity
không đủ → đóng tại budget. Không tự tăng sample, đổi mục tiêu hoặc refill.
Tối đa một correction có nguyên nhân cho release tương lai; giữ consumed
slots/failure, không sửa rồi thử vô hạn. Chưa có correction cần áp vào E2.

## 5. Thiết kế nhỏ dự kiến, chưa cấp budget

Một thí nghiệm duy nhất, **6 fresh launches đề xuất** = 3 arm × 2 block.
Thứ tự block0 B0/P/S, block1 S/P/B0 cân bằng chiều thứ tự, chưa loại được
mọi confound. Cùng setup/initial pose/load; ghi caster state hoặc unknown,
không gọi fresh launch là exact-state branching.

160 task ticks/lượt, tổng tối đa 960; chưa phải budget tổng physics/wall/disk.
Runtime phải giới hạn settling, startup, disk và owned processes riêng.
Neutral đầu là integration trong 6 lượt; không thêm smoke/retry. Review
từng lượt trước lượt tiếp. Failure sau launch giữ trong ledger; lỗi readiness
trước launch không được ghi thành một crossing experiment đã chạy.

Estimand: P/B0 và P/S RMS ratio−1 trong từng block, rồi trung bình bằng
trọng số hai tỷ lệ; giữ absolute values, cả block và mọi failure. Mẫu đối
chứng bằng0 → UNKNOWN, không chia0 hay thay metric.

**0/6 được cấp; runner/adapter chưa được triển khai.** JSON draft không
thể mở Gazebo, optimizer, hardware hoặc kế thừa slot block1 của E2.

## 6. Dữ liệu cần và outline hiện thực hóa

| Giai đoạn | Việc cụ thể | Artifact/gate |
|---|---|---|
| 1 — Đã chuẩn bị | Draft mục tiêu, ba arm; giải S trước outcome; metric fixture gravity/source/mask/spike | JSON spec + analytic plan +9 tests fixture đạt; chưa outcome |
| 2 — Tiếp theo, offline | Extract spatial crossings với brackets; QC gap/clock/frame; adapter preview dùng estimated progress, mất freshness → inherited stop/latch | Synthetic/fault tests và identity riêng; không GT fallback |
| 3 — Chuẩn bị release | Chốt objective/trade-off, expanded model/world/gravity, source/install parity; owned runner/ledger/wall/disk; freeze S và toàn protocol | Concrete reviewable release; vẫn0slot cho tới khi release riêng |
| 4 — Sau release | B0 integration trong6lượt; thu/review từng arm, giữ failures | Raw/provenance/hash và report; go/no-go/unknown theo contract |
| 5 — Nếu đáng làm | Xác nhận classical với conditions độc lập; chỉ xét learner nếu có biến thiên cần thích nghi vượt fixed schedule | Validation/test/action-coverage protocol mới; không tự train từ kết quả6lượt |

Raw cần: IMU gyro/accel +source/receipt/frame, GT pose/attitude/speed chỉ
scoring, encoder từng bánh, targets/driver telemetry/limits, các tầng command
thật sự tồn tại, estimated progress và quyết định tick, owner/freshness,
contact component/source/receipt audit, model/world/config/commit, reset/caster
labels, integrity/hash và failure reason. Requested, projected, final ROS và
actuator target khác nhau; không tạo telemetry giả cho đủ schema.

Khi trở lại robot thật cần xác minh mounting/attitude/gravity, IMU bandwidth
và body/reference uncertainty tại payload quan tâm. Phần mềm Sim metric
không biến thành hardware measurement đã xác nhận. Phiên hardware chưa mở.

## 7. File và trạng thái bàn giao

- `src/nino_rl/config/known_route_motion_quality_draft_v1.json`: spec có hash,
  objective/decision accepted=false, release mọi authority=false/0.
- `motion_quality_draft.py`: validator + analytic reference planner, không ROS.
- `motion_quality_metrics.py`: tích phân source-event, gravity projection và
  masks; chỉ fixture offline, chưa spatial extractor hoặc Gazebo qualification.
- Studio SIM-R4: hướng mới, đối chứng/thông số/data/gates và 0/6; loader kiểm
  hash/provenance, không hiển thị prepared như runtime/benefit đã đạt.

Artifact:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/known_route_motion_quality_preparation_2026-11-09/`.
Không xóa raw/checkpoint, không sửa controller hoặc ledger lịch sử.

Kiểm tra bàn giao: **75/75 tests offline đạt**, build `nino_rl`/`nino_pi`
đạt, source và bản cài khớp hash; GUI đã kiểm hiển thị và không khởi chạy
job. 234 file của6slot E2,209 file trong5audit niêm phong,54 original được
bảo vệ và197 file E1 còn giữ đều khớp.66 file E1 thiếu khớp receipt dọn cũ,
không có xóa mới. Ledger E2 giữ nguyên byte; không phát hiện Sim đang chạy.

**Việc tiếp theo duy nhất:** kiểm offline extractor biên không gian và adapter
classical preview với estimated progress, trước khi xét release. Đổi hướng
nếu mục tiêu người dùng khác hoặc không thể đo observable/time constraint
đủ rõ; không cần mở lại audit E2 hay train thêm để trả lời điều đó.
