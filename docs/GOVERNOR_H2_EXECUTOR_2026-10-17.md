# Executor H2 — triển khai và kiểm tra offline, 17/10/2026

**Cập nhật analysis:** [bộ phân tích/quyết định offline đã hoàn tất](GOVERNOR_H2_OFFLINE_DECISION_2026-10-17.md).
92 tests liên quan đạt, gồm 52 analyzer và 40 executor/protocol. Executor
vẫn thu thập riêng; analyzer đọc batch để quyết định. Chưa có simulation mới.

## Trạng thái

**Đã triển khai executor giới hạn 16 attempts; 40 tests đạt. Chưa chạy ROS,
Gazebo hoặc episode simulation nào.** Kết quả tests không phải xác nhận
integration với simulator thật hay lợi ích governor.

Theo yêu cầu người dùng, bộ tiêu chí slip giảm 10%, thêm tối đa 0.5 giây,
quality phụ không xấu đi được lưu **riêng dưới dạng đề xuất, chưa áp dụng**.
Form ứng dụng trong protocol vẫn để trống; không tự xem lại nội dung đề xuất
là đồng ý cấp ngân sách. Optuna/predictor/PPO chưa mở.

## 1. Code và ràng buộc thực thi

Code mới: `src/nino_rl/scripts/run_governor_h2_replication.py`.
Tests: `src/nino_rl/test/test_governor_h2_executor.py`.

- Lấy đúng schedule đã khóa của [protocol H2](GOVERNOR_H2_REPLICATION_PROTOCOL_2026-10-17.md):
  seed 77500/77501, 8 cặp, **16 slot**, giữ thứ tự cả block/repeat/arm.
- Mỗi slot tương ứng một lần gọi runner cold-start hiện có với đúng **một
  seed và một profile**, không `shuffle-order`, không oracle. Tiến trình
  trước phải đóng xong mới được xét slot tiếp theo; không chạy song song.
- Tạo `ledger.json` đủ cả 16 slot trước attempt đầu. Ghi trạng thái
  `starting` và launch request **trước khi gọi adapter/Popen**; JSON ghi qua
  file tạm, fsync và atomic replace. `events.jsonl` bổ sung nhật ký.
- Output đã tồn tại bị từ chối: không resume, retry, replacement hoặc tăng
  số lượt. Interrupted attempt vẫn tiêu thụ slot, các slot chưa chạy giữ
  `not_attempted`; không biến chúng thành physical failure.
- Trạng thái hoàn tất collection **không phải H2 pass**. Executor không tính
  promotion từ mean của các lượt success hoặc tự mở tuning. Thống kê/quyết
  định H2 theo protocol còn phải được thực hiện sau batch được cấp ngân sách.

## 2. Failure và cleanup

| Kết quả | Xử lý |
|---|---|
| Timeout/stall/off-path/wrong-direction/goal-missed, sensor/setup vẫn hợp lệ | Giữ failure và metrics thiếu dạng null; không chạy bù; có thể tiếp tục slot còn lại |
| Arrival đạt nhưng stop không ổn định, đủ dữ liệu quan sát | Giữ arrival thành công và stop thất bại riêng; không thể promotion |
| Reset, timestamp, coverage integrity, provenance hoặc outcome không xác định | Dừng batch; không gán missing thành success/failure vật lý |
| Rollover, governor/navigation fault, collision hoặc trạng thái vật lý không hợp lệ | Dừng, giữ termination/outcome gốc |
| Interrupt/child timeout/exception | Lưu ledger/result có sẵn, dừng, không retry |
| Kết quả nhầm seed/arm | Lưu kết quả để chẩn đoán nhưng không gán outcome đó cho slot được phân công; dừng |

Process child chạy trong session riêng. SIGINT được gửi cho **runner thuộc
executor** để runner dọn evaluator/Gazebo qua `finally`; không dùng killall
hoặc dừng simulator của công việc khác. Nếu không kết thúc trong giới hạn
cleanup, ghi unconfirmed và không khởi động attempt tiếp theo. Mỗi child có
deadline wall-time hữu hạn, không tự gọi lại khi timeout.

Đường cleanup này mới được kiểm tra với process giả. Chưa chứng minh vòng
đời subprocess/ROS/Gazebo thực tế trong batch live.

## 3. Reader và bảo toàn dữ liệu

- Chỉ đọc output của **attempt mới**; không audit lại trace 77400/77401.
- Đọc native arrival/termination trước các bước phân tích có thể lỗi. Nếu
  phân tích sau đó thất bại, native failure đã quan sát vẫn được giữ.
- Kiểm tra child summary có đúng một seed/arm trước khi gọi read-only
  analyzer cũ; không cho fallback tạo thêm một arm không được chạy.
- Xác minh reset gate, world/robot hash thực tế, controller/core/timing,
  config logger/case và config evaluation sau các override chuẩn của CLI.
- Native slip replay/timestamp và coverage whole-route được kiểm tra độc
  lập với việc crossing window có bị censor trong một episode thất bại.
  Thiếu quality do chưa qua cáp không tự bị đổi thành slip=0.
