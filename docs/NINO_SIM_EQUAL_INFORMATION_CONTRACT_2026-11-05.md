# Contract Sim: TD3/cổ điển cùng preview, common-only103D/1D

05/11/2026 · Chuyển [kế hoạch offline](NINO_SIM_EQUAL_INFORMATION_NEXT_2026-11-05.md)
thành config, adapter, Gym wrapper, replay audit và qualification job.
**Phạm vi hiện tại: chỉ kiểm phần mềm, không train/Gazebo/hardware.**

## 1. Remaining gap và quyết định đầu tư

**[N — Sim trước]** Common cổ điển+0,005m/s có tín hiệu tracking ở clear fixture
stop6/8s; chưa có minimum worthwhile effect được chấp nhận. TD3 V3 không có
preview tương ứng và từng học với phạm vi/action/reward khác. Hai batch cũ
không đủ để kết luận thuật toán nào tốt hơn khi cùng thông tin.

**[Đ — giả thuyết, chưa có bằng chứng thắng classical]** Common thay đổi theo
wheel/IMU history có thể bù steady tracking tốt hơn amplitude cố định khi
combined gain/lag thay đổi trong một miền được nhận dạng. Chưa đo/khóa miền
đó; không tự randomize để tạo điểm yếu cho classical. Với clear development
hiện có, chưa chứng minh remaining gap đáng đầu tư learning. Nếu baseline
đáp ứng mục tiêu thì dừng learning cho envelope này.

Primary dự kiến giữ whole-task nominal velocity RMSE14s; path/stop/estimator/
intervention là constraints/secondary, diagnostic GT-header giữ riêng.
Minimum worthwhile effect vẫn **null**, không lấy−23,09%/−13,40% vừa thấy làm
ngưỡng mới. Việc chốt yêu cầu ứng dụng và ngân sách nghiên cứu là hai quyết
định riêng; đây chưa mở ngân sách cho cả hai.

## 2. Luồng điều khiển mới — chưa nối Gazebo trong contract này

```text
Wheel/IMU/source/final/status → pipeline cũ → causal history100D
Reference generator kế hoạch → current plan2D +previous requested scalar
                  ↓ cùng packet103D
       TD3 scalar request / classical request / B0
                  ↓ scalar a∈[−1,1]
       Requested common =0,005a m/s
                  ↓ shared steady/withdrawal/validity window
       Map về proposal2D cũ [common/0,04; 0]
                  ↓ projection/ramp/limits cũ + yaw follower
       Backend velocity reference → wheel PI → Sim
```

Không dùng GT/contact/caster/body speed làm actor input. `BaselineScore` dùng
body GT/estimate cho nhãn/reward trong Sim; không nhét nhãn đó vào preview.
Fixture offline có nhãn tổng hợp, không là estimator đã được xác minh.

## 3. Observation/action ABI mới

ID `nino_equal_information_common_103x1_v1`:

- Giữ100D=20features×5frames causal của pipeline cũ. History span nominal0,4s,
  tick0,1s; schema, scale và missing-history rejection cũ giữ nguyên.
- Nối **2 feature kế hoạch hiện tại +request scalar trước đó**, không lặp
  chúng thành5frame giả: `(planned_stop−decision_time)/14`,
  `common_window_open`0/1 và `previous_requested_scalar`. Countdown rút bù
  suy được từ countdown stop và lead0,5s chung. Request trước đó được biết
  ngay cả khi window đã chặn, để action-change cost không dùng hidden state.
- Clock là episode decision tick từ generator có epoch/protocol, không wall
  clock, GT pose hoặc contact time. Kế hoạch phải được cấp thật; không suy
  obstacle từ tọa độ. Config hiện chỉ development stop6/8s đã xem.
- Cả TD3 và classical được đưa packet103D giống schema/thông tin. Feedback
  từng arm có thể khác theo trajectory: không exact-state counterfactual.
- Common request1D, signed±0,005m/s, differential luôn0; yaw follower vẫn
  hoạt động. Đây là hypothesis common-only mới, không frozen actor V3 mask.
- Shared window chỉ mở khi reference thực nhận forward, nominal shaper đã
  steady0,2m/s, history/owner/sensors/age hợp lệ, chưa fault/latch/done và
  decision<planned_stop−0,5s. Shared window là thành phần của mọi controller.
