> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

# Coverage V2 — đã chạy, đóng do readiness đầu episode

06/11/2026 · **Partial training có dữ liệu hợp lệ; chưa có phép so sánh hiệu quả.**

## Quyết định

- Đóng release V2 và toàn bộ 49 launch slots chưa chạy. Không retry/resume,
  không bổ sung learner/eval vào root đã tiêu thụ. V1 và 63 slot V1 vẫn đóng riêng.
- Giữ checkpoint A seed11 hoàn tất và partial C seed11; không gọi cả study đạt.
- Giữ classical/B0 làm reference. Chưa có evidence mới để promote TD3,
  đánh giá lợi ích probe, chọn checkpoint theo reward hoặc triển khai hardware.
- Sửa **reset readiness của drive**, không tăng gain/current, thay reward,
  hạ coverage, bỏ failure hay điều chỉnh QoS để che lỗi này.

## Kết quả thực thi

Job qua nút GUI, fingerprint/pins và budget theo
[release V2](NINO_SIM_COVERAGE_V2_RELEASE_2026-11-06.md).

| Đại lượng | A Gaussian seed11 | C stratified seed11 | Tổng |
|---|---:|---:|---:|
| Raw control attempts / trace rows | 1.024 | 841 | 1.865 |
| Transition vào replay | 1.024 | 840 | **1.864** |
| Critic optimizer updates thực | 960 | 776 | **1.736** |
| Actor optimizer updates thực | 480 | 388 | **868** |
| Fresh Gazebo launches | 8 | 7 | **15/64** |
| Full task terminals đã đạt trước lỗi | 7 | 6 | 13 |
| Trạng thái | Learner hoàn tất, cuối44bước censored | Partial; raw841 bị inhibit | Study failed |

Thời gian worker khoảng694,3giây. Bốn learner chưa khởi động; toàn bộ16eval
chưa chạy. Hàng lỗi không vào replay; không vá nó thành zero hoặc transition
thành công. Hai arm mới chỉ có seed11, không phải nhiều seed độc lập.

A đã qua replay/checkpoint/optimizer-target save/load parity. Histogram request
trong open window của A là `[216,49,18,6]`, chưa đạt rule coverage đã chốt.
C chưa hoàn tất cùng ngân sách nên chưa dùng nó làm đối chứng coverage/outcome.
Không suy từ training loss, arrival hoặc checkpoint tồn tại thành learned benefit.

## Nguyên nhân có bằng chứng

**Vị trí lỗi:** C seed11, episode6, decision đầu, timestep841.

| Bằng chứng từ raw/config/source | Kết luận trong phạm vi này |
|---|---|
| Mechanical settling đủ0,5s, `passed=true` | Gate hiện tại chỉ kiểm body/wheel yên; chưa bảo đảm drive đã nhận feedback |
| Observer có joint; support checks toàn batch tối đa1ms ở cả hai reader | Không phải tình huống observer không có joint tại boundary này |
| Drive diagnostics stamp2,554s: `have_wheel_state=0`, `cmd_fresh=0` | Backend actuator chưa ACK wheel feedback trước decision stamp2,563s |
| Input `permission=false`, guidance `owner_denied` | Pipeline bị inhibit trước khi actor request có thể tác động |
| Window đóng, residual sau window0, final reference `[0,0]` | Hàng lỗi không thực thi lệnh tiến/residual khác zero |
| Drive từ stamp2,634s có `have_wheel_state=1`; input sau tick2,663s có permission | Readiness đến muộn hơn decision đầu; không được dùng mẫu sau để hợp thức hóa mẫu trước |
| `reference_trace.proposal=null` | Đây là output của nhánh inhibit, không phải scalar action TD3 bị thiếu |
| Validator success gọi `list(null)` | Báo TypeError `'NoneType' object is not iterable`, che mất lý do inhibit phía trước |

14/15 initial rows còn lại có permission thật và proposal warmup `[0,0]`.
Correction metadata của V1 đã hoạt động: cả1.865raw rows có condition khớp
arm/seed/stop6–8. Lỗi V2 khác lỗi metadata V1.

**Giới hạn nguyên nhân:** chưa tách được DDS discovery, callback scheduling hoặc
thời điểm khởi động driver thành nguyên nhân duy nhất của ACK muộn. Không quy
thành lỗi motor/nguồn robot thật hoặc kết luận cần tăng current. Source hiện tại
không kiểm ACK này trong settling là lỗ hổng readiness có thể sửa độc lập.

