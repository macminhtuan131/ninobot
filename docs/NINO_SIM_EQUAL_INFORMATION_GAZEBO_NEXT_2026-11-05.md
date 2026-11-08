> **Cập nhật05/11:** đã triển khai [protocol mới](NINO_SIM_EQUAL_GAZEBO_PROTOCOL_2026-11-05.md) và [đóng đủ4/4qualification](NINO_SIM_EQUAL_GAZEBO_RESULT_2026-11-05.md). Phần dưới giữ draft trước chạy; không mở lại batch.

# Dự thảo bước tiếp: qualification wrapper103D/1D trong Gazebo

05/11/2026 · **Chưa triển khai/chạy; tối đa4launches/560ticks được đề xuất,
chưa cấp budget trong artifact offline.** Không optimizer hoặc phần cứng.

## Câu hỏi duy nhất

Wrapper mới có giữ plan/source clock, nominal scorer và action semantics khi
chạy với message cảm biến do Gazebo phát không? Đây là gate
software/physical integration, không là test TD3 thắng classical hoặc yêu
cầu phải có factory minimum effect trước khi được kiểm phần mềm.

## Thiết kế nhỏ nhất được đề xuất

Clear box/yaw0/cruise0,2m/s/warmup0,5s/horizon14s; giữ estimator/follower,
wheel PI/projection/ramp của parent.4fresh launches, mỗi140ticks:

1. B0 scalar0, source stop6s.
2. Classical nhận packet103D, source stop6s, shared withdraw5,5s.
3. Probe scalar theo chu kỳ−1/0/+1, source stop6s.
4. Cùng probe, source stop8s, shared withdraw7,5s.

Probe chỉ là phần mềm deterministic để kiểm requested/gated/accepted và
replay semantics, biên common±0,005m/s. Không gọi nó là trained TD3/learner
seed. Không so sánh lợi ích dựa4 lượt này; stop6/8 vẫn development đã xem.
Nếu chỉ cần kiểm thêm offline thì không chạy physics để thay unit tests.

## Chốt trước chạy khi triển khai

- Pin protocol mới, identity103D/1D và parent qualification; root/ledger mới,
  không sửa artifact offline hoặc các batch đã đóng. Kiểm native phase
  epoch/source6/8s, causal feature/history, không contact/GT input.
- Mỗi tick, nominal preview khớp scorer; scalar request đúng trace/replay,
  proposal2D differential0; gate closed thì proposal0, request vẫn giữ.
  Không ép active count31/51 của fixture hoặc30/50 cũ: kiểm cùng source
  và rule, ghi thời điểm thực nhận source và nominal steady.
- Raw giữ wheel/IMU/GT/drive, estimator/support/epoch, source/planned time,
  request/window/mapped2D/projection/final/target, physics ACK/delta và
  closure. **ABI cố định103D**, gồm100history+2plan+
  previous request; không tự thêm feature hoặc đổi shape ở launch.
- Pass integration cần đủ horizon, không source/guidance/physics fault,
  parity đúng và physical/stop/engineering bounds cũ. Ghi path/body RMSE
  diagnostic riêng, không dùng chúng làm benefit gate. Không suy continuous
  transient coverage từ counts; thiếu support thì kết luận unknown.
- Failure/missing/physical gate fail: đóng slot còn lại, giữ raw, không retry
  hoặc tăng số mẫu/tune. Tối đa một correction có nguyên nhân rõ trong
  contract khác rồi phải quyết định, không lặp integration vô hạn.

## Sau qualification

Đạt →có thể thiết kế bounded TD3 common-only pilot với103D/1D và budget mới.
Minimum worthwhile effect tạm cho nghiên cứu có thể được đề xuất cùng
protocol; không cần chờ một yêu cầu nhà máy hoàn chỉnh hoặc thu real data
để làm Sim. Vẫn phải nói rõ phần chưa được chấp nhận và không promote
ứng dụng từ return/ít bước. Không đạt →sửa đúng adapter hoặc giữ baseline;
không train để che mismatch.

Trước optimizer: remaining gap hợp lý, research hyperparameters, seeds/
timesteps, snapshot/replay/resume schema và split/held-out conditions phải
chốt. Catalog seeds11/22/33 hiện là đề xuất, không là3 seeds đã train hoặc
budget đã mở. Dữ liệu thật/model calibration/hardware deploy là gate riêng.
