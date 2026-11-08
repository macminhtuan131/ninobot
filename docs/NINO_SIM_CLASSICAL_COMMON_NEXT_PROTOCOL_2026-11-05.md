# Protocol Sim: đối chứng common cổ điển và lịch dừng

05/11/2026 · **Đã chốt trước chạy theo yêu cầu tiếp tục nhánh Sim: tối đa6 lượt/840 ticks; không optimizer/hardware.**
Đây là bước tiếp sau [frozen-axis ablation](NINO_SIM_AXIS_ABLATION_RESULT_2026-11-05.md),
không phải continuation/resume các batch đã đóng.

## Câu hỏi duy nhất

Một bù common cố định, rút trước planned stop, có giảm whole-task velocity
error mà giữ path/stop tốt như B0 không? Nếu có, chưa cần học một actor chỉ
để bù steady offset. Không kiểm contact adaptation trong batch này.

## Thiết kế hữu hạn đề xuất

- Root/module/protocol/hash mới; **3 arms × 2 fresh launches = tối đa 6**, 840
  evaluation ticks; optimizer/training/hardware 0.
- A: guided B0 hiện hành, residual zero.
- B: common cố định **+0,005 m/s** (normalized common +0,125 theo scale
  0,04 m/s), diff 0; chỉ khi nominal đã đạt steady 0,2 m/s và nguồn còn tiến.
  Rút proposal về zero từ task **7,5 s**, trước source stop 8 s.
- C: frozen V3 common-only hiện hành, làm đối chứng mechanism; raw/masked
  action riêng, cùng checkpoint pin; không xuất replay TD3 từ masked action.
- Thứ tự A/B/C/C/B/A; giữ clear box, yaw 0, estimator/follower/PI, source
  0,5–8 s, 14 s task, history h5 và all limits. Không tune gain/current.

+0,005 là candidate phát triển từ bias steady B0 khoảng −0,005 m/s trong
batch đã xem; không là giá trị tối ưu hoặc safe envelope hardware. Rút sớm
0,5 s cho năm decision ticks, dài hơn thời gian lý tưởng 0,005/0,1 = 0,05 s
để rút phần bù dưới ramp hiện hành; không bảo đảm body settling trong 0,05 s.
Không sửa acceleration bound, ép reference xuống tức thì hoặc cộng lệnh
ngoài projection. Lịch dừng được biết trước; **không áp claim này cho vật cản
chưa biết hoặc first-contact governor**.

## Trước physics

Một adapter triển khai duy nhất cho rule B; kiểm boundary trước/sau steady,
7,5 s, source zero, invalid history/source và termination. Trace phải giữ
requested compensation, normalized proposal, projected reference, final ROS
và simulated target readback. Identity mới phải ghi rule/time/amplitude;
không thay source của actor V3 hoặc shaper cũ.

Triển khai tại `residual_classical_common.py`, YAML `residual_classical_common_v1.yaml`.
Rule dùng decision clock `step × 0,1 s`, baseline/permission/freshness/history
hiện có và một zero-residual nominal shaper độc lập; không đọc outcome/GT
để chọn action. Nominal shaper được kiểm khớp từng tick với scorer sau bước;
không lấy future observation. Compensation đi qua projection cũ, không sửa
gain/limit. Một ledger `running` được ghi trước launch đầu để fail-closed
nếu process bị ngắt; root có ledger không được mở lại.

Thứ tự chốt: B0/Classical/TD3-common/TD3-common/Classical/B0. Checkpoint pin
V3 `20261105T022329071579Z_sim-v3-train`, manifest SHA256
`8cc9cbeafeea220074638185535d7a23d6a84156424b2e2a8f656414c6e71578`;
parent ablation fingerprint `1c7111598ad1460036ce6e9a132be4e2854beedbd5125051ea40e4611b408266`.

Kiểm chính xác amplitude/ramp/ownership, checkpoint hash và finite budget;
quá deadline/physics/source/guidance failure đóng batch, giữ slot còn lại
chưa dùng; không retry. Chốt contract trước launch đầu.

## Metric và điểm dừng

- Primary giữ **RMSE body v so nominal shaped reference toàn 14 s**.
- Constraints giữ marker0,95m + quiet stop2s, maxpath40mm, estimate50mm /
  yaw0,05rad là engineering bounds đề xuất; báo path RMSE riêng. Không gọi
  chúng là yêu cầu ứng dụng được chấp nhận.
- Secondary: steady/deceleration RMSE và signed bias; accepted compensation,
  saturation/projection, time/progress và source integrity.
- So từng fresh launch, không ghép exact-state hoặc tính CI giả chính xác.
  Candidate B có cả hai whole-task RMSE thấp hơn cả hai A và C, không mất
  path/stop constraint → tín hiệu mô tả ủng hộ baseline cổ điển. Minimum
  worthwhile effect vẫn null; chưa promote triển khai hoặc công bố benefit.
- B không tốt hơn / effect nhỏ hoặc đổi chiều → giữ B0; không mở thêm seed
  hoặc train TD3 tự động. Không thay primary bằng steady-only sau kết quả.
- Tối đa một correction có nguyên nhân cụ thể qua contract mới; không thêm
  nhiều amplitude/withdrawal times để tìm kết quả đẹp trong cùng batch.

Đây là **development scenario đã xem**, không held-out test bank. Chỉ khi có
remaining gap và cơ chế cần learning mới so actor common-only được train
mới, nhiều seed và history ablation trong ngân sách riêng. Dữ liệu robot thật
không là prerequisite của bước Sim này; calibration/deployment vẫn gate riêng.