- Thu các report toàn tuyến/crossing/contact sequence và cửa sổ primary
  cố định first manifold +50 ms → +3 s. GT timestamps gốc và raw IMU giữ
  nguyên; báo thêm grid 20 ms/+10 ms theo protocol. Không thay metric native.
- Dữ liệu primary, whole sequence và timing không tự đủ để tuyên bố H2
  pass; quyết định còn cần approach/authority checks và phân tích có lặp.

## 4. Chế độ mặc định và release sau này

**Mặc định chỉ tạo kế hoạch offline**: ledger 16 slot chưa chạy và các argv
dự kiến. Không tạo process, không chiếm ROS domain hoặc tiêu thụ budget.

Chế độ live tương lai yêu cầu đồng thời:

1. Protocol/frozen inputs/workspace references đúng hash.
2. Application form có trạng thái `confirmed`, metric/ngưỡng/chi phí và
   nguồn yêu cầu hợp lệ; `proposed` hoặc form điền dở bị từ chối.
3. Release riêng xác nhận budget tối đa **đúng 16**, app/protocol/executor
   hash và nguồn authorization; thiếu release bị chặn trước output/Popen.
4. Hash bổ sung của **234 source dependencies** hiện tại, gồm launch và các
   helper gián tiếp, khớp release; kiểm tra lại trước/sau mỗi attempt.
5. Domain lock và budget claim dùng một lần. Cùng release được copy đổi tên
   nhưng giữ nguyên bytes cũng không mở lại ngân sách trong cùng claim bank.
   Interrupted/crashed batch không tự được tái sử dụng release hoặc resume.

Khi live được cấp phép, executor ghi authorization/application snapshot vào
output trước attempt đầu. File `release.template.json` hiện tại có mọi cờ
authorization **false**, không phải release đã duyệt. Không có release đã
xác nhận hoặc budget claim nào được tạo trong công việc này.

Protocol JSON cũ và hash giữ nguyên; field `execution.runner_implemented=false`
là trạng thái **lúc chuẩn bị protocol**. Trạng thái triển khai mới được bổ
sung ở `executor_capability.json`; không sửa contract đã khóa để làm như
executor đã tồn tại trước đó. Preparation-status trước cập nhật cũng được giữ.

## 5. Kiểm tra offline đã thực hiện

**34 executor tests + 6 protocol tests = 40 tests đạt.**

- Fake adapter đi hết 16 slot, kiểm tra ledger đã ghi trước từng lần gọi,
  cold-start label, thứ tự, không gọi lại và không automatic promotion.
- Fault injection cho ordinary failures, native outcome thiếu/sai kiểu,
  rollover, missing stop measurement, nguồn drift trước/sau attempt,
  exception/interrupt và kết quả/measurement thiếu.
- Fake process kiểm tra argv chỉ có một seed/arm, partition riêng, cleanup
  khi interrupt và giữ native failure thu được. Tests cấm Popen/run thật.
- Synthetic artifacts kiểm tra reader cho cả traversal thành công và
  ordinary failure có crossing censored; không dùng trace cũ để test lại.
- Pending/proposed application, release sai số lượt/hash hoặc thiếu xác
  nhận đều không được authorize. Budget claim không được dùng lần hai.
- Chạy CLI mặc định thực sự tạo [offline plan](governor_h2_executor_2026-10-17/offline_plan/summary.json):
  **0 attempted, 0 child processes, 16 unattempted**.
- Validator gốc vẫn đạt **30 frozen files/23 workspace references**; không
  sửa PI/detector/ramp/physics hoặc native/study scores.

Không tuyên bố toàn bộ repository test suite đạt hoặc live integration đã
được xác nhận. Bootstrap/decision engine cuối batch hiện đã được triển khai
ở analyzer riêng theo cập nhật đầu báo cáo; collection của executor vẫn
là `H2_decision:not_assessed` cho đến khi chạy analyzer trên output mới.

## 6. Artifacts và cách kiểm tra

- [Verification](governor_h2_executor_2026-10-17/verification.json).
- [Tests log](governor_h2_executor_2026-10-17/tests.log).
- [Tiêu chí đề xuất chưa áp dụng](governor_h2_executor_2026-10-17/research_criteria_proposal.json).
- [Capability mới](governor_h2_replication_protocol_2026-10-17/executor_capability.json).
- Source/test snapshots, template release và offline ledger nằm cùng thư mục.

Chạy lại tests offline:

```bash
cd ~/ninorobot
.venv/bin/python -m pytest -q \
  src/nino_rl/test/test_governor_h2_executor.py \
  src/nino_rl/test/test_governor_h2_protocol.py
```

Tạo một bản kế hoạch offline vào thư mục **chưa tồn tại**:

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/run_governor_h2_replication.py \
  --protocol docs/governor_h2_replication_protocol_2026-10-17 \
  --output /tmp/nino_h2_offline_plan
```

Không có `--execute` trong lệnh trên. Không cung cấp lệnh launch simulation
ở bước hiện tại vì người dùng chỉ yêu cầu triển khai/kiểm tra offline.
