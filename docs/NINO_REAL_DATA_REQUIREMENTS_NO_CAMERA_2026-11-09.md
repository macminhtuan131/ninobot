# Dữ liệu thật Nino: mục đích, phần đã có và kế hoạch không camera

Ngày 09/11/2026. Người vận hành xác nhận **không có camera**.

> Cập nhật sau khi kết nối Pi .103: đã review trực tiếp tám phiên SAC torque
> ngày08/11, sáu bag integrity đạt/hai lỗi; LiDAR/bridge/EKF đã khôi phục.
> [Kết quả mới và lựa chọn velocity backend](NINO_REAL_08NOV_REVIEW_AND_BACKEND_2026-11-09.md)
> được ưu tiên cho hiện trạng. Các bảng cutoff02/11 dưới đây là bản rà soát
> trước khi có dữ liệu Pi mới; không dùng câu “chưa có navigation thật” ở
> bản cũ để phủ nhận kết quả mới, cũng không coi SAC23D là TD3 deployment.

## 1. Phạm vi rà soát và correction

Đã đối chiếu báo cáo inventory 03/11, review trực tiếp bốn bag 07/11,
task gờ không biết trước 09/11, collector/Studio, observation pipeline,
ROS shadow, SysID và cấu hình thu. Đây là rà soát source/config/báo cáo local,
không phải kiểm kê mới trên Pi hoặc giải mã lại mọi bag. Cutoff bằng chứng
real được dẫn vẫn là các phiên đến 02/11; source/GUI mới không tạo thêm data.

**Camera không phải điều kiện chung cho nhánh real.** Các protocol video
07/11 là một phương án quan sát, không phải cách duy nhất kiểm vật lý.
Không chặn wheel-response ID, feature/history hoặc shadow chỉ vì thiếu camera.
Phép đo độc lập vẫn cần cho claim thân xe/slip, nhưng có thể là mốc/thước
cho endpoint, hoặc estimator LiDAR được kiểm riêng cho trajectory.

Không có motion mới, không mở lại ledger cũ, không thay threshold/controller/
firmware, không đổi ABI hoặc checkpoint trong lần rà soát này.

Ký hiệu: **[N]** Nino (raw review/config/source/khai báo operator được nêu rõ),
**[S]** suy luận có giới hạn, **[Đ]** đề xuất chưa đo/chưa chạy.

## 2. Dữ liệu thật dùng cho thành phần nào?

| Thành phần | Cần dữ liệu gì / để làm gì? | Có cần camera hoặc body reference không? |
|---|---|---|
| Collector, command contract | Command các tầng, enable/status, sensor, clocks, owner/STOP, closure/hash: biết lệnh đi tới đâu và file có dùng được không | Không cần camera; không tự xác nhận motor/thân thực thi |
| Observation History | IMU6, wheel L/R, baseline/final, trạng thái đã khai báo, thời gian/tuổi mẫu; proposal/accepted trước đó do pipeline ghi: kiểm frame, causality, freshness và ABI | Không cần body reference để tạo history; phải đối chiếu adapter/sim đang dùng, không coi mọi checkpoint chung ABI |
| Reactive governor | IMU/gyro, wheel/reference/history: phát hiện nhiễu và điều tiết baseline | Chạy detector không cần camera; chứng minh lợi ích vật lý cần outcome phù hợp. Thiếu target thật thì không dùng wheel-error như target đã đo |
| SysID command → reported wheel | Final ROS request + wheel L/R + common receipt clock + geometry danh nghĩa + session split: fit đáp ứng tổng delay/lag/gain | Không cần camera/body speed để fit đường reported wheel; cần xác minh feedback gắn với bánh vật lý trước khi gọi là calibrated plant |
| Hiệu chỉnh sim | Đáp ứng bánh, geometry/load/caster, noise/delay cảm biến, envelope thực: giảm model discrepancy | Có thể làm từng phần; không bắt đo COM/inertia/friction đầy đủ trước wheel ID |
| TD3/PPO trong sim | Transition từ environment: observation, action proposal, projection/final, reward, termination, labels sim | Không bắt buộc có data thật để train sim. Thiếu calibration thì chưa được gọi sim-to-real đã xác nhận |
| Body model, slip, stopping | Reference thân độc lập, geometry và clock/uncertainty: tách bánh quay khỏi thân chuyển động | Cần phép đo độc lập tương ứng; camera chỉ là một lựa chọn. Endpoint tape không cho transient speed/slip |
| Follower/navigation, task mới | Path/goal, estimator/TF, pose/heading, outcome thực và thời gian: vượt gờ, tới đích, bám đường | LiDAR có thể phục vụ estimator; đánh giá error cần phân biệt estimate và reference, không tự lấy estimator làm GT |
| Shadow/deployment | Inputs thật, history/proposal/projected, inference duration, age/deadline dưới tải Pi, mode/owner/STOP | Shadow quyền 0 không cần camera; nó không chứng minh policy có ích khi thực thi |

