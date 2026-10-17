# Phân tích và quyết định H2 offline — 17/10/2026

## Trạng thái

**Quyết định của người dùng ngày 17/10/2026: giữ tiêu chí ở trạng thái đề xuất.**
Mức giảm slip²/m 10%, tăng thời gian tối đa 0,5 giây và quality phụ không
xấu đi chưa được chấp nhận hoặc áp dụng. Application requirements tiếp tục
để trống; chưa cấp ngân sách hoặc cho phép chạy batch 16 attempts.
Optuna, predictor và PPO tiếp tục chưa được mở. Quyết định này không thay
đổi protocol, hash đã khóa, metric hoặc kết quả kiểm tra offline.

**Đã triển khai bộ phân tích độc lập và kiểm tra bằng dữ liệu tổng hợp.**
**52 tests analyzer + 40 tests executor/protocol = 92 tests đạt.**
Không chạy simulation, không audit lại trace 77400/77401, không sửa native
metric/scoring, PI, detector, ramp hoặc vật lý. Chưa có kết quả H2 thực mới.

Code: `src/nino_rl/scripts/analyze_governor_h2_replication.py`.
Tests: `src/nino_rl/test/test_governor_h2_analysis.py`.

Executor giữ nguyên chế độ collection: sau 16 attempts, summary vẫn
`H2_decision:not_assessed`. Analyzer mới đọc output đó để ra quyết định,
không khởi động process hoặc tự mở Optuna/PPO/predictor.

## 1. Đúng tám cặp, không bỏ failures

- Xác minh 16 slot theo schedule đã khóa của
  [protocol H2](GOVERNOR_H2_REPLICATION_PROTOCOL_2026-10-17.md).
- Ghép theo **seed + repeat + profile + attempt**, không chỉ theo seed.
  Mỗi block 77500/77501 có bốn cặp; giữ cả thứ tự chronological và label.
- Duplicate/reorder/foreign seed hoặc native success mâu thuẫn termination
  gây kết luận chưa đủ bằng chứng, không âm thầm chọn bản ghi cuối.
- Native arrival/stop failure đã quan sát vẫn được đếm, kể cả khi crossing
  bị censor. Theo gate all-arrivals, failure đó làm batch không đạt; không
  cần giả lập slip/impact bằng 0 để ra quyết định.
- Missing/unattempted/native unknown giữ riêng, không thành physical failure.
  Báo denominator của từng metric và từng block. Một cặp thiếu một arm/value
  không được bỏ khỏi mean để tạo aggregate success-only.

## 2. Metric và khoảng bất định

Đọc namespace từ collector đã có, không tính lại hoặc chấm lại native score:

| Nhóm | Cách dùng |
|---|---|
| Postcontact | Slip²/m trên GT timestamp gốc, vertical sample RMS/peak, integral và distance; window first manifold +50 ms → +3 s |
| Toàn tuyến | GT slip RMS và native vertical RMS cho nonworsening; native slip RMS/peak vẫn báo riêng |
| Contact sequence | Slip²/m và vertical RMS của toàn chuỗi đã đóng, giữ kiểm tra hướng lợi ích |
| Crossing lịch sử | GT slip²/m và vertical RMS, báo riêng |
| Task | Route time và physical path RMSE, nguyên giá trị đã lưu |
| Sensitivity | Slip cùng window trên GT gốc, grid 20 ms và grid +10 ms; không chọn grid thuận lợi |

Với metric M càng nhỏ càng tốt:

`block benefit = 1 − mean(governor,4)/mean(PI,4)`.

Aggregate benefit là **trung bình bằng trọng số của hai block benefits**,
không thay bằng tỷ số của pooled means. Delta thời gian/metric là governor
trừ PI; mọi cặp đều có dòng báo cáo riêng.

Bootstrap: **10.000 draws, RNG 20261018**, resample bốn **cặp nguyên vẹn**
trong từng seed block; dùng cùng draws cho mọi metric, percentile interval
95%. Không bootstrap frame/contact point hoặc coi hai seed là quần thể
terrain. N=4/block không bảo đảm coverage danh nghĩa hoặc power cho mức 10%.

