# Protocol H2 có lặp — PI và reactive governor đã khóa

**Ngày:** 17/10/2026. **Trạng thái: đã chuẩn bị; chưa cấp ngân sách, chưa chạy.**

**Cập nhật analysis:** [bộ phân tích và ba quyết định H2 đã kiểm tra offline](GOVERNOR_H2_OFFLINE_DECISION_2026-10-17.md).
92 tests liên quan đạt; chỉ dữ liệu tổng hợp/offline plan, không thêm episode.
Criteria/release thực chưa được tự xác nhận bởi các fixtures tổng hợp.

**Cập nhật executor:** [đã triển khai và kiểm tra offline, 40 tests đạt](GOVERNOR_H2_EXECUTOR_2026-10-17.md).
Không chạy simulation; bộ tiêu chí 10% slip/0.5 giây giữ riêng dưới dạng đề
xuất chưa áp dụng. Protocol JSON/schedule/hash không đổi; capability mới
ghi riêng trạng thái triển khai sau thời điểm chuẩn bị protocol.

Người dùng xác nhận **chưa có yêu cầu thực tế từ nhà máy; ưu tiên là tối ưu
hệ thống**. Do đó không tự gán mức cải thiện 10–15%, trọng số gộp rung/trượt
hoặc chi phí thời gian. Các giá trị ứng dụng còn trống phải được chốt trước
lượt chạy đầu tiên. Không coi việc chuẩn bị protocol là lệnh chạy batch.

## 1. Câu hỏi và phạm vi

**H2:** với cùng hình học và cách tiếp cận, reactive governor delay 0 có
thay đổi tốc độ đủ sớm để cải thiện kết quả sau tiếp xúc, đồng thời giữ
arrival/tracking và chi phí thời gian trong giới hạn đã chốt không?

Đối chứng: PI full 0.4 m/s và PI có reactive governor hiện tại. Không thêm
candidate, delay, predictor, PPO hoặc reward tuning. Không audit lại bốn
trace 77400/77401; không gộp chúng hoặc các trial cũ vào kết quả xác nhận.

Đây là screen H2 cục bộ trên **một hình học gờ cứng 6 mm**, không phải hai
địa hình mới. Nó chưa chứng minh lợi ích ngoài việc đi chậm, H3 so với
reactive đã tune, tổng quát hóa qua pothole/groove hoặc sim-to-real.

## 2. Thiết kế và thứ tự đã khóa

**2 block seed 77500/77501 × 2 controller × 4 lần lặp = tối đa 16 attempts.**
Mỗi attempt cold start riêng. Tám cặp được chạy liền nhau, không gọi là
same-snapshot branching. Mỗi seed có hai cặp PI trước và hai cặp governor
trước; trong mỗi round cũng cân bằng hai thứ tự. RNG thứ tự **20261017**.

| Round | Attempts | Seed | Lặp | Thứ tự |
|---|---|---:|---:|---|
| 1 | 1–2 | 77501 | 1 | PI → governor |
| 1 | 3–4 | 77500 | 1 | Governor → PI |
| 2 | 5–6 | 77501 | 2 | Governor → PI |
| 2 | 7–8 | 77500 | 2 | PI → governor |
| 3 | 9–10 | 77500 | 3 | PI → governor |
| 3 | 11–12 | 77501 | 3 | Governor → PI |
| 4 | 13–14 | 77500 | 4 | Governor → PI |
| 4 | 15–16 | 77501 | 4 | PI → governor |

Các seed mới là nhãn block của cùng world; không mặc định seed khôi phục
cùng caster/PI integrator/contact microstate. Không thay thứ tự sau khi thấy
kết quả, không chọn lượt đẹp, không retry hoặc thay attempt thất bại.

## 3. Contract giữ cố định

