# Corrected logger / cadence batch — 21/10/2026

## Kết luận

**Đã xác nhận logger sửa shutdown close đúng dưới Gazebo trong attempt 1.**
Tuy nhiên batch dừng ở **1/12 attempts** vì coverage slip trong cửa sổ crossing
chỉ **96,9024%**, dưới gate 98%. Không chạy governor 20 ms hoặc 100 ms;
slots 2–12 không chạy, không retry, replacement hoặc smoke ngoài budget.

Vì vậy **không có phép so sánh cadence mới** về command timing, actual wheel/
body response hoặc quality trade-off. Không lấy số liệu từ batch cũ ghép bù.
H2 chưa đánh giá; ngưỡng 10%/+0,5 giây vẫn là đề xuất. PPO, predictor và
Optuna tiếp tục giữ lại; không thử phần cứng.

## 1. Contract và nguồn đã khóa

Người dùng cấp ngân sách riêng trong yêu cầu 21/10: tối đa 12 attempts,
PI/20 ms đầu nằm trong budget để kiểm tra integration. Protocol SHA256:
`c9d8a3b28bf343e05e27a71accd000016e54dc6acaa8d9d4d7b9a5a4489bb07b`.

- [Protocol](governor_corrected_logger_cadence_2026-10-21/protocol.json) và
  [release](governor_corrected_logger_cadence_2026-10-21/execution_release.json)
  ghi trước launch; claim riêng, domain 132/partition riêng, cold start.
- Chỉ `governor_logger.py` và `observer_health.py` khác revision batch lỗi
  shutdown. Chúng khớp snapshot đã kiểm tra 49 tests và synthetic ROS.
- Input YAML, robot, world, PI, limits, approach setting, detector, ramp,
  holding, observation windows, scoring cadence và sampling byte-identical
  với contract trước. QoS/depth và coverage 98% giữ nguyên.
- Schedule giữ hai seed block 77600/77601, ba arm, hai repeats; đây là
  scenario đã xem, không phải generalization test. Hai lượt đầu dự kiến PI
  và fast, nhưng PI không qua quality reporting nên fast không được launch.
- Các batch trước vẫn đóng, không reset ledger hoặc tiếp tục slots cũ.

## 2. Attempt 1 — PI full, seed 77600/repeat 1

| Hạng mục | Kết quả |
|---|---|
| Physical arrival | Đạt |
| Dừng sau arrival 2 sim seconds | Đạt |
| Reset/setup | Đạt |
| Metadata closed / provenance | Đạt |
| Native replay và timestamps | Đạt |
| Observer health | Đủ 72.040 records; zero error/overflow; valid |
| Cadence | 166 score rows, 100 ms đúng; PI không có micro trace |
| Cleanup | Được collector xác nhận |
| Whole-route GT slip coverage | **99,6386%**, đạt |
| Crossing GT slip coverage | **96,9024%**, không đạt |
| Post-contact GT slip coverage | **97,9661%**, không đạt |
| Quality reporting của traversal | **Không đạt — hard stop** |

Native outcome vẫn success, time 16,60 s, physical RMSE 3,767 mm, native
slip RMS 0,0184116. Whole-route GT slip RMS 0,0316221 có đủ coverage nhưng
không thay thế metric crossing/post-contact bị thiếu. Đây không phải một
quality-valid baseline để tuyên bố governor thắng/thua.

IMU post-contact giữ tất cả sample/spike, peak **27,1302 m/s²** và RMS
2,74645 m/s². IMU coverage đủ không làm slip coverage trở thành hợp lệ.

## 3. Health trace giải thích được điều gì mới?

Trong crossing có một gap joint:

- Source joint cuối: **14,918 s**; source joint kế tiếp: **14,954 s** —
  **36 ms**, vượt max interpolation support 10,001 ms đã khóa.
- GT vẫn có sample mỗi 20 ms, nhưng slip tại **14,920 và 14,940 s** không
  có joint support hợp lệ. Không nội suy xuyên gap.
- Quadrature giữ nguyên: ba segment kề hai sample invalid không đủ support,
  tổng thời lượng coverage thiếu **60 ms**. Crossing 1,937 s chỉ còn 1,877 s
  coverage; post-contact 2,950 s chỉ còn 2,890 s. Cùng gap trong whole-route
  16,600 s vẫn đạt 98%; do đó chỉ kiểm tra coverage toàn tuyến là chưa đủ.
- GT-native, grid 20 ms và grid +10 ms đều không đạt cửa sổ cần thiết. Không
  chọn grid khác hoặc bỏ đoạn thiếu để làm thay đổi kết luận.