## Integrity và measurement

- **390 file** khớp SHA256; manifest trạng thái failed được giữ nguyên.
- **5.685 boundary checks**, hai reader đều supported; max joint age **1ms**.
- Primary115.749 / independent115.796 records; common115.736 source stamps,
  **0 payload mismatch** trên phần giao. Counts khác nhau chưa được gọi là loss.
- **3.880 physics requests** đủ ACK/completion/exact iterations, retries0.
- 30 parameter readbacks;15observer process exit0/shutdownACK;
  lifecycle đóng hết, errors trống. Không còn owned Gazebo/worker.
- Đây không chứng minh mọi source sample loss-free hoặc actuator đã ready ở
  mỗi decision. Joint-observer support và drive acknowledgement là hai claim riêng.

## Correction offline đã chuẩn bị

`coverage_reset_readiness.py` là module **chưa nối vào runner**:

1. Candidate predicate yêu cầu đồng thời physical quiet, drive diagnostics
   fresh, `have_wheel_state=1` và executed/target zero được ACK. Missing/unknown
   bị chặn; không tự đổi permission. Áp trong cùng cap5sim seconds nếu version
   backend sau này; không thêm vòng đợi vô hạn hoặc physics ngoài protocol.
2. Typed fail-closed guard nhận diện input bị inhibit trước validator success.
   Không thay `None` bằng zero, không đưa hàng lỗi vào replay.
3. Recorded-row fixture giữ đúng raw lỗi và raw warmup hợp lệ; test gọi validator
   thật để tái hiện TypeError và kiểm reason rõ hơn. Source V2 đã chạy giữ nguyên.

Các test này chỉ là phần mềm. Việc backend áp gate đúng, giữ task epoch và
không tái dùng support chưa được kiểm bằng Gazebo sau correction.

Kiểm cuối: **75 tests đạt** gồm55GUI,14readiness recorded/synthetic regression
và6metadata regression đã có. Build `nino_rl`/`nino_pi` đạt. GUI có bảng từng
learner, raw/replay riêng, slot đóng, diagnosis và nút xem cả sealed job lẫn
derived audit gắn manifest. Không cộng software fixture thành Gazebo attempts.

## Bước tiếp theo có giới hạn

Xem [outline sau V2](NINO_SIM_COVERAGE_V2_NEXT_2026-11-06.md). Ưu tiên nối
predicate vào **backend candidate có phiên bản**, kiểm fixture drive ACK muộn
và readiness trước task epoch; không viết lại frozen backend hiện tại.

Trước learner mới, đề xuất qualification zero-only riêng, tối đa2fresh launches,
10zero ticks/launch, optimizer0; giữ setup cap5sim seconds, thông số PI/physics
và measurement gates. Đây là **đề xuất chưa release**, không dùng49slot V2.
Fixture âm tính phải fail, readiness UNKNOWN không được coi là PASS. Tối đa
một correction có căn cứ; nếu vẫn không qua, dừng mở training để review backend.

Nếu qualification đạt, ưu tiên thiết kế **eval-only** checkpoint A seed11 đã
hoàn tất với B0/cổ điển cùng reset contract trước khi đầu tư lại ma trận train.
Một seed chỉ là screening, không trả lời lợi ích probe hoặc generalization.
Không tiếp partial C hoặc tự mở full matrix V3.

## Provenance

- Root: `/home/tuanmac/nino_research/sim_coverage_study_v2`.
- Study: `20261106T111842753138Z_sim-coverage-v2-study`.
- Manifest SHA256:
  `0ba2d7fd3b9d98dff78e8dc27c8f1384a8f6b0d4efff113ad668b3b12c7ca7ca`.
- Fingerprint:
  `57dc776c83cf8ef3de6830423f27577b80299b089a628a3c9404d54d9f7894fe`.
- Root `review.json` là derived audit ngoài sealed artifact, gắn manifest SHA.
- Workspace QA: `artifacts/sim_coverage_v2_release_2026-11-06/` gồm release
  before/effective/closed, GUI events, audit, diagnosis, regression, ảnh và build.
- Hardware actions0; real data cutoff02/11 giữ nguyên. Chưa obstacle/contact
  evaluation, holdout hoặc deployment mới.