| Thành phần | Giá trị |
|---|---|
| Route/start/goal | E1, `(0,0,0)` → `(6.45,0,0)` |
| Sàn collision | Box 10×7×0.1 m, mặt trên z=0 |
| Vật cản | Capsule cứng, đường kính 6 mm, đoạn trụ 4 m, x=3.10 m, yaw +8° |
| Tốc độ cruise | 0.4 m/s cho cả hai arm |
| Physics/control/IMU | 1 ms / 100 ms / 20 ms |
| Wheel PI | Kp=0.30, Ki=0.10, `conditional_v1`, torque 4 N·m |
| Giới hạn drive | Acceleration 12 rad/s², effort rate 10 N·m/s |
| Reactive | Target scale 0.90; ramp 0.4/s; hold min/max 0.8/1.0 s; delay **0 s** |
| Detector | Body-rate/wheel-error hiện tại; vertical-only trigger tắt; mọi ngưỡng giữ nguyên |
| Robot/caster/estimator | Theo reference config, URDF và source hash; không sửa |
| Randomization/curriculum | Geometry, adaptive items, curriculum và domain randomization tắt |

Hai arm **chỉ khác** `governor.parameters.profile: full/reactive`.
Không chạy thêm một ROS speed governor bên cạnh governor inline của evaluator.
Ground truth/contact/caster chỉ phục vụ kiểm tra/đánh giá, không thành input
privileged mới của governor.

**Provenance:** config gốc và metadata có tag radius/mesh kế thừa, không mô
tả collision hiệu lực của screen này. Giữ nguyên file lịch sử; SDF snapshot
là nguồn hình học được khóa, được kiểm tra có capsule radius 0.003 m và sàn
box. Phải đối chiếu world/URDF thực sự spawn trước mỗi lượt; không lấy tag
metadata cũ làm bằng chứng đang chạy một loại cáp khác.

## 4. Reset, approach và tính hợp lệ

- Sau mutation/reset: zero command, đứng yên liên tục **0.5 s**, tối đa
  **5 simulation seconds**, feedback mới và đúng timestamp. Gate hiện có
  giữ nguyên; thời gian gate báo riêng ngoài native episode time.
- Dừng quan sát **2 simulation seconds sau arrival**. Không có dữ liệu
  dừng thì không tự cho đạt.
- Approach window −300→−50 ms: speed 0.39–0.41 m/s; |y|≤0.01 m;
  |yaw|≤2°; |roll/pitch|≤2°; coverage theo checks hiện có.
- Trong cặp: chênh median speed≤0.005 m/s, y≤0.005 m, yaw≤1°. Báo caster
  rolling/swivel/chịu tải, không ép caster ít tải phải quay như bánh có tải.
- Nếu approach không đạt hoặc governor đã giảm lệnh trước first contact,
  **giữ attempt**, ghi không đủ điều kiện kết luận clean postcontact H2;
  không lọc nó khỏi mẫu hoặc chạy bù.

## 5. Metric, sampling và kiểm tra quyền điều khiển

### Cửa sổ

1. **Postcontact chính:** first recorded obstacle manifold +50 ms → +3 s.
   Giống nhau cho hai arm. Nó không bảo đảm đã loại hết đuôi first impact.
2. **Toàn tuyến:** native boundaries hiện có, giữ nguyên score/replay.
3. **Crossing lịch sử:** +50 ms → clearance plane hiện có, báo riêng.
4. **Toàn chuỗi contact và phục hồi:** dùng quy tắc đóng mọi manifold,
   clearance/quiet tail và xác nhận phục hồi đồng thời đã có.

### Phép đo

- Rung: vertical RMS/peak từ **mẫu IMU header gốc**, không bỏ spike hoặc
  giảm mẫu xuống 10 Hz. Sample RMS mới nằm namespace riêng, không thay
  native RMS vốn có cách tích lũy khác.
- Slip: `gt_timestamp_series` và `integrate`, GT timestamp gốc; chỉ nội suy
  joint với gap≤10.001 ms, không extrapolate; giữ nguyên công thức ratio,
  clipping và denominator. Báo RMS, tích phân slip², quãng đường và slip²/m
  (đơn vị s/m, **không phải năng lượng J**). Coverage phải đạt quy tắc 98%.
