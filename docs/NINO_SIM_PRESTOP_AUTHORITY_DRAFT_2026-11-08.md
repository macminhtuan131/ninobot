# Draft Sim — quyền tác động của common correction trước lệnh dừng

Ngày 08/11/2026. **Chỉ chuẩn bị offline. Không chạy batch.**

Protocol: `nino_prestop_tail_authority_draft_v1_2026_11_08`.
Config: `src/nino_rl/config/prestop_tail_authority_draft_v1.json`.
Helper: `nino_rl/prestop_authority_draft.py` chỉ lập lịch và preview reference
bằng đại số; không có runner, ROS publisher, model load hoặc optimizer.

## 1. Quyết định hiện tại và câu hỏi mới

**[N]** Một learner seed11 đã train 30.000 bước; classical scheduled có
velocity RMSE tốt hơn TD3 trong clear-box/planned-stop 6/8 s/Ki0,10. Giữ
quyết định đó; không mở lại training 20k→30k, không chọn checkpoint25k làm
winner từ shadow. [Review đã đóng](NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md).

**[N]** Khoảng 86–87% SSE toàn tuyến của TD3 30k nằm ngoài cửa sổ residual
đã mở; có phần ramp-up trước can thiệp và ramp-down sau withdrawal. Đây là
vị trí lỗi trên trajectory cũ, không là trần benefit hoặc chứng minh quyền
tác động mới. Reward/critic chưa đủ để quyết định controller.

**[S]** Rút residual sớm 0,5 s có thể thay trạng thái wheel/body tại lúc
bắt đầu hạ source. Một thay đổi common nhỏ ở đoạn này có thể ảnh hưởng
tracking khi giảm tốc; cũng có thể làm dừng xấu hơn. Chưa biết dấu nào có
lợi và liệu khác biệt có vượt biến thiên giữa fresh launches.

**Câu hỏi duy nhất:** thay common correction trong 0,5 s cuối trước source
stop có thay đổi wheel/body và cải thiện tracking của đoạn tail–stop với
cùng ràng buộc task/stop không?

Đây là probe cổ điển về control authority, chưa là thí nghiệm TD3, predictor
hoặc contact governor. Không cần Pi hoặc data thật để chuẩn bị/chạy screen
Sim này theo một release riêng. Kết quả không xác nhận sim-to-real.

## 2. Biến thay đổi và đối chứng

Tất cả arm giữ nguyên lịch common cổ điển trước `stop−0,5 s`. Trong tail
`[stop−0,5; stop)` thay đúng một yếu tố: **requested common scalar**.

| Arm | Tail scalar | Common request trong tail | Vai trò |
|---|---:|---:|---|
| Tail0 | 0 | 0 m/s | Classical scheduled lịch sử, đối chứng parity |
| Tail+ | +1 | +0,005 m/s | Kiểm dấu tăng reference |
| Tail− | −1 | −0,005 m/s | Kiểm dấu giảm reference |

Chỉ mở tail khi source còn tiến, nominal đã steady và history/source/
permission/health hợp lệ. Differential=0. Không đưa GT, contact hoặc caster
vào scheduler. Planned source stop được cấp giống nhau cho cả ba arm.

Từ source stop trở đi, requested residual bằng0 và giữ zero-source priority
của projector cũ. **Không mở residual trong braking sau source-zero.**
Reference/body có thể còn khác do trạng thái trước stop và slew; không ép
các trajectory sau stop giống nhau hoặc gọi tất cả reference còn dương là
lệnh residual mới. Đây chính là carry-over cần đo.

Giữ frozen Ki0,10, estimator/follower, shaping/limits, history5/10Hz,
gain=1, geometry/world, reward và source cruise **0,2 m/s của Sim**. Không
copy profile này sang robot thật. Scenario là **clear_box fixture**, chưa
phải toàn factory mixed map và không có vật cản trong câu hỏi này.

## 3. Đơn vị thử, thứ tự và ngân sách đề xuất

**Hai block × hai source stops 6/8 s × ba arm = tối đa12 attempts.**
Mỗi attempt là một fresh launch 14 s /140 task decisions; tổng1.680 task
ticks /168 task simulation seconds, chưa gồm reset/settling. Không optimizer,
không checkpoint training và không replay buffer mới.

