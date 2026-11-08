> **Cập nhật cuối07/11: COMPLETED, QC đã đóng.** Global30.000,
> 20.000critic/10.000actor updates,6/6eval đạt task/stop. Chưa hơn classical;
> [đánh giá30k và khuyến nghị](NINO_COMMON_TD3_30K_ASSESSMENT_2026-11-07.md).
> Phần snapshot đang chạy bên dưới được giữ làm lịch sử.

# TD3 continuation20k→30k — lượt đã được cấp budget

**Đã khởi chạy07/11/2026.** Trạng thái trong tài liệu này là snapshot;
xem `status.json`/worker `job.json` để biết đang chạy hay đã đóng.

## Ngân sách và điều kiện giữ cố định

- Một continuation **10.000steps**, từ final20k; cùng seed11,common103D/1D,
  history5/10Hz, clear-box, source-stop6/8s, Ki0,10 frozen.
- Model/actor/critics/targets/optimizer/replay đã kiểm hash/source/runtime.
  Bắt đầuglobal20.000,10.000critic/5.000actor,20.000replay,pos20.000.
- **Không warmup mới**; optimizer tiếp tục ngay. Không zero-init actor.
  Simulator/history bắt đầu episode mới, không restore physics/RNG bit-exact.
- Giữ nguyên algorithm/reward/action/limits; không tuning trong lượt này.
- Tối đa73training launches; checkpoint mỗi5.000steps thêm; wall cap180phút.
- Final evalB0/classical scheduled/TD3×stop6/8:6launches/840ticks.
- Khi hoàn tất bình thường, kỳ vọngglobal30.000, tổng20.000critic/
  10.000actor updates,30.000replay trongcapacity32.768; phải kiểm counters thực.
- Không retry/gia hạn hoặc chọn checkpoint theo kết quả eval.
  Screening5% so classical trên cả3grids/hai stop vẫn chỉ là mục tiêu
  nghiên cứu đề xuất, không là chuẩn an toàn/ứng dụng hay chứng nhận lợi ích.

## Readiness đã kiểm trước launch

- Parent manifest giữSHA256
  `1c0dba102f39adaaa419a682738713e701bbd8e9070113828821dbfe6e2db37f`.
- Model/replay/counters/identity/source khớp; không có jobSim khác giữ lock.
- Disk trống4.64GiB,
  vượt dự toán4,15GiB bao gồm1GiB reserve. Không hạ gate hoặc xóa dataset.

## Snapshot tiến độ lúc ghi tài liệu

- Global trace: **20914**;
  thêm914rows, 6terminal đầy đủ.
- Critic ở log gần nhất: **10907**
  (cumulative, có thể trước optimizer call cuối). Chưa là QC replay cuối.
- Chưa có kết quả benefit mới hoặc hardware action.

Job:
`/home/tuanmac/nino_research/td3_studio/20261107T080414816378Z_common_train`

QA:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/common_studio_continuation_2026-11-07`

`preflight.json`/`request.json` giữ budget và parent identity;
`continuation_stdout.log` giữ quá trình; `status.json` được watcher đọc và
cập nhật mỗi30s. Sau khi worker đóng manifest sẽ có `review.json`/`REVIEW.md`
nếu QC thành công, hoặc `watcher_error.txt` nếu QC gặp lỗi. Watcher không
train, điều khiển robot, retry hoặc cấp thêm physics.

## QC khi job đóng

1. Kiểm hash toàn bộ sealed files và parent checkpoint còn nguyên.
2. Load finalmodel/replay; kiểm new10.000rows và20.000parent rows giữ nguyên,
   counters/finite targets/optimizers, lifecycle closure; không gọi loss
   giảm là convergence.
3. Đọc eval6condition và so TD3 với B0/classical trên native/GT20ms/+10ms.
   So với checkpoint20k thuộc blockfresh khác, không exact-state causal test.
4. Giữ dữ liệu lỗi/grid-sensitive và không tự promote. Sau30k phải review
   trước repeat/seeds/ablation hoặc giữ classical cho benchmark này.

## Studio

Mở lại Studio, chọn **Train TD3 · Sim**, root `~/nino_research/td3_studio`.
Đọc lại phiên để thấy job mới; TensorBoard cùngroot đọc learning curves.
Trang tiến độ vẫn giữ20k là kết quả đãreview, đồng thời hiển thị continuation
qua live snapshot. Snapshot không được gọi là replay đã kiểm cuối phiên.
Không bấm Train thêm khi continuation này còn chạy.

[Đánh giá20k và cơ sở đề xuất](NINO_COMMON_TD3_20K_ASSESSMENT_2026-11-07.md).
