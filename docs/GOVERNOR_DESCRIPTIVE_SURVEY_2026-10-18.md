# Khảo sát mô tả governor có lặp — 18/10/2026

## Kết quả hoàn thành

**Đã chạy đúng 16/16 attempts: PI 8/8 và reactive 8/8 đến đích vật lý; cả
16 lượt đạt dừng ổn định 2 simulation seconds.** Không arrival/stall failure,
retry, replacement hoặc thêm smoke episode. Cả 16 lượt có setup, provenance,
native replay, measurement integrity và cleanup hợp lệ. Đủ 17 metric trên
mọi lượt; không có dữ liệu thiếu hoặc spike bị loại. Simulation đã đóng.

Approach: cả 16 lượt và tám cặp nằm trong caliper đã khóa. Đây không phải
khôi phục cùng trạng thái caster/contact. Không thấy đảo dấu slip benefit
giữa GT timestamp gốc, grid 20 ms và grid +10 ms trong từng block/aggregate.

### Số đo và khoảng bất định

Delta = governor − PI. Các trung bình và delta dưới đây dùng hai block bằng
trọng số, mỗi block bốn cặp. CI95 là bootstrap cặp đã chốt trước chạy; N nhỏ
không bảo đảm coverage/power. Không áp dụng ngưỡng 10%/+0,5 giây.

| Metric | PI full | Reactive | Delta | CI95 của delta |
|---|---:|---:|---:|---|
| Thời gian (s) | 16,600 | 16,725 | +0,125 | [+0,100; +0,150] |
| Physical path RMSE (mm) | 3,719 | 3,817 | +0,097 | [−0,460; +0,621] |
| Slip² tích phân/m sau contact (s/m) | 0,013140 | 0,013058 | −0,000083 | [−0,002425; +0,002183] |
| Vertical RMS sau contact (m/s²) | 3,978 | 3,113 | −0,865 | [−3,104; +1,565] |
| GT slip RMS toàn tuyến | 0,033976 | 0,033981 | +0,000005 | [−0,002966; +0,003239] |
| Vertical RMS toàn tuyến (m/s²) | 2,128 | 1,671 | −0,457 | [−1,255; +0,384] |

**Slip sau contact đổi chiều giữa hai block:** governor cao hơn PI khoảng
22,15% ở 77500, thấp hơn khoảng 20,12% ở 77501. Estimand relative benefit
đã khóa là trung bình bằng trọng số của *hai tỷ lệ block*, bằng **−1,01%**,
CI95 **[−24,21%; +15,68%]**. Nó không phải tỷ lệ của hai pooled means trong
bảng; không chọn công thức cho kết quả thuận lợi hơn.

Rung trung bình thấp hơn ở cả hai block, nhưng CI delta vẫn bao gồm cả tăng
và giảm. Postcontact peaks dao động khoảng 5,22–86,90 m/s² giữa các lượt;
tất cả được giữ. Số đo này chưa xác lập lợi ích chất lượng chuyển động lặp
lại chắc chắn của cấu hình governor hiện tại.

### Can thiệp và contact

- Cả tám lượt reactive không giảm scale trước first contact; cả tám có bằng
  chứng drive reference và wheel target giảm trước một manifold mới chịu tải.
- Publication đầu tiên có bằng chứng giảm nằm **82–98 ms sau first contact**.
  Đây là upper bound quan sát được ở drive publication, không phải latency
  motor hoặc thời điểm vận tốc thân bắt đầu đáp ứng được nhận dạng độc lập.
- Ở năm lượt, contact được kiểm tra tiếp theo là bánh chủ động trái, sau
  publication giảm **520–533 ms**. Ở ba lượt, nó là caster phải, chỉ sau
  **2–6 ms**; các snapshot có thể dùng chung một mẫu GT do chu kỳ 20 ms.
- Body speed đã giảm trước publication giảm do chuỗi tiếp xúc đang diễn ra.
  Không quy first-impact dip hoặc toàn bộ thay đổi vận tốc thân cho governor.
  Command/target giảm không tự chứng minh đã giảm severity của contact sau.

**Không đưa ra quyết định H2 đạt/không đạt, không mở tuning/predictor/PPO.**
Khảo sát dừng ở đúng ngân sách đã cấp. 77500/77501 hiện là dữ liệu đã xem;
không gọi chúng là unseen test bank hoặc đổi nhãn kết quả thành xác nhận
hồi tố sau khi chọn tiêu chí. Phần robot thật tiếp tục chờ.

### Artifacts

