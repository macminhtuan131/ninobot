# Kết quả: diagnostic joint boundary hai process

06/11/2026 · **2/2launches,200zero ticks đã đóng; không tái hiện failure50ms.**
Kết luận nguyên nhân **unknown**. Không mở training hoặc sửa backend frozen.

## Quyết định

Đã hoàn thành diagnostic được đề xuất sau pilot TD3partial. Cả hai đường
joint đủsupport≤40ms ở mọi feedbackcheck đã chạy, nhưng không có optimizer
load và chỉ hai fresh launches. Không suy loss-free, reliability tổng quát
hoặc nguyên nhân failure cũ từ kết quả sạch này. Partial TD3700ticks/
636criticupdates, seed22/33 và10eval vẫn đóng.

Bằng chứng mới cho candidate nhỏ: publisher offerRELIABLE, hai readers dùng
BEST_EFFORT/depth100. Chỉ đề xuất một candidate readerRELIABLE và kiểm fixture
riêng; chưa thay parent hoặc gọi QoS là nguyên nhân đã chứng minh.

## Đã làm gì

- Thêm `residual_joint_boundary.py`/YAML/script riêng và process
  `joint_boundary_observer.py` chỉ đọcJointState.
- Primary giữ backend cũ, thêm log nội bộ. Process phụ subscribe cùngtopic,
  type/QoS; không phát command, không convert contact, không nạp actor.
- Tại mỗi feedbackgate, hai process query cùngtarget/source-age40ms và
  deadline5s; ghi source/receipt/counter/hash/ACK/error/clock riêng.
- Zero source toàn bộ10s/lượt. Native100ms, physics1ms/chunk50steps, model/
  PI/geometry/estimator/contact instrumentation giữ. Setup/closure giữledger.
- GUI có profile **Joint boundary ·hai observer ·2lượt zero-only**: nút chạy,
  tiến độ, sốtick/check, maximumage mỗiđường, payloadparity/error, result và
  hướngtiếp. Budget đóng khóa rerun; không tự phát thêm physics/train.

## Số thực thi và QC

| Chỉ số | Launch1 | Launch2 |
|---|---:|---:|
| Complete zero native ticks | 100 | 100 |
| Feedbackchecks(có duplicate final recheck) | 306 | 306 |
| Trong đó setup/control | 6/300 | 6/300 |
| Joint records primary/independent | 7.569/7.569 | 7.651/7.651 |
| Shared source stamps | 7.569 | 7.651 |
| Canonical payload mismatch | 0 | 0 |
| Maximum endpoint age primary/independent | 0/0ms | 1/1ms |
| Maximum consecutive source gap | 3ms | 3ms |
| Observer shutdown ACK | đạt | đạt |

612checks không là612trials độc lập: mỗinative tick có2half-boundarychecks
và1finalrecheck; setup còn6checks/launch. Sốrecord bao gồm startup, không
chia cho10s để gọi observedrate của control window. Counts khớp giữa hai
readers không xác nhận tổngpublishercount hoặc không mấtmẫu upstream.

- **60artifact hashes +121prelaunch source files** đạt kiểm trước cập nhật
  presentation/metadata.420worldrequests ACK/completion/clock đúng, retry0;
  tổng21.000physicssteps trong cácrequests gồmsettling, không gồmfree startup.
-4parameter readbacks;1.000causal estimatorupdates, chỉwheel/IMU; GT dùng
  setup/audit, không đi vào điều khiển. Mọi drive requested/executed reference
  được kiểm bằngzero. Khôngmarker/progresstask cho diagnostic này.
- Hai graph cùngpublisherGID trong từnglaunch: `joint_state_broadcaster`,
  `sensor_msgs/msg/JointState`, offered reliability1(RELIABLE). Reader
  reliability2(BEST_EFFORT),depth100. Offered history3/depth0 là giátrị
  introspection; không coi0 là đãđo internalpublisherqueue.
- Process phụ PID152474 và152896 ở hai lần; subprocessđược tạo riêng, không
  thread cùngprimary. Nó chỉ ghi rawmetadata và đápIPC, không váprimary.
- Actor inference0, optimizerupdates0, trainingtransitions0, hardware0.
  Jobwall70,19s; không dùng con số này làm deadline realtime hoặc throughput guarantee.

## Correction phần mềm trước chạy: hash message

Fixture ROS phát hiện CDR serialize lại có hash khác giữaprocess dù field
khớp. Đã thêm hashcanonicalfield(schema`joint_fields_json_v1`) cho parity;
CDRhash chỉ giữdiagnostic, không gọi raw-wire bytes hoặc báo payloaderror.

Trong Gazebo, cả15.220sharedstamps đều canonicalmatch trong khi CDRhash
serialize lại khác ở15.220trườnghợp. Không sửa dữliệu để làm hashkhớp.

Final softwarefixture(domain139, khôngGazebo) phát20syntheticmessages,
nhận19; thiếu mẫuđầu stamp10s được giữ, không gọi loss-free. Kiểm snapshot
support và stale-tailtimeout đạt. Các lỗi chuẩn bịtest(PYTHONPATH làm mấtROS,
fixture dùngglobalexecutor thay customcontext, CDRparity) giữXML/log; chúng
được sửa trước release, không tiêu thụ diagnosticGazebo slots.

**44software/GUI tests đạt**(17diagnostic +27GUI), không phải44robotruns.

## Điều chưa kết luận và điểm dừng

Failure50ms cũ chưa tái hiện. Không có source publish counter, nên cả hai
readers cùngthiếu nếu xảyra vẫn có thể là source hoặc sharedtransport.
Instrumentation mới có overhead, diagnostic không cóMLPgradientload; không
đồng nhất với failed TD3episode6. Giữunknown; không có root-cause correction
sau kết quả chỉ để chọn một nguyên nhân.

Đợt TD3 cũ không mở lại. Diagnostic này khôngretry hoặc thêmlaunch. Chỉ có
[một candidate tiếp](NINO_SIM_JOINT_RELIABILITY_CANDIDATE_NEXT_2026-11-06.md)
được thiết kế, chưa triển khai/release: thayyêu cầuQoSjoint trong backend
riêng, giữdepth/clock/gate, kiểmfixturefault/counter trước physics mới.
Nếu không có bằngchứnguseful khác biệt hoặc candidatefailure: giữunknown/
classical, dừngtăngbudget; không chuỗi mini train→logger→retry vôhạn.

## Artifact

Root `/home/tuanmac/nino_research/sim_joint_boundary_v1`;
run `20261106T013910423655Z_sim-joint-boundary`.

Fingerprint runner/observer/config/script:
`5798d9939f1fdc5419315f8ea6d87f04616cda6a8dc879ee5d6787a20ce015a1`.

QA, plots, tests, GUI screenshot và audit ở
`artifacts/sim_joint_boundary_2026-11-06` trong workspace hội thoại.
Verification cuối: `NINO_SIM_JOINT_BOUNDARY_VERIFICATION_2026-11-06.json`.
