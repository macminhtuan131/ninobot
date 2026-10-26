# Cadence v6: mất mẫu joint và correction queue v7 — 23/10/2026

## 1. Quyết định hiện tại

**Dữ liệu Nino:** batch v6 dừng ở **1/12 attempts**, PI duy nhất. Arrival
16,600 s, stopping 2 s, lifecycle/closure, provenance và native replay đạt.
Crossing slip coverage **97,9777553%**, dưới contract 98%; 11 slot còn lại
đóng. Không có lượt governor 100/20 ms mới và không có performance comparison.
**H2 vẫn chưa xác định**, H1/H3 chưa được mở lại.

**Suy luận:** nút chặn trực tiếp lần này là acquisition thật sự mất mẫu ở
recorder riêng, không còn là lỗi thiếu field/file của analyzer. Điều đó
không làm bằng chứng về useful control authority mạnh hơn. Kết quả survey
18/10 vẫn là bằng chứng controller trung tâm; không cộng tiến bộ recorder
thành lợi ích governor.

**Correction đã kiểm tra phần mềm:** queue nhận joint/GT của recorder riêng
đổi 5 → 100, vẫn bounded KEEP_LAST / BEST_EFFORT. Không đổi shared sensor
QoS, primary/controller, physics, PI, detector, ramp hoặc scoring. Fixture
ROS tổng hợp có đối chứng và **156 software tests đạt**. Contract v7 đã
freeze, **chưa release ngân sách, chưa chạy Gazebo**. Không tiếp tục batch
v6, không lấy primary để vá measurement view.

**Đề xuất:** kết thúc vòng sửa hiện tại ở correction queue có bằng chứng
này. V7 chỉ đủ điều kiện review phần mềm, chưa đủ điều kiện kết luận coverage
trong Gazebo hay triển khai controller. Không tự tăng queue hoặc tạo batch
kế tiếp nếu gặp một failure khác. Hardware, PPO/BC, predictor và Optuna tiếp
tục giữ lại trong workflow hiện tại; việc chuẩn bị contract không phải cấp
ngân sách hay chấp nhận ngưỡng ứng dụng.

## 2. Batch v6 nguyên trạng

Contract `isolated_joint_gt_cadence_v6_2026_10_23`, protocol SHA256:
`567228933edaece4fd4e615986316d150f18be40754e320eb26d3709828be153`.

| Gate / outcome | Kết quả |
|---|---|
| Attempt / arm / seed / repeat | 1 / PI (`full`) / 77600 / 1 |
| Physical arrival / stopping | Đạt / đạt 2 s |
| Setup / provenance / physical state | Đạt |
| Hai recorder / reset-end ACK / closure | Đạt |
| Native replay | Khớp, 166 bước, RMS 0,028033615476425376 |
| Native timestamps / PI cadence | Đạt |
| Whole-route GT-header slip coverage | 99,6987952% |
| Crossing GT-header slip coverage | **97,9777553%, không đạt** |
| Quality availability / measurement integrity | Không đạt / không đạt |
| Simulation launches / retries / extra smoke | 1 / 0 / 0 |
| Slots 2–12 | Đóng, chưa thực hiện; không tái sử dụng |

Crossing window `[15,242; 17,220]` s dài 1,978 s, coverage hợp lệ 1,938 s.
Whole-route hoặc vertical coverage đạt không thay yêu cầu crossing slip.
Tích phân quan sát vẫn giữ trong artifact; các metric crossing cần đầy đủ
coverage vẫn `null`. Không làm tròn 97,9778% thành 98% để admit kết quả.

- [Release được lưu trước launch](governor_isolated_cadence_v6_run_2026-10-23/execution_release.json).
- [Ledger](../rl_runs/governor_isolated_cadence_v6_2026-10-23/ledger.json),
  [summary](../rl_runs/governor_isolated_cadence_v6_2026-10-23/summary.json),
  [attempt 1](../rl_runs/governor_isolated_cadence_v6_2026-10-23/attempt_01/result.json).
- [Analysis chính thức: không admit comparison](governor_isolated_cadence_v6_run_2026-10-23/analysis/report.json).
- [Validation nguồn tại thời điểm đóng v6](governor_isolated_cadence_v6_run_2026-10-23/closed_source_validation.json).

## 3. Chẩn đoán offline: đoạn thiếu ở đâu?

**Dữ liệu Nino**, từ [diagnosis JSON](governor_isolated_cadence_v6_run_2026-10-23/coverage_diagnosis.json)
và [script có hash](governor_isolated_cadence_v6_run_2026-10-23/coverage_diagnosis.py):

1. Recorder riêng có hai mẫu joint liên tiếp ở **17,170 và 17,192 s**:
   source gap **22 ms**. Mười mẫu 17,172…17,190 s đều có trong primary,
   nhưng không có trong raw CDR của recorder riêng.
