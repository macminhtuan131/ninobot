# Protocol zero-only: hai observer kiểm joint ở biên physics

06/11/2026 · `sim-joint-boundary` · root `~/nino_research/sim_joint_boundary_v1`.
Được triển khai theo yêu cầu tiếp tục nhánh Sim. Đây là budget diagnostic mới;
không mở lại partial TD3/seed22/33 hoặc các slot evaluation đã đóng.

## 1. Câu hỏi và nguồn

Khi joint thiếu support sau một physics chunk, observer ROS độc lập có nhận
mẫu mà primary thiếu không? Nếu cả hai thiếu, chưa tách source publication
và shared DDS delivery nếu không có counter upstream. Không sửa broadcaster,
controller/gain/reward/feature schema để thực hiện diagnostic này.

Pin failed parent common TD3 manifest SHA256:
`09f7c044e93b5b22990d9a497b77b31cc790ca6441c5ff6e5264004b841b8663`.
Failed parent700transitions/636criticupdates giữ nguyên77files.

Wiring đọc từ workspace: joint_state_broadcaster500Hz → `/joint_states`
→ primary BestEffort/depth100/SingleThreadedExecutor. Không qua Gazebo
parameter_bridge; IMU/GT dùng các channel riêng. Không sửa bridge theo phỏng đoán.

## 2. Budget trước chạy

- Tối đa2fresh launches, mỗi launch100native ticks×100ms =10simulation seconds.
  Tổng tối đa200complete control ticks; physics1ms, hai chunks50steps/tick.
- Source/reference **zero toàn phiên**, bao gồm setup settling. Không actor,
  optimizer, checkpoint, training transition hoặc hardware. Cùng clear-box
  Nino model/PI/geometry/contact/estimator/subscriptions từ parent.
- Setup zero-settle0,5s liên tục/tối đa5sim seconds kế thừa. Free startup,
  setup requests và incomplete chunk giữ riêng trong ledger, không gọi200ticks
  là tổng physics requests/iterations của mọi startup.
- Observer IPC ready≤15wall seconds; feedbackdeadline5s, IPC response grace1s;
  toàn job≤1200wall seconds gồm tối đa2×330s startup +setup/control/shutdown.
- Một lỗi support/physical/source/IPC/closure: đóng lượt và slot chưa chạy,
  giữ raw/log/manifest. Không retryphysics, tăng sample hoặc hạ40ms.
- Software fixture với20synthetic ROS JointState/domain139 trước chạy không
  Gazebo/motor/physics; không là measurement readiness của diagnostic thật.

## 3. Instrumentation và các khác biệt có chủ ý

Primary là subclass của frozen GuidedBackend, thêm counter nội bộ/source
stamp/receipt monotonic/hash canonical các field JointState. Hash của
**reserialized CDR** chỉ giữ diagnostic; fixture phát hiện hash này không ổn
định giữa process nên không dùng làm payload-parity gate hoặc gọi raw-wire CDR. Process phụ chỉ nhận `/joint_states`, không contact
conversion hoặc command publisher; cùng BestEffort/depth100, domain129/local.

Tại mỗi `_wait_feedback`, gửi IPC snapshot cho process phụ đồng thời với
primary wait: cùngtargetstamp,40ms và5s deadline. Log count/last source/receipt
trước/sau, response ACK, source age, primary processingstamp, error và cutoff.
Không dùng dữ liệu observer phụ để vá primary, không nội suy hoặc lấy mẫu tương lai.
Trước control log publisher identity/GID/QoS. Internal receive sequence không
là counter publication upstream; mất mẫu không tự suy từ chênh count đầu/cuối.

Primary vẫn yêu cầu đủ IMU/wheel/GT/drive. 100ticks thường có300feedbackchecks
(2half boundaries và1final check/tick), setup/final-reset checks giữ riêng.
Không cộng duplicate checks thành independent trials.

Instrumentation có overhead thêm; diagnostic không có TD3 optimization load.
Do đó clean2launches không chứng minh training acquisition loss-free. Không
giả đã tái tạo chính xác load/timing của failed parent.

## 4. Phân loại, metric và gate

| Primary joint | Independent joint | Diễn giải được phép |
|---|---|---|
| đủ | đủ | joint endpoint đủ ở lần check đó; lỗi channel khác report riêng |
| thiếu | đủ | khoanh vùng delivery/consumer primary; không suy riêng executor là nguyên nhân |
| đủ | thiếu | khoanh vùng đường observer phụ/instrumentation, chưa quy source |
| thiếu | thiếu | source/shared delivery chưa phân biệt; cần upstream counter nếu muốn tách |

Nếu cả2launches đủ100ticks: `not_reproduced_unknown`, rootcauseunknown,
training_releasedfalse. Không có correction chỉ để “chọn một nguyên nhân”.
Nếu tái hiện: giữ firstfailure và đối chiếu payload/stamp/cutoff để chọn
một correction có căn cứ dưới contract mới; không chạy bù lượt thứ2.

QC: artifact/hash/close ACK; PID khác; GID/type/QoS publisher khớp; internal
sequence liên tục cho data đã nhận; sharedstamps/payloadhash parity; endpoint
age/max inter-sample gap report riêng; world ACK/iterations/clock/no retry;
estimator chỉ dùng wheel/IMU causal. Marker/progress không áp cho zero-only.

## 5. Điểm dừng và artifact

`diagnostic_result.json` phân biệt collection_complete với rootcauseknown.
GUI hiển thị số lượt/tick, support của hai đường, classification và lỗi;
khóa budget sau đóng. Một result “completed” chỉ là diagnostic lifecycle
đã hoàn tất, không training readiness hoặc đủ điều kiện hardware.

Không mở thêm train sau diagnostic. Nếu không tái hiện: đề xuất đúng một
phép phân biệt tiếp có information gain rõ hoặc giữunknown/dừng mởrộng;
không lặp train pilot tới khi tình cờ chạy qua.
