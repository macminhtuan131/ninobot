> **Cập nhật mới07/11 — pilot20k đã hoàn tất:** 20.000transitions,10.000critic/5.000actor updates;6/6eval đạt task/stop. Tốt hơn B0 trong screen, chưa chứng minh hơn classical. Đề xuất continuation10k, chưa chạy thêm. [Đánh giá và bước tiếp](NINO_COMMON_TD3_20K_ASSESSMENT_2026-11-07.md). Các trạng thái “đang chạy/chờ dung lượng” dưới đây là lịch sử.

# Pilot TD3 common103D/1D — đã khởi chạy

**Trạng thái quan sát: RUNNING**, 2026-11-07T05:47:25.253333+00:00. Đây là snapshot,
không phải xác nhận job hoàn tất. Trạng thái live nằm trong `status.json`
do watcher cập nhật mỗi30 giây; khi đóng job sẽ có `review.json`/`REVIEW.md`.

## Việc đã thực hiện

- Dọn đúng cache tải gói pip bằng `pip cache purge`:1331files,5460,6MB.
  Cache có thể tải lại; không xóa dataset/checkpoint/artifact nghiên cứu.
- Preflight có 9.99GiB trống,
  vượt dự toán6,99GiB. Kiểm lại50file hash của smoke và engine identity đạt.
- Khởi chạy đúng request đã chuẩn bị: fresh seed11,20.000transitions,
  history5/103D, common1D ±0,005m/s, baseline Ki0,10 frozen, clear-box,
  source-stop luân phiên6/8s, horizon14s,10Hz. Không cần real dataset mới.
- Research MLP256×256, replay32.768,warmup10.000,LR0,0003,batch256;
  checkpoint mỗi5.000steps,wall cap180phút. Không đổi profile giữa chừng.
- Evaluation cuối đã đặt6condition: B0/classical scheduled/TD3×stop6/8,
  tối đa840evalticks. Không tự retry hoặc thêm số bước sau kết quả.

## Tiến độ lúc cập nhật

| Đại lượng | Quan sát |
|---|---:|
| Trace transitions đã ghi | 976 |
| Fresh episodes đã launch | 7 |
| Full task terminals | 6 |
| Critic updates ở log gần nhất | 0 |
| Trạng thái học | warmup nếu global step≤10.000 |
| Benefit/hardware | chưa xác nhận /0actions |

Counts trên là tiến độ ghi trace, chưa phải audit replay sau checkpoint cuối.
Warmup vẫn thu transition nhưng chưa cập nhật optimizer. Không cộng learner
mới với A1024/C840/smoke64 thành một learner hoặc nhiều training seeds.

Artifact job:
`/home/tuanmac/nino_research/td3_studio/20261107T054154365880Z_common_train`

QA/log/watcher:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/common_studio_pilot_2026-11-07`

`request.json`, `preflight.json` giữ ngân sách/source trước chạy;
`pilot_stdout.log` giữ quá trình; `status.json` là live snapshot.
Watcher không chạy controller, training, retry hoặc resume: sau khi worker
đóng manifest, nó kiểm hash, load checkpoint/replay, kiểm finite/counters,
và tóm tắt native/GT20ms/+10ms theo condition nếu evaluation hoàn tất.
Automatic QC không thay thế review khoa học và không tự promote TD3.

## Xem trong Studio

Mở lại Studio → **Train TD3 · Sim** → thư mục lưu
`~/nino_research/td3_studio` → **Đọc lại phiên/checkpoint** để xem dòng job.
**Mở TensorBoard** đọc learning curves trong cùng root. Giai đoạn warmup
chưa có actor/critic loss là đúng; không coi đó là lỗi chỉ vì chưa update.
Không bấm Train lần nữa khi job này còn chạy; worker giữ shared Sim lock.

## Sau khi job đóng

1. Kiểm status/error và replay/checkpoint counters thực, không chỉ requested20k.
2. Kiểm coverage/action gating, learning curves và task/stop/measurement validity.
3. So final checkpoint với B0/classical theo từng lịch dừng và cả3grids.
   Kết luận đổi chiều theo grid hoặc effect nhỏ thì UNKNOWN; chỉ một seed và
   seen conditions chưa đủ generalization/convergence. Chưa tự tăng budget.
4. Nếu job lỗi: giữ raw/manifest/checkpoint hoàn chỉnh cuối; đóng phần còn lại,
   phân tích đúng failure trước khi đề xuất protocol tiếp. Không tự chạy lại.

Thiết kế/bằng chứng tích hợp trước chạy:
[protocol và smoke](NINO_COMMON_STUDIO_PILOT_2026-11-07.md).
