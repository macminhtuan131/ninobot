# Protocol: qualification103D/1D trong Gazebo, chốt trước launch

05/11/2026 · Theo yêu cầu tiếp tục nhánh Sim, triển khai từ
[draft](NINO_SIM_EQUAL_INFORMATION_GAZEBO_NEXT_2026-11-05.md).
Đây là budget mới cho integration, không mở lại batch đã đóng.

## Câu hỏi, điều kiện, budget

Wrapper103D/1D có giữ causal preview/history, source/decision epoch,
shared window, nominal score và requested→mapped→accepted semantics khi
nhận message Gazebo không? Không đánh giá learner hoặc ưu thế thuật toán.

Thứ tự cố định, fresh launch từng lượt,140ticks/14s mỗi lượt:

| Lượt | Controller request | Source stop |
|---|---|---|
|1 |B0 scalar0 |6s |
|2 |Classical cùng packet103D |6s |
|3 |Probe scalar−1/0/+1 theo step%3 |6s |
|4 |Cùng probe |8s |

Tối đa4launches/560evaluation ticks, actor inference/optimizer/train0.
Không smoke launch ngoài budget, retry hoặc thêm lượt theo kết quả. Seed
reset701 là khai báo, không4training seeds hoặc snapshot/restore exact state.
Root `~/nino_research/sim_equal_gazebo_v1`, action `sim-equal-gazebo`.

Giữ clear box/yaw0/cruise0,2m/s/warmup0,5s/horizon14s, geometry, estimator,
follower, h5, projection/ramp/wheel PI của parent. Physics1ms/native100ms.
Source stop đồng bộ backend/guidance/task/scorer; common±0,005m/s, diff0,
shared withdrawal=stop−0,5s. Không GT/contact/caster vào controller. Không
SSH/hardware hoặc dùng current/gain thật. Deadline toàn job1200wall seconds.

## Chốt kiểm và measurement

- Pin offline fingerprint67bb76d… và ABI b8c71ccb…; verify parent manifests/
  runtime/hash trước ledger. Giữ frozen core và qualifier offline.
- Mỗi tick:103Dobs/1Drequest và ABI mới;100history khớp inherited trace trong
  tolerance2e−6; source/decision epoch delta≤1e−8s (software sim clock check,
  không độ chính xác sensor thật). Preview countdown và previous requested
  action đúng; no truth input; requestedscalar/mapped2D/accepted giữ riêng.
- Một legacy shadow **chỉ đọc cùng received source** kiểm window predicate
  và nominal shaper; classical proposal phải khớp. Không ép số active ticks
  của fixture31/51 hoặc batch cũ30/50; ghi first source/steady/window thực.
- Shared nominal adapter/scorer parity≤1e−10. Gate closed thì mapped0,
  request khác0 vẫn lưu replay. Yaw follower không bị xóa bởi common-only.
- Replay chẩn đoán560rows tối đa, không train: scalar requested, obs103/
  nextobs103, reward và terminal/timeout. Dùng chung numerical audit từ
  helper offline nhưng report scope mới là Gazebo integration diagnostic.
- Raw wheel/IMU/GT/drive, estimator/support/epoch, guidance, physics requests/
  parameter readbacks/closure giữ nguyên. Native boundary source age≤40ms
  là engineering measurement gate kế thừa estimator gap; không đổi max-age
  của controller hoặc chấp nhận một ngưỡng phần cứng.
- Chốt cả diagnostic GT-header20ms/dịch10ms theo cùng method của stop-time
  transfer: causal latest GT, không nội suy body, max support age20ms. Thiếu
  support→measurement unknown, đóng slot chưa dùng. Không vá gap/cắt spike.
  Counts/hash không là proof continuous coverage hoặc mọi transient limiter.

## Pass/stop/unknown

Integration pass cần đủ4×140ticks, source/guidance/physics/parity hợp lệ,
đạt marker0,95m+quiet stop2s và engineering bounds cũ: maxpath40mm,
maxestimate50mm/yaw0,05rad. Native body/path RMSE cùng timestamp diagnostic
được report riêng, không dùng làm benefit gate hoặc chọn checkpoint.

Physical/source/guidance failure dừng ngay, ghi progress/ledger/manifest và
đóng slot chưa launch. Measurement/functional failure cũng đóng slot còn lại
với grade unknown/failed. Không retry, hạ coverage, đổi metric hoặc tune.
Tối đa một correction có nguyên nhân rõ chỉ trong contract khác trước khi
phải quyết định; không coi failure là0 hoặc overwrite run.

## Sau batch

Đạt →wrapper có bằng chứng integration trong clear development6/8s; chốt
bounded learner pilot mới với103D/1D, research objective, hyperparameters,
seeds/timesteps và split. Chưa có learned checkpoint hoặc lợi ích residual.
Không cần đợi real data/factory specification hoàn chỉnh để tiếp tục Sim;
engineering effect tạm phải được ghi là đề xuất nghiên cứu. Không đạt →sửa
đúng adapter hoặc giữ baseline; không tăng train để che lỗi integration.