## 3. Dữ liệu đã thu xong cho claim hẹp

| Dữ liệu [N] | Bằng chứng/kết quả | Đã đủ cho / giới hạn |
|---|---|---|
| Inventory sensor 27/10 | IMU 2.708; motor_fb 2.707; status 270; LiDAR 394 scan; rate quan sát khoảng 47,13 Hz và 6,95 Hz | Có dữ liệu các kênh trong cửa sổ; không là rate bảo đảm hoặc latency |
| Raw ↔ bridge | Payload/header đã đối chiếu trong cửa sổ giao nhau | Bridge chuyển đổi trong phiên; derived odom không là body truth |
| Trục IMU thô | 708 mẫu xác minh ứng viên yaw +90° | Mapping thô; không phải fine calibration |
| Dấu gyro Z | 718 mẫu yên/trái/phải; mean −0,000453 / +0,303611 / −0,359153 rad/s | Đúng dấu theo nhãn operator; không phải scale/góc chính xác |
| Mounting/TF | IMU [−0,050; −0,020; +0,014] m; LiDAR [+0,220; 0; +0,189] m so gốc trục; yaw IMU +90° từng áp/kiểm live | Số đo gần đúng; không effective rolling calibration |
| Closure recorder đứng yên | Stationary v2: 20.749 messages, 22 file hash, SQLite/metadata và cuối phiên 55–60 s đã review | Một capture đóng sạch; không cần lặp đứng yên giống hệt nếu không có thay đổi/lỗi mới |
| Command/STOP/enable traces | Có source/intermediate/final, status, enable requests; có cả phiên STOP và discovery failed | Phân biệt input bị chặn; firmware enable không là effective motor permission |
| Review bánh/thân 07/11 | Bốn bag: 95.459 messages; 100 file raw hash khớp, SQLite/counts đạt | Integrity + trace đã kiểm; không phải bốn motion success hoặc body reference |

Geometry Pi R=0,060 m, separation=0,345 m là **config**, không đưa vào cột
đã hiệu chuẩn. Cao trục 0,056 m không tự là bán kính lăn hiệu dụng.

## 4. Phần đã có một phần, còn phải thu gì?