- Báo sensitivity cùng windows bằng grid 20 ms và grid +10 ms đã có. Nếu
  chọn slip làm primary mà hướng kết luận đổi theo grid: **inconclusive**,
  không chọn grid thuận lợi để qua gate.
- Báo arrival, stall/timeout/failure, physical path RMSE, route time,
  stopping, toàn bộ contact/recontact và mọi data thiếu/censored.

### Timing H2

Ghi detector trigger → lệnh giảm tốc **cuối cùng đã thực thi** → wheel
targets/raw encoder/body response → những lần contact chịu tải tiếp theo.
Phân biệt độ trễ command với biến động vận tốc do chính contact. Body-speed
dip đơn lẻ không đủ chứng minh hiệu quả can thiệp.

Muốn qua screen phải có lệnh can thiệp thực thi trước ít nhất một contact
chịu tải tiếp theo trong **mỗi** episode reactive; đồng thời có dữ liệu phản
hồi bánh/thân để kiểm tra, không chỉ requested scale. Lợi ích outcome được
đánh giá qua đối chứng ngẫu nhiên có lặp, không qua một timeline đẹp.

First-50-ms negative control chỉ dùng khi **toàn bộ support GT/joint** nằm
trước lệnh giảm đầu tiên; nếu chạm can thiệp thì ghi contaminated/unavailable,
không gọi nó là negative control hợp lệ.

## 6. Phân tích đã định trước

- Đơn vị thống kê là **episode**. Có tám cặp nằm trong hai block seed cố
  định; frame/contact point không phải các mẫu độc lập.
- Với metric M càng nhỏ càng tốt, mỗi block dùng
  `benefit = 1 − mean(governor,4)/mean(PI,4)`. Aggregate là trung bình bằng
  trọng số của hai block. PI denominator bằng 0/không đủ dữ liệu → unavailable;
  không thêm epsilon để tạo improvement.
- Báo mọi chênh lệch theo cặp, kết quả từng block và aggregate; không đổi
  sang median hoặc chọn best repeat khi mean không thuận lợi.
- Bất định: paired bootstrap **10.000 lần**, seed **20261018**; resample bốn
  cặp nguyên vẹn trong từng block, percentile interval 95%. Không bootstrap
  frame. Với n=4/block, coverage không được bảo đảm; không suy ra quần thể
  địa hình hoặc tuyên bố screen đủ power cho một phần trăm cụ thể.
- Báo cả đánh đổi rung–slip–thời gian, không gộp thành scalar score khi chưa
  có trọng số ứng dụng. Bảng đánh đổi là mô tả, không tự thay primary/gate.

## 7. Điều kiện ứng dụng còn trống

Theo câu trả lời mới của người dùng, các trường sau **chưa được chốt**:

| Trường | Trạng thái |
|---|---|
| Primary: rung hay slip postcontact | Chưa chọn |
| Cải thiện tương đối tối thiểu đáng giá | Chưa có yêu cầu |
| Tăng route time tối đa (giây) | Chưa có yêu cầu |
| Nguồn ngưỡng | Chưa có yêu cầu nhà máy hoặc engineering assumption được chấp nhận |

Không diễn giải “ưu tiên tối ưu hệ thống” thành một bộ trọng số hoặc tỷ lệ
cụ thể. Có thể chốt engineering assumptions cho nghiên cứu khi chưa có yêu
cầu nhà máy, nhưng phải ghi đúng nguồn và chốt **trước kết quả**, không gọi
chúng là yêu cầu nhà máy hoặc tiêu chuẩn ngành.

Giữ các giới hạn sẵn có: mean time≤18.5 s và≤1.05×PI; mean physical RMSE
≤1.05×PI. Protocol áp dụng cho từng block. Giới hạn thêm giây từ ứng dụng
cũng phải đạt, không dùng nó để nới giới hạn cũ âm thầm.

Quality phụ mặc định của protocol: metric postcontact còn lại và rung/slip
toàn tuyến không tăng ở mỗi block. Nếu cần noninferiority margin, phải sửa
revision và khóa trước chạy; không đặt margin sau khi thấy kết quả.

