# Protocol trước chạy — TD3 V3 guided tracking/stop

05/11/2026. Người dùng yêu cầu tiếp tục nhánh sim. Thực thi một pilot hữu hạn
sau guided baseline [clear ±5°](NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md)
và [clear/gờ 6 mm](NINO_SIM_GUIDED_CONTACT_RESULT_2026-11-05.md) đã qua gate.
Không hardware hoặc real data mới. Không sửa parent/checkpoint V1/V2.

## Câu hỏi và ba stage

1. `sim-v3-contract`: offline, không reset/step physics/optimizer. Tạo TD3
   mới, zero final Linear actor, sync target; kiểm 12 input100D, critic giữ
   nguyên, deterministic zero, portable actor và save/load identity.
2. `sim-v3-train`: **512 transition**, một seed7, train trên controlled
   single cylinder Ø6 mm x0,65 m của factory hall. Bốn episode allocations,
   140 tick/episode; đoạn cuối có thể right-censored do hết ngân sách train,
   không gọi nó là task success/failure tại14 s. Early physical/source fault
   đóng job, giữ partial model/replay, không retry.
3. `sim-v3-evaluate`: **8 fresh launches / tối đa1.120 tick**:
   B0/TD3 × clear/gờ6mm ×2, thứ tự khóa trong YAML. Không exploration,
   không optimizer. Đây là scenario đã thấy, không held-out test bank.

Root mới `~/nino_research/sim_guided_td3_v3`. Mỗi stage chỉ tiêu thụ một lần,
kể cả failure. Wall deadline1.800 s/stage. Không tự thêm seed, transition,
lượt smoke hoặc sample. Source/contract fingerprint và manifest dependency
phải hợp lệ trước mỗi stage.

## Giữ cố định và điều thay đổi

Giữ Nino/caster, PI, physics1ms, policy/scoring100ms, historyh5/100D,
normalization vật lý, action common/diff wheel-linear, limits/projection
và causal wheel+gyro-Z estimator/follower parent. Robot/tuyến yaw0, path3m,
cruise0,2m/s; source0,5–8s, task14s gồm6s pha dừng. Initial estimate0 là
metadata; không align theo GT sau settling. GT chỉ reset/reward/evaluation.

Simulation residual authority1 trong envelope sim hiện có; hardware0.
Guided B0 dùng cùng đường reference với proposalzero. Không dùng constant
straight làm đối chứng chính và không đồng thời đổi history/hyperparameter.

TD3 dùng profile smokeh5 hiện có: LR chung0,0003; batch32; buffer2048;
learning_starts16; architecture[32,32]; gamma0,99; tau0,005; delay2;
target noise0,2/clip0,5; exploration sigma0,1; train_freq/gradient_steps1.
Dự kiến496 critic updates; một seed không chứng minh hội tụ/độ ổn định.
Zero-init chỉ là deterministic actor trước optimizer: SB3 warmup16 bước
chọn action uniform và các bước train có exploration, không giả vờ tất cả
action đầu đều zero hoặc bằng deployment action.

## Reward và ngữ nghĩa transition

Nominal reference có shaper riêng, nhận **baseline follower trước residual**
của trajectory hiện tại. Không dùng accepted reference do actor thay đổi
làm target. Follower vẫn phụ thuộc estimated pose của trajectory đó, không
là counterfactual trajectory bất biến.

Mỗi100ms:

`r = −[(e_v/0.2)² + (e_w/0.5)² +0.01||a||²]dt −0.001||a−a_prev||²/dt`.

Physical/permission failure thêm−10. Deadline14s thêm−5 nếu chưa marker,
−10 nếu chưa stop2s. Không thưởng progress tích lũy. Deadline success/fail
là true terminal, không TimeLimit timeout để bootstrap. Raw pose/contact
không vào actor; reward là sim label, không là slip/impact/hardware claim.

Replay lưu **normalized policy proposal đã chọn**, gồm warmup/exploration,
không thay bằng delta sau projection. Requested, projected, accepted, ROS
final và actuator target readback giữ riêng. Kiểm toàn bộ512 rows cho
obs/action/reward/next-obs/done/timeout; lưu terminal observation trước
auto-reset. Save/load phải giữ actor/target, twin critics/target, optimizer
và replay. Fresh actor không resume replay/optimizer/checkpointV2.

Checkpoint identity kiểm thêm task/reward/baseline/guidance/estimator và
source hashes ngoài observation ABI. Cùng100D không đủ để load checkpoint.

## Metric, dừng và diễn giải

Primary: body velocity/yaw RMSE so nominal, path cross-track; mỗi lượt giữ
marker/quiet stop, source/pose age, estimate error, projection và bias yaw
ở cửa sổ taskt<3,5s. Cửa sổ đó là diagnostic định trước, không khẳng định
first loaded contact. Cùng score/penalty cho B0 và TD3. Giữ gate engineering
parent40mm path/50mm estimate/0,05rad và stop2s, chưa là factory acceptance.

Đánh giá đủ8 nếu không physical/source/guidance fault. Functional miss
được giữ trong bảng và chặn promote; không bỏ failures hoặc đổi gate.
Hai fresh launches/arm/scene không exact-state pairing hoặc nhiều training
seed. Mean/range chỉ mô tả; chưa có minimum effect được chấp nhận, không
CI/power/generalization claim. Không tự chọn checkpoint qua return hoặc
tăng budget sau kết quả. Nếu bias hoặc tracking xấu hơn guided B0, giữ B0
và khoanh action/reward/critic trước khi mở experiment khác.
