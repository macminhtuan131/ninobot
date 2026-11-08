# Protocol: fresh TD3 common-only 103D/1D — 05/11/2026

## Release và câu hỏi

Đã được người dùng yêu cầu tiếp tục nhánh Sim. Release riêng **một pilot**
`sim-common-td3`, root `~/nino_research/sim_common_td3_v1`; không hardware.
Parent qualification Gazebo 4/4 đã đạt. Không sửa parent có trường lịch sử
`training_released=false`; learner mới có identity/release riêng.

Câu hỏi: learner scalar có học hữu hạn, đúng contract và đáp ứng task/path/
stop trên hai lịch dừng development hay không? Có cải thiện tracking vượt
B0 **và** common cổ điển không? Pilot không chứng minh hội tụ hoặc sim-to-real.

## Budget khóa trước chạy

- Learner seeds độc lập 11 →22 →33, 1.024 transition/model, tổng3.072.
- Episode140ticks/14s, source stop6/8 xen kẽ bắt đầu6, mỗi seed8episodes:
  7episode đủ140 +episode cuối44ticks cắt phải; giữ đoạn cuối, không ép terminal.
- Backend reset hiện là fresh Gazebo launch, không snapshot. Tối đa24train
  launches +10evaluation launches =34; không thêm launch smoke.
- Eval thứ tự cố định: B0/6; TD3-11/6; classical/8; TD3-22/8; TD3-33/6;
  classical/6; TD3-11/8; B0/8; TD3-22/6; TD3-33/8.
- Eval140ticks/lượt, tối đa1.400; tổng **4.472control transitions**.
  Setup zero-settling/initial pause/physics requests giữ ledger riêng,
  không gọi control transitions là toàn bộ physics requests hoặc physics steps.
- Wall deadline5.400s: qualification trước560ticks mất179,4s; dư cho optimizer,
  34launch/reset và I/O. Đây là giới hạn đóng job, không thời gian được bảo đảm.
- Một root chỉ tiêu thụ một lần. Lỗi/hủy đóng các seed/lượt chưa chạy,
  giữ partialmodel/replay/raw; không retry hoặc thêm budget.

## Model và controller bất biến

- Clear box, cruise0,2m/s, yaw follower, physics/PI/estimator/guidance giống parent.
- H5/100D +countdown/window/previous requested scalar =103D. Scalar request
  ±1 →common±0,005m/s →shared window →mapped2D(common/.04,0) →projection/PI.
- Không đọc GT/contact/caster vào actor/guidance. GT được dùng cho reward,
  audit và gate, độc lập với input deployable.
- MLP32²/CPU, LR0,0003; gamma0,99; tau0,005; batch32; buffer8192;
  warmup64; train_freq1; gradient_steps1; policy_delay2;
  target noise0,2/clip0,5; explorationGaussian sigma0,1 scalar.
- Fresh zero actor head +target sync; critics/optimizers/replay mới. Warmup/
  exploration vẫn có nonzero request. Expected960criticupdates/seed, kiểm thực tế.
- Reward nominal tracking độc lập và action cost vật lý theo frozen parent;
  không tune reward/gain/limits sau kết quả. Checkpoint cuối budget mỗi seed,
  không chọn seed/checkpoint theo eval. No resume V3/Studio/inspection.
- Bundle model+targets+critics+optimizer+replay+identity/config/runtime/hash.
  Save-load kiểm trên observations đã thu, không thêm physics. Không khẳng
  định RNG hoặc trạng thái vật lý có thể resume chính xác.

## Gate và estimand

1. Mỗi tick kiểm obs103/request1D/mapping, previous request, task/source clock,
   nominal/reward parity và replay semantics. Verify **trước** trả terminal
   cho SB3 để không auto-reset sang episode mới sau failure.
2. Native boundary support≤40ms; finite reward/observation/model/loss/gradient;
   không physical intervention/guidance fault. Path maximum≤40mm,
   estimator position≤50mm, estimator yaw≤0,05rad là engineering proposals
   kế thừa, không factory acceptance. Full episode phải đạt marker0,95m +quietstop2s.
3. Replay đúng1.024rows/seed, target/optimizer/model parity; expected960updates,
   actor thay đổi hữu hạn. Chỉ tiến sang seed/eval tiếp khi đạt.
4. Eval toàn140ticks +GT-header20ms và dịch10ms: latest support, không nội suy
   body; diagnostic invalid đóng slot còn lại. Native giữ primary riêng.
5. Primary descriptive: nominal velocity RMSE toàn14s, chênh từng seed theo
   stop so B0 và classical cùng stop. Báo cả yaw/path/stop/reference intervention
   và sampling sensitivity. Không bootstrap CI hoặc coi seeds là exact-state pairs.
6. Minimum worthwhile effect **null**. Mức nhỏ/đảo dấu theo grid hoặc chỉ thắng
   B0 nhưng thua classical →unknown về learned benefit; không promote/scaleup.

## Điểm dừng

Sau đủ budget, khóa checkpoint/result. Nếu không có giá trị vượt classical,
ưu tiên giữ classical làm benchmark tối giản; không tự train dài, thêm DR,
PPO/history ablation, hoặc đưa residual lên robot. Mọi correction cần nguyên
nhân rõ và protocol mới; tối đa một correction trước quyết định đổi hướng.

Offline tests (fixture/model serialization) không phải rollout Gazebo hoặc
bằng chứng motion. GUI profile mới tách riêng TRAIN TD3 tự do100D/2D.