2. Frame sequence 9441 → 9442 liên tục, CRC/SHA đạt. Đây là thứ tự các mẫu
   **đã nhận**, không phải sequence của publisher và không chứng minh đủ mẫu.
3. Receipt monotonic gap tại đó **57,993453 ms**; receipt sim clock tiến
   31 ms. GT ở crossing có max source gap 20 ms. Raw → view giữ nguyên tập
   timestamp joint/GT; bước decode/compose không làm mất mười mẫu này.
4. Tại GT 17,180 s, joint support `[17,170; 17,192]` vượt giới hạn nội suy
   10,001 ms. Hai đoạn tích phân `[17,160;17,180]` và `[17,180;17,200]`
   mất hiệu lực: tổng 40 ms, khớp đúng phần thiếu coverage.
5. Các drive diagnostic publication quanh gap vẫn báo wheel state có,
   raw update dt tối đa 2 ms, không dt >4 ms, joint age tối đa 2 ms.
   Đây là ngữ cảnh của consumer khác, không cứu dữ liệu recorder.

**Kết luận chắc:** mất mẫu xảy ra trước khi recorder ghi raw frames; đây
là đường nhận riêng của recorder, không phải một source-wide outage hoặc
lỗi tính slip ở đoạn này. **Chưa kết luận chắc:** vị trí drop chính xác,
hay CPU/OS scheduling, middleware/transport hoặc queue overflow là nguyên
nhân duy nhất. Callback ghi dài nhất trong manifest là khoảng 4,59 ms,
không tự giải thích toàn bộ receipt gap 58 ms.

**Suy luận có căn cứ:** queue depth 5 chỉ chứa được một phần số mẫu joint
500 Hz phát trong một khoảng consumer không được phục vụ. Pattern mất
mười mẫu phù hợp khả năng queue bị tràn. Cần kiểm tra cơ chế này bằng
nguồn phát biết trước; không sửa metric để thử giả thuyết.

## 4. Fixture ROS tổng hợp và phạm vi chứng minh

Không Gazebo, không publisher motor; domain 199, localhost. Dùng node
`IsolatedAcquisition` thật, publisher cố định depth 100, cố ý không service
recorder trong khi gửi 30 joint messages. Baseline/recovery có service;
tổng joint 50 mẫu. Hai cấu hình chỉ khác reader depth.

| Fixture qua QoS builder production | Depth 5 | Depth 100 |
|---|---:|---:|
| Joint source rate / tổng gửi | 500 Hz / 50 | 500 Hz / 50 |
| Joint nhận | **25/50** | **50/50** |
| GT source rate / nhận | 50 Hz / 5/5 | 50 Hz / 5/5 |
| Joint max source gap | 52 ms | 2 ms |
| GT max source gap | 20 ms | 20 ms |
| Khoảng không service, wall time đo được | 91,626 ms | 91,802 ms |
| Raw frame CRC/SHA | Đạt | Đạt |

[Script fixture](governor_isolated_cadence_v6_run_2026-10-23/queue_fault_fixture.py),
[kết quả](governor_isolated_cadence_v6_run_2026-10-23/queue_fault_fixture.json).
Một fixture trước correction, phát **cả hai topic ở 500 Hz**, cũng tái hiện
mất mẫu với depth 5. Giữ riêng [script cũ](governor_isolated_cadence_v6_run_2026-10-23/queue_fault_fixture_before_fix.py)
và [kết quả cũ](governor_isolated_cadence_v6_run_2026-10-23/queue_fault_fixture_before_fix.json);
không trộn hai stimulus thành nhiều lượt robot. Raw captures của cả hai
fixture được lưu kèm [archive và hashes](governor_isolated_cadence_v6_run_2026-10-23/queue_fixture_archive.json).

**Giới hạn:** một khoảng ngừng service do fixture áp đặt không tái tạo toàn
bộ tải Gazebo. Kết quả chứng minh queue capacity có thể gây và tránh loss
trong fixture này; chưa quy kết duy nhất nguyên nhân v6, chưa chứng minh
coverage v7 trong Gazebo và không bảo đảm delivery của BEST_EFFORT.

## 5. Correction duy nhất và contract v7

`capture_sensor_qos()` tạo profile mới cho mỗi recorder, depth 100; giữ các
policy sensor-data còn lại. Manifest lấy policy thực sự dùng. Shared
`qos_profile_sensor_data` vẫn depth 5; primary và governor không đổi. Test
kiểm tra hai profile độc lập và sửa một profile không ảnh hưởng shared QoS.

Depth 100 là buffer hữu hạn, tương ứng khoảng 200 ms source time ở 500 Hz,
không phải deadline/latency wall time được bảo đảm. Nó có thể giữ backlog;
header timestamps, epoch/readiness/closure và coverage vẫn phải bắt dữ liệu
trễ, thiếu hoặc sai scope. Chưa đo memory/latency dưới tải Gazebo/Pi thật.
Không tăng rate, đổi reliability, nới gap nội suy hoặc vá từ primary.

