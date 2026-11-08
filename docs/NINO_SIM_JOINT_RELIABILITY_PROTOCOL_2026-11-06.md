# Protocol: candidate joint reader RELIABLE

06/11/2026 · một candidate riêng, hai stage hữu hạn. Không sửa frozen backend,
không mở lại partial TD3/seed22/33/evaluation cũ. Người dùng yêu cầu tiếp tục
nhánh Sim; protocol này chốt trước khi chạy fixture hoặc physics mới.

## Câu hỏi và thay đổi duy nhất

Publisher joint đã offer RELIABLE; observer cũ dùng BEST_EFFORT/depth100.
Candidate chỉ đổi reliability của subscription `/joint_states` sang
RELIABLE, giữ toàn bộ QoS còn lại, topic/type, callback, depth100, các
subscription khác và PI/physics/guidance/reward/feature contract.

Backend mới là subclass; replace subscription sau khởi tạo observer nhưng
trước owned Gazebo launch và trước bất kỳ joint sample. Kiểm cả entity và
QoS các subscription khác không đổi. Không sửa source broadcaster hoặc
subscriber của PI. Đây là compatibility/hardening candidate, không tuyên bố
QoS đã được chứng minh là nguyên nhân failure50ms của pilot.

## Stage1 — một fixture ROS-only, không Gazebo

Action `sim-joint-reliability-fixture`, root `~/nino_research/sim_joint_reliability_v1`.

- Source RELIABLE/depth100, domain139/local. Hai process readers độc lập:
  BEST_EFFORT và RELIABLE, cùng depth100; không motor command.
- Tối đa **1handshake +1.000labeled JointState =1.001publish attempts**.
  Labeled source500Hz, source header10s +index×2ms; source log index,
  stamp, fieldhash, before/afterpublish monotonic. `publish()` return không
  được gọi là DDS delivery ACK.
- Discovery phải thấy2readers, quiet0,2s, một handshake stamp9s; cảhai phải
  xác nhận đúngstamp trước labeled window. Không resend nếu thiếu handshake.
- Cùng một pauseplan được gửi trước stream: tại start+1s (index500), mỗi
  reader dừng executor100ms, ghi actual start/end/count/laststamp. Source
  tiếp tục ở process khác; không bỏ message trong pause.
- Để phép fault hợp lệ: actual pause100–200ms, startlag≤40ms và40–100source
  attempts nằm trong từng pause. Đây là fixture engineering gates tạm thời.
- Sau1.000messages query endpoint cuối bằng cùng source target; support
  causal≤40ms, deadline5s, IPC grace1s. Không interpolate/future support,
  không thêm message để váđuôi. Quietdrain0,1s rồi đóng cảhai process.
- Source publish call≤100ms, max interval≤40ms; vượt ngưỡng/không tạo được
  fault đúng lịch →fixtureinvalid/no-go, giữ toàn bộ pacing/backpressurelog.
- RELIABLE phải có đủ1.000labeled unique và1.000records, không payload
  mismatch, không duplicate/unknown/out-of-order; coverage không thấp hơnBE.
  Cảhai endpoint/pause/closure phải hợp lệ. ThiếuBE giữ nguyên trong kết quả.
- Canonical fieldhash dùngschema đã kiểm; CDR serialize lại chỉ diagnostic.
- Wall deadline120s. Một fixture, không retry/tăngcounter/đổiqueue sau kết quả.

Nếu cảhai cùng đủ: `candidate_compatible=true`, **chưa chứng minh lợi ích
reliability**. Nếu RELIABLE thiếu, trễdeadline/backpressure hoặc fixtureinvalid:
no-go; stage2 không được mở. Không sửa QoS candidate thứhai.

## Chọn stage2 có điều kiện trước outcome

Quy tắc khóa: nếu candidate_compatible thì chọn candidate cho **functional
B0 qualification**, để kiểm đường reference/task/stop dưới acquisition mới.
Quy tắc không đòi claim superiority của reliability; không coi fixture là
training readiness. Kiểm software và namespace/clock phải đạt trước launch.

Action `sim-joint-reliability-gazebo`; cùng root nhưng stage/manifest riêng,
phụ thuộc đúng SHA của fixture đạt, không tự chạy do chỉ mở GUI.

- **Tối đa2fresh Gazebo launches**: B0 clear stop6s rồi stop8s;
 140native transitions/14s mỗi lượt, tối đa280; residual request scalar0.
- Giữ103D/1D wrapper/sharedpreview, frozen nominal reward/limits, physics1ms,
  chunks50ms, source/native100ms, estimator wheel/IMU và yawfollower.
- Primary joint RELIABLE, independent observer BEST_EFFORT chỉaudit; không
  váprimary bằngsidecar. Giữ strictsupport40ms, endpoint/receipt/payload/ACK.
- Task: marker0,95m, quietstop2s; maxpath40mm, estimateposition50mm và
  estimateyaw0,05rad. Đây là proposal gate Sim, không factory acceptance.
- Native nominal vRMSE primary; GT-header20ms/+10ms riêng, không nội suybody.
  Replaydiagnostic obs103/request1D/nextobs103 giữ rõ, không thêm vào TD3replay.
- Failure support/physical/task/ABI/measurement/closure: đóng slot còn lại,
  retainraw/partialtrace. Không smoke/retry/extrapolation hoặc ép metric pass.
- Wall deadline1200s; setup settling0,5s/maximum5s và startup ghi riêng,
  controlticks không phải tổngphysicsrequests hoặc free-startup iterations.

## Phạm vi kết luận và điểm dừng

Không actorinference/optimizer/training/hardware ở cảhai stage. Không có
optimizer load; dù2/2B0 đạt cũng không đủ kết luận failurecũ được chữa hoặc
reliableloss-free. Không so hai rollout mới với historicalB0 để kết luận
QoS cải thiện tracking theo causal/statistical estimand.

Nếu cảhai stage đạt, chỉ đề xuất một learner protocol mới với candidate,
freshidentity/budget và ghi rõ unresolvedsource/load risk; không reopen700ticks.
Nếu fail/unknown, dừngcandidate và quyết định baseline/acquisitionarchitecture;
không thêm correction/queue/physics budget trong protocol này.

## Software QA trước release

Kiểm counter/coverage/payload/missing/duplicate, invalidpause và backpressure;
kiểm thayQoS bằng ROS Node thật/domain140 không source/Gazebo; các fixture
số liệu tổng hợp không là1.000live samples. GUI hai nút códependency/gate,
progress/result/error và budgetconsume; trainingtab100D/2D vẫn riêng.