| Mức ưu tiên / dataset | Hiện trạng [N] | Dữ liệu bổ sung [Đ] / cách thu không camera | Dùng để quyết định gì? |
|---|---|---|---|
| P0 · Đối chiếu vật lý cùng phiên | Clear-zone từng được báo tiến/tự dừng; V2 final/feedback tăng nhưng operator báo không tiến; mâu thuẫn chưa giải thích | Một phiên chẩn đoán: marker thân + mốc sàn; đo vị trí đầu/cuối và ghi uncertainty; quan sát riêng từng bánh nếu nhìn được, không tới gần xe đang chạy. Ghi không nhìn thấy/không phân biệt nếu cần | Có chuyển vị endpoint hay không; feedback có khớp bánh nhìn thấy không; chọn nhánh lỗi. Không kết luận slip hoặc body latency |
| P1 · Độ lặp command → wheel | Chưa đủ ba lượt hợp lệ cùng điều kiện; các pilot cũ đã đóng/unknown | Sau P0, protocol mới tối đa 3 phiên cùng profile/sàn/tải/pose, caster note; review từng phiên. Bag các phase baseline/ramp/hold/zero/poststop, đo endpoint thủ công mỗi phiên | Biến thiên L/R, chênh bánh, tính nhất quán endpoint; chưa chứng minh tổng quát |
| P1 · Dataset SysID | Có tool, chưa model thật được kiểm held-out | Chuyển bag hợp lệ thành CSV/session metadata theo schema tool; khóa whole-session holdout trước fit. Chỉ thêm excitation/profile nếu input hiện tại không nhận dạng được | Model đáp ứng tổng bánh cho sim, sai số holdout và phần không identifiable |
| P2 · Geometry/load/caster | Mounting gần đúng; rolling geometry, tải/caster thực chưa đủ | Đo wheel/track/clearance bằng thước, cân tải/robot nếu có dụng cụ; ghi caster orientation hoặc unknown. Sau baseline, đối chiếu encoder với displacement/heading ngoài encoder theo protocol riêng | Không trộn sai radius, gain, slip và lag vào một fit |
| P2 · Body trajectory/heading | Chưa có reference định lượng được review | Kiểm khả năng scan matching với LiDAR hiện có trong vùng có tường/góc cố định; đối chiếu endpoint bằng thước/mốc. Giữ LiDAR-only đủ độc lập với encoder nếu dùng kiểm wheel discrepancy; khai báo mọi fusion | Candidate body estimator; chỉ chấp nhận accuracy/rate phù hợp claim sau validation. Chưa tự là GT |
| P2 · Mode/limits/backend telemetry | Có source tham khảo và status; binary/readback/target/current thực chưa đủ | Đọc cấu hình/readback/interface thật; ghi target sau limit, fault/current/voltage nếu có. Kênh không xuất giữ null; không tự flash hoặc tăng dòng | Giới hạn diễn giải plant và phát hiện saturation/fault |
| P3 · Gờ không biết trước, bám đường | Chưa dataset real crossing được xác nhận | Gờ cứng cố định trong envelope đo thật; controller không nhận vị trí gờ; reference path, estimator, IMU/wheel/commands/STOP; outcome operator + mốc endpoint, trajectory nếu đã validate | Vượt/arrival/tracking/time. Không có trajectory đáng tin thì chỉ báo estimate, chưa path error độc lập |
| P3 · Governor/residual comparison | Chưa có lợi ích real được xác nhận | Baseline trước; sau đó protocol đối chứng cùng information/limits/layout, log proposed/projected/final riêng; actuator readback chỉ nếu có | H2/H3 trong envelope, không lấy arrival hoặc source giảm làm bằng chứng giảm risk |
| P3 · Shadow/compute | Có software observer alpha0, chưa deployment budget đo trên Pi | Record inputs, history-ready/block reasons, ABI, proposal/projection, inference/control timing dưới tải thực; không phát motor command | Tương thích và compute/freshness; không chứng minh controller tốt hơn |
| Sau cùng · Generalization | Chưa có real test bank | Session/load/height/angle/route held-out sau feasibility; dây mềm/rãnh/hõm tách cơ chế | Phạm vi áp dụng; không gộp mọi vật cản |

**Chi tiết SysID hiện có:** `residual_sysid.py` yêu cầu tối thiểu 3 session
đầy đủ, nonempty held-out whole sessions, explicit SI/clock/provenance và
geometry danh nghĩa. Đây là điều kiện phần mềm hiện tại, không là chứng minh
3 phiên đủ thống kê. Test excitation/gap có thể từ chối dataset; không hạ
ngưỡng hoặc đổi holdout sau khi thấy fit để tạo PASS. Không cần fit body/slip
đồng thời. Một forward profile không tự xác minh trái/phải bị đổi kênh.

## 5. Quy trình đo không camera cho việc gần nhất

1. **Offline trước:** kiểm metadata/schema/clock/cửa sổ của bag đã có, xác định
   session nào dùng được cho reported-wheel fit hoặc cần giữ diagnostic.
2. **Chuẩn bị measurement:** chọn một điểm cố định trên thân; xác định X/Y
   đầu/cuối theo cùng mốc sàn bằng thước. Ghi resolution/repeatability và
   cách đo; không tuyên bố mm accuracy nếu chưa đo được. Giữ nguyên vị trí
   xe sau trial đến khi ghi endpoint; tiếp cận khi đã dừng/disarm.
3. **Khi mở một motion protocol mới:** revalidate live owner/Agent/telemetry/
   STOP/startup ACK. Profile đã thảo luận vẫn 0,05 m/s, ramp 0,10 m/s²,
   source 2 s rồi zero/disable, bag 60 s. Không tự tăng tốc/thời gian để
   displacement dễ nhìn. Việc này không phải motion đã được thực hiện.
4. **Ghi kết quả:** endpoint displacement và uncertainty; wheel L/R
   observed/not_observed/ambiguous/not_visible; tự dừng/can thiệp; flags/STOP.
   Thiếu visibility không làm raw wheel dataset tự mất giá trị, nhưng giới
   hạn claim physical mapping. Không tự kết luận trượt khi body không tiến.