[Software verification](governor_isolated_cadence_v6_run_2026-10-23/software_verification_v7.json):
**156 passed**, 11,91 s, chín test files của acquisition/cadence/executor/
observer/native replay/slip/frozen inputs. Đây là software assertions,
không phải 156 crossing trials. Fixture ROS ở §4 kiểm tra buffer qua node
thật, bổ sung cho assertions, cũng không phải simulation attempt.

Contract: `isolated_joint_gt_cadence_v7_2026_10_23`.
SHA256: `571f72edfaf74710390b59db784805da1d1015425255b4dc5d415492bcc0a351`.
[Protocol](governor_isolated_cadence_contract_v7_2026-10-23/protocol.json),
[prepared manifest](governor_isolated_cadence_contract_v7_2026-10-23/prepared_manifest.json).
Physical/controller inputs và schedule giữ nguyên; receipt queue được khai
báo chung cho mọi arm. `budget_released=false`, `simulation_attempts=0`,
`live_integration_validated=false`, application thresholds vẫn proposal.

73 file của run v6 được giữ theo [hash tại batch close](governor_isolated_cadence_v6_run_2026-10-23/closed_run_sha256.json).
Correction v7 không hợp thức hóa batch v6 hoặc bất kỳ batch cũ nào.
[Kiểm tra cuối](governor_isolated_cadence_v6_run_2026-10-23/final_verification_v7.json)
xác nhận đủ 73 file không đổi, physical inputs/schedule/fixed v6–v7 giống
nhau, chỉ hai execution dependencies đổi (recorder và contract preparer),
hash script/result/raw fixture khớp và v7 validation đạt. `git diff --check`
đạt; không có simulation v7 trong lượt tiếp tục này.

## 6. Xếp lại ưu tiên và điểm dừng

| Ưu tiên | Đánh giá hiện tại | Quyết định |
|---|---|---|
| 1. Độ tin cậy phép đo cho screen đã chọn | V6 chỉ ra receipt loss cụ thể; fixture hỗ trợ một correction | Đóng correction ở queue 100 và freeze v7; không sửa logger vô hạn |
| 2. Useful control authority H2 | Vẫn chưa có actual wheel/body contrast hợp lệ mới | Không mở predictor/PPO/MPC để lấp khoảng trống này |
| 3. Objective ứng dụng / operating envelope | Chưa có trade-off nhà máy được chấp nhận | Giữ vector slip, vibration, time, tracking và failures riêng; chưa promote |
| 4. Sim-to-real | Thiếu response/backend/body reference thật | Không chuyển gain/latency sim xuống CyberGear; chưa cần mở hardware cho chẩn đoán receipt này |

Không đọc lại cùng trace để tạo thêm performance claim. Nếu sau này có
release riêng cho v7, PI và lượt 20 ms đầu vẫn nằm trong budget mới tối đa
12, không extra smoke/retry. Chỉ khi measurement hợp lệ mới xét command →
actual response trước contact kế tiếp → crossing trade-off. Command sớm
hoặc target đổi không đủ cho H2.

Nếu v7 vẫn không đạt phép đo, kết luận **measurement readiness chưa đạt**,
đóng batch và dừng series cadence với kiến trúc hiện tại. Khi đó cần quyết
định kiến trúc acquisition riêng (ví dụ đánh giá recorder chuẩn rosbag2/CDR
với cùng timestamps/QoS/coverage), hoặc chuyển sang operating-envelope/
navigation memory; chưa có bằng chứng ở đây để gọi phương án nào tốt hơn.
Không tiếp tục queue 200/1000, đổi executor hoặc giảm coverage một cách tự động.

**Một việc nên làm ngay:** review bản correction v7 và bằng chứng fault
fixture đã đóng gói để quyết định có đáng cấp một screen mới hay chuyển
trọng tâm. Tôi chỉ đổi khuyến nghị giữ H2 ở trạng thái unknown khi có
contrast wheel/body hợp lệ, xảy ra trước phase tiếp xúc còn lại và có
crossing outcome cùng chi phí thời gian/tracking; thêm software tests hoặc
arrival PI thành công không đáp ứng điều kiện đó.

## Nguồn và giới hạn

Đây là báo cáo continuation dựa trên artifacts/code Nino, không phải báo
cáo tổng quan 12–20 công trình bên ngoài trong prompt deep research.
Các số liệu trong báo cáo là dữ liệu Nino/fixture vừa nêu; suy luận và đề
xuất được gắn nhãn tại chỗ. Chưa thu dữ liệu robot thật hoặc kiểm chứng
operating envelope ngoài rigid capsule 6 mm/E1 đã chọn. Đọc kèm
[timing-envelope audit](GOVERNOR_H2_TIMING_ENVELOPE_2026-10-23.md) và
[envelope/kế hoạch](NINO_OPERATING_ENVELOPE_AND_NEXT_STEPS_2026-10-23.md).