Nếu denominator PI bằng 0 hoặc một số bootstrap draws không xác định,
benefit/interval tương ứng để unavailable; không thêm epsilon hoặc bỏ
những draws đó. Delta tuyệt đối vẫn có thể được báo nếu dữ liệu đủ.

## 3. Kiểm tra can thiệp thực thi trước contact tiếp theo

Analyzer chỉ đọc trace của **batch mới được chọn**, từ chối case path ngoài
batch. Không glob các run cũ để bổ sung mẫu còn thiếu.

1. Dùng `governor_input_time_s` và header simulation time; không dùng receipt
   time hoặc action-end thay thời điểm quyết định.
2. Ghép lệnh governor với `command_received_sim_s` của driver bằng lookup
   quá khứ. Requested command phải khớp reference×scale; **executed command
   và average wheel target** phải thật sự giảm. Receipt stamp ở tương lai
   hoặc chỉ requested scale giảm không đủ bằng chứng.
3. Chọn timestamp publication đầu tiên có bằng chứng trên làm upper bound
   bảo thủ cho thời điểm thực thi quan sát được.
4. Contact tiếp theo phải có **manifold begin mới sau thời điểm đó**, đúng
   collision/component và có mẫu **depth>0, force norm>1e-6 N** trước end.
   Mẫu tải tiếp diễn của manifold đầu tiên không được gọi là contact mới.
5. Ghi body/joint snapshots bằng as-of lookup có age limit trước/tại lệnh
   và tại contact kế tiếp. Đủ dữ liệu response không đồng nghĩa đã nhận dạng
   actuator latency hoặc chứng minh lợi ích từ một body-speed dip.

Kiểm tra support trên cửa sổ contact −0.3→+3 s: control gap≤100.001 ms,
drive≤50.001 ms, GT≤40.001 ms, joint≤10.001 ms. Sensor duplicate stamps dùng
keep-last như protocol. Thiếu/gapped support → **chưa đủ bằng chứng**.

Contact/GT/caster là diagnostics phục vụ chấm điểm, không thành input
privileged cho governor. Force sample không được suy thành impulse.

## 4. Ba kết luận

### Đạt — `dat`

Cần đủ 16 attempts, all-arrivals/stop, integrity/provenance, approach và
timing opportunity đạt. Criteria phải confirmed và đã seal trước batch.

- Hai block primary point benefits và aggregate lower95% bound đạt minimum.
- Metric postcontact còn lại, whole-route GT slip RMS và vertical RMS không
  tăng theo point estimate ở mỗi block. Native slip vẫn được báo độc lập.
- Primary benefit trên complete contact sequence cùng hướng giảm.
- Mỗi block giữ mean time≤18.5 s,≤1.05×PI; physical RMSE≤1.05×PI.
- Upper95% added-time bound không vượt số giây đã chấp nhận.
- Khi chọn primary slip, không có sign reversal giữa GT/20 ms/+10 ms ở
  từng block hoặc aggregate.

Đạt chỉ cho phép **xem xét** ngân sách tuning governor cổ điển riêng, không
tự chạy tuning hoặc xác nhận generalization/sim-to-real.

### Không đạt — `khong_dat`

Bao gồm native arrival/stop failure đã biết, hoặc dữ liệu đủ/hợp lệ nhưng
vi phạm gate point-estimate, không có timing opportunity, upper95% primary
benefit còn thấp hơn minimum, hoặc lower95% added time đã vượt ngân sách.

Một gate point-estimate không đạt **không phải** tuyên bố tác hại có ý nghĩa
thống kê. Không đạt screen này không phủ định H2 với mọi controller.

### Chưa đủ bằng chứng — `chua_du_bang_chung`

Missing/censored data ngăn quyết định, batch incomplete, criteria/seal chưa
hợp lệ, approach không so sánh được, precontact intervention, integrity lỗi,
primary/time interval cắt ngưỡng, hoặc primary slip sign reversal theo grid.

**Không chọn grid đẹp hơn, tăng budget, sửa threshold hoặc bỏ failure.**
Không đạt/chưa đủ bằng chứng đều dừng nhánh screen/configuration hiện tại;
không tự tạo thêm pilot từ cùng dữ liệu.

## 5. Kết quả kiểm tra tổng hợp