Ngay tại boundary này, health record **40644**, contact bánh phải:

| Giai đoạn callback | Thời gian wall đo được |
|---|---:|
| Toàn callback | **47,746 ms** |
| `message_to_ordereddict` conversion | **47,501 ms** |
| Sanitize | 0,079 ms |
| JSON encode | 0,104 ms |
| Raw write | 0,0066 ms |

Callback joint trước đó có source 14,918 s. Trong khi contact callback chưa
trả quyền xử lý, nguồn tiếp tục tiến; joint callback tiếp theo chỉ còn
source 14,954 s. Drive trace trong gap vẫn có publications ở 14,928 và
14,948 s, wheel-state valid và 10 PI updates mỗi interval. Không có bằng
chứng driver motor/PI dừng cùng observer.

**Khoanh vùng có bằng chứng:** consumer sensor chia sẻ executor/callback
group với contact conversion đồng bộ, và joint acquisition bị gap trong
khoảng đó. **Chưa phân biệt được:** conversion CPU, garbage collection hoặc
OS descheduling trong stage conversion. Stage duration bao gồm thời gian
không được schedule, không phải CPU time riêng của hàm. Không gọi disk
flush là nguyên nhân gap này hoặc khẳng định gap 3,32 s cũ cùng nguyên nhân.

Health vẫn ghi zero error: callback chậm không phải exception, và sidecar
đủ không tự chứng minh raw acquisition coverage đủ. Đây chính là lý do giữ
cả health/provenance lẫn coverage từng cửa sổ.

## 4. Phép so sánh được báo như thế nào?

Frozen analyzer giữ đủ 12 assigned slots: **1 arrival, zero physical task
failure, 11 chưa chạy**. Lỗi acquisition/reporting của attempt 1 được giữ
riêng; không gọi nó là failed arrival. Các aggregate contrast và CI thiếu
cặp bắt buộc đều unavailable. Không dùng mean riêng những lượt có dữ liệu,
không ghép bộ 20/10, không bỏ spike hoặc đổi cửa sổ.

| Câu hỏi | Trả lời từ batch này |
|---|---|
| Fast governor ra lệnh sớm hơn? | Unavailable — chưa launch fast |
| Actual body/wheel đổi sớm trước contact tiếp theo? | Unavailable cho so sánh controller |
| Slip/rung/tracking/time trade-off? | Unavailable cho so sánh controller |
| Shutdown correction hoạt động dưới Gazebo? | **Có, ở attempt PI đầu này** |
| Acquisition đủ cho crossing quality? | **Không** |

## 5. Quyết định và bước tiếp theo

Giữ batch dừng tại hard-stop. Không chạy 11 slot còn lại hoặc mở rescue
budget. Controller và scoring giữ nguyên.

Correction acquisition có căn cứ để **thiết kế và kiểm tra offline tiếp**:
tách đường thu joint/GT nhẹ khỏi synchronous contact-message conversion,
để callback contact chậm không chiếm quyền xử lý sensor cần cho slip. Giữ
source timestamps/raw values/rates; queue overflow và loss phải explicit.
Kiểm tra ordering, episode/reset boundaries và injected slow conversion
trước một contract simulation mới. Đây là **đề xuất chưa implement**, không
được gọi là acquisition đã sửa hoặc bằng chứng governor tốt hơn.

Không cần dữ liệu robot thật để khắc phục lỗi observer phần mềm này. Nhưng
simulation hiện vẫn chưa cho phép nâng cấp/tuning policy từ quality outcome.

## 6. Artifacts

- [Ledger](/home/tuanmac/ninorobot/rl_runs/governor_corrected_logger_cadence_2026-10-21/ledger.json).
- [Summary](/home/tuanmac/ninorobot/rl_runs/governor_corrected_logger_cadence_2026-10-21/summary.json).
- [Native outcome, checks và health](/home/tuanmac/ninorobot/rl_runs/governor_corrected_logger_cadence_2026-10-21/attempt_01/result.json).
- [Frozen analysis](governor_corrected_logger_cadence_2026-10-21/analysis/report.json).
- [Health costs](governor_corrected_logger_cadence_2026-10-21/health_analysis/report.json).
- [Gap evidence / execution review](governor_corrected_logger_cadence_2026-10-21/execution_review/report.json).
- [Input hashes](governor_corrected_logger_cadence_2026-10-21/execution_review/inputs_sha256.json).
- [Review script](governor_observer_health_tools_2026-10-20/review_corrected_batch.py).
