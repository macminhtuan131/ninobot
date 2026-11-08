> **Mới nhất:** [common cổ điển đã xong6/6](NINO_SIM_CLASSICAL_COMMON_RESULT_2026-11-05.md), whole-task velocity tracking tốt hơn hai đối chứng trong batch, chưa promote. Tiếp [stop-time transfer6s](NINO_SIM_STOP_SCHEDULE_TRANSFER_NEXT_2026-11-05.md), chưa chạy.

> **Cập nhật mới nhất:** [ablation frozen đã đóng6/6](NINO_SIM_AXIS_ABLATION_RESULT_2026-11-05.md). Bước tiếp là [draft common cổ điển/planned stop](NINO_SIM_CLASSICAL_COMMON_NEXT_PROTOCOL_2026-11-05.md), chưa chạy; giữ guided B0 và chưa mở train mới.

# Bước tiếp nhánh Sim sau baseline V3

05/11/2026. **Cập nhật sau chạy: bước 1 đã hoàn tất [4/4 lượt](NINO_SIM_GUIDED_CONTACT_RESULT_2026-11-05.md). Bước 2–3 cũng đã triển khai/chạy trong [pilot TD3 V3](NINO_SIM_GUIDED_TD3_V3_RESULT_2026-11-05.md); chưa promote.**
Baseline clear floor đã [chạy và được kiểm](NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md).
Các bước dưới đây không cần real dataset. Calibration/deployment thật là gate riêng.

## 1. Screen baseline guided khi tiếp xúc — làm trước learning

**Câu hỏi:** wheel+IMU estimate và follower còn đủ dùng khi gặp gờ cứng
6 mm, hay wheel slip/gyro/initial-state/contact gây sai reference trước
khi residual có thể hữu ích?

- Protocol/root/module mới; giữ nguyên V3 clear và các batch lịch sử.
- **Tối đa 4 lượt**: guided residual-zero trên clear box và single capsule
  6 mm, mỗi điều kiện hai fresh launches, thứ tự clear/gờ/gờ/clear.
  Dùng lại controlled world đã tạo trong V2, lưu SDF/hash/pose gờ cụ thể
  vào manifest trước chạy; không gọi nó là full mixed factory map.
- Tuyến thẳng yaw 0, robot spawn yaw 0; initial estimate theo metadata.
  Đây là baseline contact screen, không phải lặp lại thử heading ±5°.
- Giữ cruise 0,2 m/s, shaping/PI/geometry, source 0,5–8 s, task 14 s,
  140 tick/lượt; tổng tối đa 560 evaluation transitions, optimizer 0.
- Giữ acquisition/causal support và source/fault rules V3. GT/contact chỉ
  đánh giá; actor và governor không hoạt động trong screen này.
- Primary: hoàn thành progress marker + quiet stop. Gate diagnostic giữ
  max cross-track 40 mm, max estimate position error 50 mm/yaw 0,05 rad
  như V3, ghi rõ chúng là đề xuất kỹ thuật. Secondary: body/reference
  tracking, drift trước/sau contact và source/accepted/final/target.
- Giữ tất cả failures/spikes. Contact manifold chỉ giúp chia phase, không
  là force/load hoặc xác nhận first loaded contact. Chưa đánh giá impact
  quality/slip benefit nếu chưa có metric/coverage contract tương ứng.
- Fail physics/source/pose/guidance → đóng batch, không tự retry/thêm mẫu.
  Nếu outcome khác giữa hai lượt hoặc sampling-sensitive → unknown,
  không lấy trung bình để giấu failure. Tối đa một correction có căn cứ
  theo protocol mới; không sửa gate sau khi thấy dữ liệu.

**Qua:** baseline có thể dùng làm đối chứng nghiên cứu trong envelope sim
hẹp đó. **Không qua:** khoanh estimator/actuator/contact discrepancy, giữ
clear floor nếu cần; chưa mở tăng ngân sách train để sửa nền móng.

## 2. Contract TD3 V3 — tách path guidance khỏi residual velocity

Chốt code/config/hash trước optimizer:

1. B0 = cùng estimator + follower + projection/PI, residual zero. B1 cổ điển
   chỉ thêm khi có câu hỏi tuning cụ thể; không dùng constant straight làm
   đối chứng chính cho policy có follower.
2. Residual vẫn common/differential wheel-linear m/s theo ABI hiện có,
   history h5/normalization vật lý và limits sim giữ nguyên. Không đổi
   đồng thời history 8, reward, action và dynamics trong một pilot.
3. Actor TD3 mới, **đầu output khởi tạo zero**, target actor đồng bộ;
   deterministic action phải bằng zero trước optimizer trên fixture hợp lệ.
   Replay/optimizer không resume từ V2. Cùng observation ABI không đủ
   tương thích baseline/task/normalization/checkpoint distribution.
4. Reward bám **nominal baseline đã shaping độc lập với residual trực tiếp**
   cho v và yaw rate; không thưởng tổng progress hoặc so body với lệnh đã
   bị chính residual thay đổi để tự giảm error. Follower vẫn phụ thuộc pose
   của trajectory đang chạy: không gọi nominal này là counterfactual
   trajectory bất biến. Đánh giá path/time/task riêng để phát hiện reward
   gaming và policy làm baseline đổi theo đường đi.
5. Requested proposal, projected contribution, accepted reference, ROS
   final và actuator target readback phải tách riêng. Replay lưu action
   actor đã chọn với ngữ nghĩa cố định; không thay bằng action sau projection.
6. Warmup/history invalid, permission/source fault, baseline zero và
   stopping dùng cùng logic cho cả B0/TD3. Deadline task 14 s là true terminal;
   không bootstrap từ deadline failure. Lưu failure và reason.
7. Pin seed, library/runtime, ABI + baseline + estimator + task + reward
   hashes, manifest checkpoint và source trước train. Kiểm save/load actor
   và target/optimizer, zero-init, causal history và action semantics offline.

Các mục này đã được triển khai ở `guided_td3_contract.py` và `residual_guided_td3.py`, có checks offline, optimizer/replay/save-load thật. TD3 V1/V2 và smoke cũ giữ nguyên; checkpoint V3 chưa promote.

## 3. Pilot learning sau contract

Một pilot mới phải có số transition/seed/evaluation cố định trước chạy,
root mới và đối chứng guided B0 hiện hành; không tăng ngân sách tự động khi
return đẹp. Tối thiểu báo cáo path/reference tracking, stop/failures,
progress/time, projection/intervention và bias reference trước contact.

Chỉ pilot tích hợp chưa đủ kết luận hội tụ hoặc thắng baseline. Sau khi
pilot chứng minh luồng optimizer/checkpoint/evaluator đúng mới thiết kế
multi-seed comparison và ablation history. Effect nhỏ/đổi chiều theo grid
thì unknown; không đổi objective, loại spike hoặc mở thêm mẫu sau kết quả.

**Ưu tiên hiện tại:** giữ B0 clear; [ablation frozen full/common-only/B0](NINO_SIM_AXIS_ABLATION_RESULT_2026-11-05.md) đã đóng đủ6 lượt/optimizer0. Common-only giảm lệch đường nhưng chưa thắng B0 toàn task. Bước tiếp đề xuất: bù common cổ điển có rút trước known stop theo protocol mới, chưa chạy. Không tự mở train dài hoặc gộp các batch trước.
