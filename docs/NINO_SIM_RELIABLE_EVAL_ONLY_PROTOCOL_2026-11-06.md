# Protocol evaluation-only: ba checkpoint TD3 RELIABLE

06/11/2026 · Một đợt Sim local mới, được tiếp tục theo yêu cầu người dùng.
Không train lại hoặc mở lại batch learner V1 đã đóng.

## Đầu vào và câu hỏi

Ba final checkpoint seed11/22/33: mỗi seed đã train1.024transition, có
960critic updates và kiểm model/replay/targets/optimizers đạt. Job cha failed
ở evaluator namespace, không phải trong ba learner. Chỉ chấp nhận đúng lý
do failure đó và đủ ba training results. Manifest cha pin:
`bb6293d9d5e62b1f63646e805e6b67dc9f712fc570ecbe2fa29b75de629ff053`.
Model/replay/identity từng seed pin trong YAML; kiểm toàn bộ648file của cha.

Câu hỏi: với cùng information/action/limits, final TD3 có tracking tốt hơn
B0 và common cổ điển trên clear-box known-stop mà vẫn đạt task/dừng không?
Đây là development evaluation trên condition đã thấy, không holdout/contact.

## Budget và thứ tự khóa trước chạy

| Slot | Arm | Seed learner | Source stop(s) |
|---:|---|---:|---:|
|1|B0|—|6|
|2|TD3|11|6|
|3|Classical_scheduled|—|8|
|4|TD3|22|8|
|5|TD3|33|6|
|6|Classical_scheduled|—|6|
|7|TD3|11|8|
|8|B0|—|8|
|9|TD3|22|6|
|10|TD3|33|8|

- Tối đa10fresh launches,140tick/14s mỗi lượt, tổng1.400tick.
- Training/optimizer/hardware0. TD3 deterministic, không exploration noise.
  Không chọn seed/checkpoint theo outcome; đánh giá cả ba final checkpoints.
- Wall deadline1.800s: qualification hai B0 mất89,58s/280tick, suy rộng
  khoảng448s/1.400tick; margin xấp xỉ4 lần cho startup/inference/cleanup.
  Đây là deadline job, không chứng nhận realtime.
- Một root `~/nino_research/sim_reliable_eval_only_v1`, action
  `sim-reliable-eval-only`. State tồn tại là đã tiêu thụ, kể cả corrupt.
- Không thêm physics smoke ngoài budget. Một lỗi/cancel đóng mọi slot còn
  lại; giữ partial/raw/attempts và manifest, không retry/correction trong đợt.

## Controller và lifecycle

Giữ ABI103D/1D, history5, common±0,005m/s, preview lịch dừng, shared window,
projection/ramp/follower/PI/reward/geometry/physics từ learner. Chỉ identity
đợt eval mới khác; cùng backend ở tất cả arms.

Mỗi lượt có một EpisodeLifecycle, backend/context/executor/log/partition và
independent observer mới. READY trước launch, namespace kiểm sau reset và
**trước control interval đầu**, close/ACK sau lượt. Không tái dùng support
epoch cũ. Joint primary RELIABLE/depth100; independent BEST_EFFORT audit,
không vá primary. Cả hai giữ gate40ms, auxiliary failure cũng quarantine.

Ghi requested/mapped/accepted riêng, control attempt trước step và trace
trước validation. Với TD3, kiểm hash policy state/counters trước/sau; không
gọi learn/update hoặc sửa checkpoint. Không resume replay để inference.

## Metrics và gate

- Primary: body-minus-independent-nominal velocity RMSE toàn14s, native100ms.
- Constraints:140tick, marker0,95m, quietstop2s, maxcross-track40mm,
  estimatorposition50mm/yaw0,05rad, không guidancefault hoặc intervention.
- GT-header20ms và dịch+10ms là diagnostics riêng, không nội suy body.
  Giữ spikes/failures; thiếu support hoặc task fail thì không promote.
- So từng seed/stop với cả B0 và classical; báo absolute/relative deltas,
  path/task/stop và ranking theo cả hai grids. Không pooled ratio hậu nghiệm,
  không chọn grid/seed thuận lợi hoặc tự tăng mẫu. Một eval/condition và ba
  learner seeds không đủ xác nhận generalization, không exact-state pairing.
- Minimum worthwhile effect vẫn null. Effect nhỏ/đảo ranking theo grid →
  unknown; không hơn classical → giữ baseline, audit action theo phase.
  Đủ10lượt không tự là benefit promotion, training dài hoặc hardware release.

## Gate phần mềm và artifact

Trước job: test factory/namespace cho mọi arm, checkpoint/manifest/replay/
identity/runtime tamper, budget/order, failure/cancel, consumed ledger và GUI.
Không gọi software tests là trial robot hoặc thêm source-delivery guarantee.

Artifact: protocol/fingerprint/dependencies, config/epoch/READY/close,
world/parameter/physics logs, per-control attempt/trace, actor before/after,
native/header summaries, progress/result/job/manifest. GUI có nút thực thi,
log tiến độ, bảng kết quả, hiển thị failure và khóa budget đã tiêu thụ.

**Điểm dừng:** đóng đợt sau đủ10lượt hoặc lỗi đầu. Quyết định từ bảng kết
quả hợp lệ; không train lại để sửa evaluator hoặc che kết quả bất lợi.