- [Báo cáo đủ metric, hai block, tám cặp và timing](governor_descriptive_survey_2026-10-18/analysis/REPORT.md).
- [Report JSON](governor_descriptive_survey_2026-10-18/analysis/report.json).
- [Timing summary](governor_descriptive_survey_2026-10-18/analysis/timing_summary.json).
- [Release đã khóa trước chạy](governor_descriptive_survey_2026-10-18/survey_release.json).
- [Supervisor log](governor_descriptive_survey_2026-10-18/supervisor.log).
- Dữ liệu native và ledger: `rl_runs/governor_descriptive_survey_2026-10-18/`.

## Quyết định trước kết quả

Người dùng đã chọn: **khảo sát mô tả tối đa 16 attempts, giữ ngưỡng ở mức
đề xuất, báo số đo và khoảng bất định, chưa kết luận H2 đạt/không đạt**.
Phần robot thật tiếp tục chờ. Không áp dụng 10%/+0,5 giây, không tự mở
Optuna, predictor, PPO hoặc thêm lượt chạy.

Đây là contract riêng kế thừa geometry/controller/cách đo từ protocol H2
17/10. Protocol, application và hash của H2 chính thức không bị sửa. Release
descriptive không hợp lệ với executor H2 chính thức.

## Thiết kế đã khóa

- Hai seed block 77500/77501 × PI full/reactive × bốn lần lặp = **16 slots,
  tám cặp**, cold start riêng, thứ tự cân bằng theo schedule đã chuẩn bị.
- Fixed E1, gờ capsule cứng đường kính 6 mm tại x=3,10 m/góc +8°, sàn box.
- Cruise 0,4 m/s; cùng robot, caster, wheel PI, estimator, physics 1 ms,
  control 100 ms, IMU 20 ms, detector và ramp hiện tại.
- Reactive target 0,90, hold 0,8–1,0 s, ramp 0,4/s, **delay 0**.
- Gate sau reset: lệnh zero, yên liên tục 0,5 s, tối đa 5 simulation seconds;
  kiểm tra dừng 2 simulation seconds sau arrival.
- Các lượt đầu cũng kiểm tra integration **trong 16 slots**, không có smoke
  episode riêng. Không retry, replacement, resume hoặc tự tăng ngân sách.
- Lỗi setup/provenance/timestamp/reporting/cleanup hoặc physical fault dừng
  batch. Failure nhiệm vụ thông thường vẫn được giữ; không loại khỏi mẫu.

## Đo và báo cáo

Mười bảy metric của analyzer đã kiểm tra được báo song song, không chọn
primary sau kết quả: postcontact/whole-route/crossing/whole-sequence rung và
slip, peaks, thời gian và physical tracking. Giữ metric native và mọi spike.
Window postcontact: first manifold +50 ms → +3 s. GT timestamp gốc và joint
interpolation giữ nguyên; grid 20 ms và +10 ms là sensitivity, không chọn
grid thuận lợi.

Báo tám cặp, từng block và aggregate trung bình bằng trọng số hai block.
Bootstrap 10.000 draws, RNG 20261018, resample cặp nguyên vẹn trong mỗi block,
percentile 95%. Bốn cặp/block không bảo đảm coverage/power; thiếu dữ liệu thì
metric/interval unavailable, không zero-fill hoặc dùng success-only mean.

Đối chiếu approach, timestamp lệnh/drive, wheel targets, body/encoder và
manifold mới chịu tải để mô tả cơ hội can thiệp. Chỉ thay đổi command không
đủ kết luận vận tốc thân đã đáp ứng hoặc tác động được giảm do governor.

Kết quả không tuyên bố H2 formal đạt/không đạt, không chứng minh lợi ích
ngoài việc đi chậm, H3, generalization hoặc sim-to-real. Nếu muốn xác nhận
theo ngưỡng ứng dụng sau này, cần chốt protocol/budget trước dữ liệu xác nhận
mới; không đổi nhãn khảo sát này hồi tố.

## Triển khai và kiểm tra trước simulation

- Runner/report: `src/nino_rl/scripts/run_governor_descriptive_survey.py`.
- **10 tests offline đạt**, gồm giữ parent/application, loại release này
  khỏi executor H2 formal, đúng 16 fake slots, giữ failure/missing, hard stop,
  không reuse ngân sách và sensitivity đảo dấu. Không có simulator trong tests.
- ROS/evaluation imports đã kiểm tra; chưa thêm episode để kiểm tra startup.
- Bundle: `docs/governor_descriptive_survey_2026-10-18/`.
- Run: `rl_runs/governor_descriptive_survey_2026-10-18/`.
- Budget claim dùng hash release tại `rl_runs/.governor_descriptive_budget_claims/`;
  cùng release không được chạy lại qua bundle/output copy.

Các file `survey_spec.json`, `survey_release.json`, `user_authorization.json`
và source/dependency hashes được khóa trước attempt đầu. Ledger được ghi bền
vững trước từng launch. Báo cáo collection không tự chuyển thành quyết định
đạt/không đạt hoặc mở tuning.