**Bảng dưới là dữ liệu tổng hợp kiểm tra logic, không phải kết quả Nino.**
Ngưỡng 10%/0.5 s trong fixtures không xác nhận acceptance hoặc budget thật.

| Ca tổng hợp | Primary benefit/CI95 | Kết luận |
|---|---|---|
| Dữ liệu đầy đủ, lợi ích ổn định | 20%; CI [20%,20%] | Đạt |
| Lợi ích ổn định nhưng dưới mức tối thiểu | 5%; CI [5%,5%] | Không đạt |
| Point benefit tốt nhưng bất định lớn | 15%; CI [2.5%,31.25%] | Chưa đủ bằng chứng |
| GT primary tốt, shifted grid đảo chiều | GT 20%, CI tốt nhưng sign reversal | Chưa đủ bằng chứng |
| Thiếu một primary value | Aggregate unavailable, không success-only mean | Chưa đủ bằng chứng |
| Một timeout, quality censored | Failure vẫn đếm, không zero-impute | Không đạt arrival gate |

Tests còn kiểm tra: actual execution/target không giảm, manifold tiếp diễn,
zero-force contact, future receipt, thiếu sensor support, reader header-time
với duplicate, hai lựa chọn primary, secondary harm, sequence harm, tracking,
time budget/CI overlap, zero denominator, undefined bootstrap draws và đổi
label/thứ tự. Các test cấm subprocess thật.

CLI cũng đã chạy trên **offline plan**, không phải trace simulation:
0 attempted, 16 native unknown, kết luận chưa đủ bằng chứng đúng dự kiến.

## 6. Hash, criteria và điều kiện trước simulation

- `analysis_spec.json` khóa định nghĩa, bootstrap, mapping metric và code SHA.
- Future release của executor phải chứa analyzer mới trong
  `execution_dependency_sha256` **trước attempt đầu**. Analyzer đối chiếu
  application/protocol/analyzer hash với authorization snapshot của batch.
- Input ledger/criteria/protocol và các trace đọc được hash trước–sau;
  thay đổi trong khi đọc làm bằng chứng không hợp lệ. Native inputs chỉ đọc.
- **30 frozen files và 23 references của protocol cũ vẫn giữ nguyên.**
  Không sửa executor hoặc contract đã khóa để thêm analysis âm thầm.
- Bộ tiêu chí thực hiện tại vẫn là **đề xuất** cho đến khi người dùng chốt.
  Fixtures `confirmed/synthetic_only` không được dùng xác nhận batch thật.
- Chưa tạo approved release, chưa tiêu thụ budget, chưa chạy simulation.

Bước sau: chốt criteria nghiên cứu; seal hash; quyết định cấp tối đa **16
attempts** cho đúng protocol. Các lượt đầu thực hiện integration check ngay
trong 16 slot đó, không thêm smoke episodes. Integrity lỗi thì executor dừng
theo protocol; không bù lượt hoặc tự mở thêm ngân sách.

## 7. Artifacts và lệnh offline

- [Analysis spec](governor_h2_analysis_2026-10-17/analysis_spec.json).
- [Tests log](governor_h2_analysis_2026-10-17/tests.log).
- [Các ca tổng hợp](governor_h2_analysis_2026-10-17/synthetic_results.json).
- [Báo cáo tổng hợp ca đạt](governor_h2_analysis_2026-10-17/synthetic/pass/REPORT.md).
- [Báo cáo trên offline plan](governor_h2_analysis_2026-10-17/offline_plan_report/REPORT.md).
- [Verification](governor_h2_analysis_2026-10-17/verification.json).

Chạy lại nhóm tests liên quan:

```bash
cd ~/ninorobot
.venv/bin/python -m pytest -q \
  src/nino_rl/test/test_governor_h2_analysis.py \
  src/nino_rl/test/test_governor_h2_executor.py \
  src/nino_rl/test/test_governor_h2_protocol.py
```

Analyzer đọc batch mới sau này bằng `--protocol`, `--batch`, `--criteria`,
`--output`; output phải là thư mục mới. Không có chế độ launch/execute.
Chạy trên plan chưa có episodes sẽ trả về chưa đủ bằng chứng, không tạo dữ
liệu hoặc quyết định promotion giả.