- Legacy mappings không bị sửa. Trên cùng source/view, classical mới phải
  cho proposal2D khớp rule cũ từng tick.

**Cập nhật sau qualification Gazebo05/11:** fixture yaw0 có source từ0,5s
và nominal steady2,4s →31/51open ticks. Trace Gazebo cũng có source từ0,5s,
nhưng yaw follower nhỏ kết hợp wheel-ramp làm nominal v tại2,4s chưa đạt
0,2m/s trong tolerance1e−8; window mở2,5s →30/50ticks. Diễn giải trước đây
rằng source Gazebo muộn một tick là sai; xem báo cáo qualification Gazebo.
Kiểm theo cùng input/nominal semantics, không ép count hoặc thêm delay giả.

## 4. Replay và reward

Replay mới lưu `(obs103, requested_action1, reward, next_obs103, done, timeout)`.
Trace giữ `requested_scalar_action`, `requested_common_m_s`,
`controller_proposal`2D sau window và inherited accepted/final/target riêng.
Closed window không được thay action requested bằng0 trong replay.

Reward nominal velocity/yaw giữ scales0,2m/s và0,5rad/s; action size/change
phạt **request vật lý theo scale0,04m/s**, tức q=0,125a, kể cả window chặn.
Không phạt a=1 như thể request0,04m/s, vì đổi range sẽ vô tình tăng penalty
64lần ở cùng physical request. Đây là task/reward identity mới; reward không
thay primary hoặc được dùng như bằng chứng lợi ích vật lý.

Fixed task deadline14s là terminal success/failure; external early timeout
là truncation với next observation thuộc continuing state để bootstrap.
Không đóng window trong next observation chỉ vì external timeout. Reset
xóa history, nominal shaper, previous request và clock; không carry giữa run.

## 5. Checkpoint và ngân sách

- ABI/task/reward/plan/fingerprint mới, reject V3/Studio100D/2D và bản đổi
  scale/preview/limits. Không resume checkpoint cũ hoặc convert bare actor.
- Offline chỉ tạo model103D/1D **chưa học**, head actor zero và target đồng
  bộ, save/load model/target/critics, optimizer state rỗng. MLP32²/buffer512
  là inspection fixture, chưa là research hyperparameters.
- File `inspection_model_untrained.zip` và `synthetic_replay_do_not_train.pkl`
  là artifact kiểm phần mềm; không checkpoint train/resume hoặc dataset Sim
  vật lý. GUI train V3 hiện có không được coi là trainer của ABI mới.
- Tối đa840 synthetic fixture transitions=stop6/8×B0/classical/proposal probe
  ×140. **Training transitions0, optimizer0, Gazebo0, physics0, hardware0.**
  Các lượt unit tests tách riêng, không cộng thành physics/evaluation samples.
- Root `~/nino_research/sim_equal_information_v1`, một qualification job có
  ledger/hash/dependency và wall deadline180s; failure giữ raw, không retry.

## 6. Acceptance offline và bước sau

Đạt offline khi103D/1D đúng; plan causal/source sync; shared mapping/gates và
nominal scorer khớp; replay giữ requested action/terminal/truncation; actor
zero/targets/critics save-load khớp và optimizer không chạy. Regression không
được sửa frozen parent chỉ để contract mới đạt.

Đạt offline **chưa mở train**. Các gate còn lại được hiển thị trong GUI:

1. Xác định remaining gap/điều kiện nào cần adaptive common thay fixed rule.
2. Chốt objective/meaningful effect và constraints trước outcomes mới.
3. Protocol qualification wrapper mới trong Gazebo bằng B0/cổ điển/probe
   có cùng schedule; số lượt/physics budget mới cần chốt riêng.
4. Chọn research profile/normalization/replay/checkpoint identity mới; dự kiến
   nhiều training seeds (catalog đề xuất11/22/33), timesteps/seed vẫn null.
5. Chốt train/validation/test splits toàn run/condition và final test budget.
   Stop6/8 đã xem là development, không đổi tên thành unseen bank.

Gate không có bằng chứng thì giữ unknown. Không tune trên test hoặc thêm
mẫu sau kết quả. Không có gap →giữ B0/classical Sim candidate, chuyển công
sức sang model discrepancy/operating envelope. Contact H2/real deployment
vẫn là nhánh riêng; dữ liệu thật chưa là prerequisite cho contract offline.
