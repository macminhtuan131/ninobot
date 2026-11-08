> Cập nhật06/11: đã triển khai và mở pilot riêng theo protocol05/11; đợt đóng sau700train ticks seed11/636critic updates vì joint support50ms ở half-tick zero episode6. Seed22/33 và10eval chưa chạy, đóng toàn bộ. Bản draft bên dưới giữ làm lịch sử; xem [kết quả partial](NINO_SIM_COMMON_TD3_RESULT_2026-11-06.md).

# Dự thảo learner pilot kế tiếp: TD3 common-only103D/1D

05/11/2026 · **Chưa triển khai/chạy hoặc mở training budget.** Chỉ xét sau
qualification Gazebo103D/1D đạt. Không cần chờ real data hoặc một bộ yêu cầu
nhà máy hoàn chỉnh để thiết kế bounded Sim pilot; không gọi gate phần mềm
là lợi ích ứng dụng hoặc dùng unknown objective để cấm mọi nghiên cứu Sim.

## 1. Câu hỏi và remaining gap

**Câu hỏi pilot:** sau khi được cấp cùng plan preview/window, một learner
scalar mới có học được hành vi hữu hạn, hợp lệ và tránh suy giảm tracking/
stop/path so B0 và candidate cổ điển trong development clear6/8s không?
Đây là pilot khả thi của learner/task mới, không kết luận common adaptation
cần thiết hoặc đủ mạnh cho vật cản. Không train tiếp checkpoint V3.

Gap ứng dụng hiện chưa được chứng minh: common cố định đã tốt trong hai
lịch dừng đã xem. Giả thuyết adaptive common hữu ích khi gain/lag thay đổi
cần miền uncertainty có căn cứ riêng; không tạo DR tùy ý để baseline thua.
Không có gap đáng quan tâm sau pilot →dừng tăng ngân sách cho envelope này.

## 2. Ngân sách đề xuất cần chốt trong protocol khi triển khai

-3 independent learner seeds11/22/33, **1.024 train transitions/seed**,
  tổng3.072; mỗi model/replay/optimizer tách riêng. Hơn pilot cũ512 nhưng
  vẫn chỉ khoảng7full episodes +44steps cắt phải/seed; không gọi hội tụ.
- Train source stop6/8 luân phiên theo episode, horizon140ticks/14s,
  bắt đầu6s; ghi episode/schedule/censoring. Cuối budget giữ đoạn cắt phải,
  không biến thành terminal hoặc xóa transition, không tự thêm episode.
- Evaluation tối đa10fresh launches/1.400ticks:
  B0+classical mỗi stop6/8 (4launches),3frozen learners mỗi stop6/8
  (6launches). Thứ tự/block cụ thể phải chốt trước train; không chọn seed
  hoặc checkpoint đẹp từ test. Không inference noise trong evaluation.
- Tổngphysics/control transitions tối đa4.472 cho budget đề xuất; không
  smoke launch hoặc train riêng ngoài ledger. Wall deadline phải dựa trên
  throughput đo từ qualification, chốt hữu hạn trước job.

Ba learner seeds là ba lần khởi tạo/học, không ba lần thay seed đánh giá của
cùng model. Fresh Gazebo launch không bảo đảm exact-state hoặc independent
physics RNG. Stop6/8 và clear đã xem là **development**, không unseen bank.

## 3. Learner/task contract

- Reuse frozen103D/1D controller schema/window/projection và nominal reward.
  Lập learner/task/checkpoint identity mới ghi parent ABI/qualification và
  release riêng. `training_released=false` trong parent là hồ sơ offline
  cũ, không tự sửa parent thànhtrue hoặc coi parent cấp budget cho trainer.
- New model tạo trực tiếp với environment103D/1D đã qualify; không dùng
  factory trainer100D/2D hoặc `inspection_model_untrained.zip` làm model
  research. Actor scalar head zero +target sync; optimizer/critic/replay mới.
  Zero head không làm random warmup/exploration thành zero.
- Profile đề xuất cho bounded pilot: CPU MLP32², LR3e−4, gamma0,99,
  tau0,005, batch32, replay8.192, warmup64, train_freq1/gradient_steps1,
  policy_delay2, target noise0,2/clip0,5 và exploration sigma0,1 scalar.
  Đây là small-pilot proposal, chưa tối ưu hoặc xác nhận convergence;
  sigma0,1 tương ứng requested common0,0005m/s trước gate/projection.
- Giữ common±0,005m/s, diff0 và yaw follower. Reward cost dựa request vật
  lý scale0,04m/s như sealed contract; không tune reward sau nhìn kết quả.
- Replay giữ obs103/request1D/nextobs103/reward/terminal/truncation, cùng
  requested/mapped/accepted trace. Không lấy teleop hoặc probe replay làm
  data TD3, không thay requested bằng accepted sau projection.
- Checkpoint đầy đủ model/targets/critics/optimizer/replay/config/runtime/
  ABI/normalization/plan/baseline/reward identity. Chọn checkpoint cuối mỗi
  seed theo budget, không pick theo evaluation return. Save-load parity kiểm
  offline trên observations đã thu, không thêm physics để test reload.
- Pilot đầu fresh từng seed, không resume V3/Studio/inspection/probe. Nếu
  muốn resume sau này phải chốt new episode/clock/censoring và budget riêng;
  không giả snapshot/restore Gazebo/RNG đã có.

## 4. Metric và điểm dừng trước khi release

Primary dự kiến whole-task nominal velocity RMSE/native100ms; GT-header20ms/
dịch10ms diagnostic giữ riêng, không nội suy body. Path/estimate/quiet stop/
interventions và time constraints giữ explicit. Minimum worthwhile effect
vẫn **null**; có thể đề xuất engineering criterion tạm cho research trong
protocol mới nhưng không coi là factory/deployment acceptance.

- Software pass: có critic/actor updates hữu hạn, replay đúng semantics,
  target/optimizer/save-load khớp và action/feature/clock hợp lệ.
- Feasibility: không physical/source/guidance failure, task/stop/engineering
  bounds đạt. Một failure giữ raw và dừng stage/đóng slot còn lại; không
  chạy bù seed, thêm mẫu hoặc train dài để che lỗi.
- Quality: report từng learner/condition so cả B0 và classical; reward đẹp
  không thay tracking. Effect nhỏ/đảo chiều theo grid hoặc trade-off chưa
  có objective →unknown, không promote. Không suy learned benefit nếu chỉ
  bắt chước amplitude cố định hoặc chỉ thắng B0 mà thua classical.
- Tối đa một correction có nguyên nhân rõ, contract mới trước khi quyết
  định dừng/chuyển. Không tạo vòng tiny train→tune→test vô hạn.

Kết quả tốt chỉ cho phép chốt benchmark/held-out conditions tiếp theo; chưa
PPO/history ablation/DR scale-up hoặc hardware residual. Có thể giữ classical
làm sản phẩm Sim tối giản nếu learner không đem lại value cần thiết.