| Thứ tự | Block | Stop | Tail scalar |
|---|---:|---:|---|
| P01–P03 | 0 | 6 s | 0, +1, −1 |
| P04–P06 | 0 | 8 s | −1, 0, +1 |
| P07–P09 | 1 | 8 s | +1, 0, −1 |
| P10–P12 | 1 | 6 s | −1, +1, 0 |

Requested environment seeds 88110/88111 là nhãn block đề xuất, không phải
training seeds hay bằng chứng Gazebo đã restore cùng trạng thái/RNG. Thứ
tự được cân bằng một phần để giảm confound thứ tự, không giả vờ hoàn toàn
randomized. Hai block là pilot mô tả, không đủ power/generalization.

P01 là integration check trong chính12 slots, không thêm smoke trước nó.
Nếu P01 lỗi readiness/measurement thì đóng batch, giữ slot và các attempt
chưa chạy ở trạng thái closed/unrun; không retry hoặc thay thế slot. Mọi
failure/unknown giữ trong mẫu báo cáo. Không lấy pilot cũ làm repeats mới.

**Đang cấp: 0 attempts.** Con số12 là proposal. Runtime adapter/runner mới
chưa được xây trong draft này. Cần review ngưỡng và release riêng sau khi
có parity/measurement/readiness/storage checks; không sửa JSON để bypass.

## 4. Dữ liệu bắt buộc và chuỗi kiểm chứng

Giữ raw joint/GT/IMU, command/reference history và lifecycle theo parent
đang dùng, cùng ledger, clock/epoch và source/config hashes.

| Kênh | Dùng để kết luận | Giới hạn |
|---|---|---|
| Decision time, planned stop, tail level, health flags | Xác nhận đúng lịch và quyền nguồn | Không thay sample timestamp body |
| Requested → eligibility/windowed → stateful accepted reference | Quyền tạo reference sau projection | Chưa là physical authority |
| Driver requested/executed reference, target/cap/slew và feedback từng bánh | Lệnh tới backend và đáp ứng bánh | Telemetry Sim, không motor readback thật |
| Body GT header/twist, nominal scorer độc lập, path | Đáp ứng thân và task-quality | Chỉ cho scoring, không vào scheduler |
| Native outcomes, reset/ready ACK, clock/gap/window support | Measurement validity | Counts hoặc ready flag riêng không đủ |

Thứ tự trả lời: **reference khác không → driver thực thi không → wheel/body
khác khi nào → outcome có tốt hơn không**. Không dùng requested action hoặc
snapshot làm bằng chứng tự động cho body response. Không suy latency dưới
độ phân giải sample; báo interval giữa sample, không nội suy để tăng precision.

Trước tail: reference phải cùng lịch/shaping. Kiểm mô tả physical approach
trên1 s trước tail. Caliper RMS body difference **0,001 m/s** chỉ là đề xuất
screening; vi phạm làm causal interpretation unknown, không loại run/đổi
ngưỡng/thêm mẫu. Fresh launch paired seed vẫn không là exact-state branch.

## 5. Metric, estimand và quyết định đề xuất

### Primary

`ISE_v = integral((v_body − v_nominal_independent)^2 dt)` trên cửa sổ cố định
`[source_stop−0,5; source_stop+2,5)`; đơn vị **m²/s**, không phải năng lượng.
Lấy window theo measurement task time của body; thời điểm gửi action dùng
decision clock riêng. Không lấy index quyết định gán cho sample tiếp theo.
Native statistic được định nghĩa là `sum(e_v² * 0,1)` trên các sample có
measurement time trong window; đây là tích phân rời rạc theo contract,
không phải tích phân liên tục đã biết chính xác. Cần kiểm executable metric
và boundary support trước release, giữ cùng quy tắc ở mọi arm.

Giữ native primary và hai sensitivity grids GT-header20 ms /dịch+10 ms
riêng, không pool/chọn grid có lợi. Không sửa native task outcome hoặc
coverage contract. Nếu metric trên grid không có support hợp lệ, verdict
unknown/measurement fail theo protocol; không tạo số0 cho dữ liệu thiếu.

Mỗi tail sign và stop báo riêng trung bình hai tỷ lệ candidate/control
trong block trừ1. Báo cả absolute ISE/delta và từng block; denominator0 thì
relative unknown. Giữ cả hai dấu, không chỉ trình bày arm thắng. Không có
selection/confirmation holdout trong12 attempts nên kết luận chỉ screening.

### Secondary và ràng buộc