## 8. Quyết định và điểm dừng

**Chỉ xét đạt khi đồng thời:**

1. Hoàn tất 16 attempts; mỗi arm 8/8 arrivals và stable stop, reporting,
   provenance/approach đạt; không thiếu dữ liệu cần cho quyết định.
2. Có cơ hội can thiệp thực thi trước contact tiếp theo theo mục 5.
3. Primary benefit của **cả hai block** đạt mức tối thiểu ứng dụng;
   cận dưới aggregate interval 95% cũng đạt cùng mức đó.
4. Quality phụ không xấu đi theo mục 7; primary benefit trên toàn chuỗi
   contact có cùng hướng; sensitivity không đảo kết luận primary slip.
5. Timing/tracking giữ giới hạn cũ; cận trên interval 95% của thời gian
   tăng thêm không vượt số giây ứng dụng chấp nhận.

Đạt → cân nhắc ngân sách Optuna governor cổ điển nhỏ, với development seeds
riêng; không tự mở tuning, predictor/PPO hoặc dùng lại bank này chọn tham số.

Không đạt/inconclusive → **dừng cấu hình can thiệp này và nhánh screen nhỏ**.
Không thêm lượt, thử delay khác, tăng penalty hoặc mở một vòng audit vô hạn.
Không đánh đồng “16 lượt chưa phân biệt được” với H2 sai cho mọi governor.

### Quy tắc failure

- Ledger giữ đủ 16 vị trí được phân công, attempted/unattempted tách biệt.
  Không zero-impute missing impact/slip hoặc tính điểm chọn mẫu success-only.
- Timeout/stall/miss arrival thông thường vẫn được giữ; có thể chạy các
  slot còn lại nếu setup/vật lý hợp lệ, nhưng batch không được promotion.
- Readiness/timestamp/provenance/measurement integrity lỗi, rollover hoặc
  trạng thái vật lý invalid → dừng batch, không retry/bù. Các slot còn lại
  ghi chưa chạy; batch incomplete không thể đạt.
- Không kiểm tra lợi ích rồi dừng sớm. Không tăng ngân sách nếu interval rộng.

## 9. Những gì đã chuẩn bị và điều kiện trước chạy

Artifacts tại [thư mục protocol](governor_h2_replication_protocol_2026-10-17/protocol.json):

- `protocol.json`, `prepared_manifest.json`: contract và hash bản chuẩn bị.
- `run_order.csv`: đúng 16 slot, ngẫu nhiên và cân bằng.
- `inputs/`: config gốc, hai config arm, world/metadata và URDF reference.
- `source_snapshot/`: source/controller/reporting snapshots; **30 frozen
  files và 23 workspace references** được kiểm tra hash.
- `application_requirements.json`: form còn trống; context người dùng ghi
  riêng, không tự biến thành threshold hoặc cấp ngân sách.
- `validation.json`, `tests.log`: validator và **6 tests đạt**. Tests dùng
  temporary directories; không chạy ROS/Gazebo.

**Bước còn lại trước khi cấp ngân sách:** chốt yêu cầu/engineering assumption;
seal hash form cuối; xem lại và cấp tối đa 16 attempts cho protocol cụ thể;
chuẩn bị executor có ledger/failure policy đúng protocol. **Executor lúc
chuẩn bị protocol chưa được implement; nay đã kiểm tra offline theo cập nhật
đầu báo cáo, chưa chạy live**. Runner PI-only bốn lượt cũ dừng sớm ở physical
failure, không được dùng nguyên dạng cho batch này.

Công cụ mới chỉ chuẩn bị/validate, **không có chế độ execute**. Lệnh kiểm tra
an toàn, không khởi động simulation:

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/prepare_governor_h2_protocol.py \
  --validate docs/governor_h2_replication_protocol_2026-10-17
```

`structure_valid: true` nghĩa cấu trúc/hash hợp lệ; **không đồng nghĩa**
`run_allowed`. Hiện `budget_released`, `execution_authorized`, `run_allowed`
đều **false**, kể cả nếu chỉ điền đủ form.