5. **Review rồi quyết định:** raw hợp lệ + endpoint/quan sát nhất quán mới
   chốt repeatability riêng. Nếu còn mâu thuẫn, giữ UNKNOWN và kiểm đúng
   mapping/scale/truyền động/backend; không tuning để che mâu thuẫn.

Endpoint trước/sau **không có time series**, không cho onset/T90/instantaneous
body velocity, quãng dừng sau riêng thời điểm zero hoặc slip ratio. Đồng hồ
bấm tay chỉ cho timing thô có reaction uncertainty. Không đồng bộ bằng cách
ép onset feedback trùng onset observer rồi dùng nó đo latency.

LiDAR khoảng 7 Hz lịch sử có thể hữu ích cho pose trên đoạn dài hơn được
chốt riêng, nhưng chưa đủ mặc định cho transient ~100 ms, pitch/contact hoặc
vùng ít đặc trưng. Endpoint validation không tự xác minh toàn trajectory.

## 6. Ghi gì mỗi phiên và tiêu chí chất lượng theo claim

- Bag: command source/selected/smoothed/final đang thực dùng; `/motor_fb`,
  `/motor_status`, `/imu/data`, enable request, `/scan_raw`, TF cần cho guard,
  monitor events nếu có. Source/final/target/readback phải tách nghĩa.
- Metadata: session/protocol/config identity, firmware known/unknown,
  RC/owner, sàn/tải/caster, nguồn/pin nếu biết, mốc đo và uncertainty.
- Kết thúc: lifecycle, raw bag/metadata/hash, lỗi/STOP/failure/censoring,
  endpoint/quan sát ghi riêng; không sửa raw để thêm nhãn.
- QC file đạt không tự làm physical outcome đạt. Phân biệt **raw integrity**,
  **reported-wheel usable**, **endpoint usable**, **trajectory validated**,
  **slip measurable**; có thể đạt một loại và chưa đủ loại khác.
- Studio hiện vẫn có trần WARN/Q2; không tự gán Q3/Q4 từ thước/mốc hoặc bỏ
  check chỉ vì không có camera. Panel video hiện có là optional, chưa có
  workflow nhập endpoint thủ công chuyên biệt; lưu metadata/derived record
  ngoài raw trước, không giả vờ GUI đã triển khai chức năng này.

## 7. Những gì chưa cần thu

Không lặp inventory/IMU sign chỉ vì thêm GUI. Không bắt force sensor, torque
độc lập, caster encoder hoặc camera làm prerequisite cho wheel ID/history.
Không thu teleop ngẫu nhiên để nạp replay TD3. Không bắt full navigation
trước wheel ID; vẫn giữ TF/scan mà Collision Monitor cần. COM/inertia, caster
friction, power instrumentation chuyên sâu chỉ ưu tiên khi có câu hỏi/failure
cụ thể. Chưa có reference thân phù hợp thì tạm hoãn claim slip định lượng,
không tạm dừng mọi công việc real hoặc train sim.

## 8. Nguồn local đã đối chiếu

- `docs/NINO_REAL_DATA_STATUS_2026-11-03.md`, `NINO_REAL_DATA_CHECKLIST_2026-11-03.md`.
- `docs/NINO_WHEEL_BODY_GAP_REVIEW_2026-11-07.md`, diagnostic draft và body-reference Studio cùng ngày.
- `docs/NINO_UNKNOWN_STEP_TASK_DIRECTION_2026-11-09.md`.
- `docs/NINO_TD3_DATA_STUDIO_STANDARDIZATION_2026-11-08.md`.
- `src/nino_pi/REAL_DATA_STUDIO.md`, `REAL_DATA_COLLECTION.md`, `WHEEL_RESPONSE_PROTOCOL.md`.
- `src/nino_pi/config/real_session.template.json`, `real_collection_residual_diagnostic.json`, `stm32_usb_wheel_response_collection.json`.
- `src/nino_control/nino_control/residual_pipeline.py`, `residual_velocity.py`, `residual_shadow.py`.
- `src/nino_rl/nino_rl/residual_sysid.py`; `src/nino_pi/nino_pi/studio_quality.py`, `project_evidence.json`.

**Việc kế tiếp:** dùng bag/metadata hiện có đánh giá đầu vào reported-wheel
SysID; chuẩn bị một diagnostic endpoint bằng thước/mốc để giải quyết physical
consistency khi mở lại real. Không cần mua/đợi camera để làm hai việc này.