Full14 s velocity RMS, signed error, từng bánh, path RMS/max, target saturation,
quiet-condition onset/settling interval và task/stop outcomes. Source/horizon
giữ nguyên; không đổi task deadline để tạo lợi ích thời gian. So cả primary
local và toàn tuyến nhằm phát hiện cải thiện tail đổi lấy lỗi ở nơi khác.

Giữ functional proposals của parent: marker0,95 m, max guided cross-track
0,04 m, estimator position/yaw0,05 m/rad và điều kiện task/stop trong config.
Đây là ngưỡng nghiên cứu Sim đã khai báo, không là tiêu chuẩn an toàn thật.

### Go / no-go / unknown — chưa chấp nhận để chạy

- **Useful authority proposal:** body contrast ≥0,001 m/s kéo dài≥0,2 s,
  có chain tới driver/wheel và cùng dấu giữa block. Đây là tiêu chí nghiên
  cứu tạm thời, không phải mức ứng dụng đã chấp nhận.
- **Go sang classical tuning/confirmation:** một dấu có ≥5% ISE reduction
  ở cả hai block/cả hai stops, cùng chiều trên ba grids, task/stop/path
  gates đạt; full-route velocity RMS không tăng quá2% và quiet-onset không
  muộn quá0,1 s so đối chứng. Đây đều là trade-off screening đề xuất, chưa
  là ngưỡng ứng dụng được chấp nhận; 0,1 s tương ứng một native control tick,
  không là precision body timing được bảo đảm. Chưa promote tổng quát;
  chưa mở training TD3 từ kết quả này.
- **No-go:** có reference contrast nhưng không có ích lợi lặp lại, hoặc
  task/stop constraints fail. Giữ historical classical cho envelope đó.
- **Unknown:** thiếu measurement/approach support, effect đổi dấu theo
  grid hoặc block, hoặc effect quá nhỏ. Đóng screen; không tự tăng sample
  hoặc hạ gate. Hướng mới cần câu hỏi/phép thử khác có cơ chế.

Chỉ cân nhắc learning khi còn nhu cầu thích nghi vượt candidate cổ điển
mạnh, có quyền tác động hữu ích và protocol training riêng. Không dùng
critic loss, return hoặc Laya làm gate thắng controller.

## 6. Chuẩn bị offline đã làm và việc còn lại

Đã tạo config immutable-input pins, matrix/order, release=false và helper
preview reference. Fixture kiểm neutral arm parity với adapter cổ điển
frozen, prefix equality, chỉ khác trong/quanh tail do carry-over, zero-source
priority và invalid-state handling. Đây là kiểm toán học/phần mềm; **không
có wheel/body mới hoặc12 lần Gazebo đã chạy**.

Trong fixture straight-source này, chênh accepted reference đạt±0,005 m/s
từ đầu tail và có thể còn tới gần2 s sau source stop do state của slew
limiter, dù proposed residual lúc source-zero đã bằng0. Đây là contrast ở
reference để thiết kế phép thử, không phải body-response/stop-time đã đo.

Còn lại trước release: isolated versioned runtime adapter, trace schema,
runner/ledger/readiness/stop handling, live Sim acquisition/window support,
source/install parity và storage/wall-cap review. Không chạm các file frozen
để biến checkpoint cũ thành ABI mới; không resume actor trong screen này.

Tối đa một correction có căn cứ trong giai đoạn chuẩn bị offline. Nếu còn
lỗi sau correction, giữ unknown và review thiết kế trước release. Sau khi
batch bắt đầu, không vá nóng hoặc mở slot replacement trong cùng protocol.

## 7. Dung lượng

Dự toán12×40 MiB raw +128 MiB metadata/analysis +1 GiB reserve ≈1,59 GiB.
Đây là estimate từ workflow cũ, không là upper bound hoặc xác nhận đĩa đủ.
Hiện máy chỉ còn khoảng1,9 GiB. Preflight thực phải đo lại và giữ reserve
khi chạy; không tự xóa raw/checkpoint, hạ reserve hay giảm logging để vừa đĩa.
Wall cap180 s/attempt là đề xuất cần review với runner, không là thời gian
đã quan sát hoặc ngân sách được cấp. Không dự báo wall time toàn nghiên cứu.

**Bước nên làm tiếp sau review draft:** xây adapter/runner tách phiên bản và
kiểm parity offline. Không cần chờ Pi; chưa chạy batch ở bước hiện tại.
