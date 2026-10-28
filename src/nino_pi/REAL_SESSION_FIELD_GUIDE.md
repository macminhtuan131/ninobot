# Cách điền từng trường trong real_session.template.json

Biểu mẫu: `config/real_session.template.json`.

Cho pilot command→wheel, dùng
[`config/wheel_response_session.template.json`](config/wheel_response_session.template.json)
và [WHEEL_RESPONSE_PROTOCOL.md](WHEEL_RESPONSE_PROTOCOL.md). Form này bổ sung
owner/RC/stop/profile, clocks/events và cách xử lý trial; unknown vẫn null.
Đây là metadata chuẩn bị, chưa phải release hoặc bộ kiểm motion readiness.

**Không phải điền hết mới được thu dữ liệu.** Đây là metadata: giúp hiểu và
tái lập một lần thu. Nó không cấu hình motor, PI hay governor. Telemetry biến
thiên theo thời gian vẫn được ghi trong bag; không chép từng sample vào form.

Collector hiện chỉ kiểm tra session là JSON object và `session_id` là chuỗi
không rỗng. Kiểu dữ liệu dưới đây là **quy ước đề nghị để đọc được thống nhất**,
chưa phải JSON Schema mà chương trình enforce cho mọi trường.

## 1. Quy ước chung

- `null`: chưa biết/chưa đo/không có phép đo. Không dùng `0`, `false`, `""`
  để thay unknown. Có thể ghi lý do trong `notes` hoặc mục evidence tương ứng.
- **Số**: JSON number, ví dụ `0.1`; không viết `"0.1 m"` nếu trường đã có đơn vị.
- **Số nguyên**: counts, ID, số lần lặp; không dùng số thập phân cho counts.
- **Chuỗi**: model, đường dẫn file, tên node/topic, mô tả phương pháp.
- **Boolean**: `true`/`false` khi đã xác minh câu hỏi yes/no. Unknown vẫn `null`.
- **Mảng**: thứ tự phải rõ, ví dụ `[x, y, z]` hoặc `[length, width, height]`.
- **Object**: nhóm dữ liệu có tên, ví dụ `{"left": null, "right": null}`.
  Dùng tên thật của caster; không bắt buộc đặt front/rear nếu robot dùng left/right.
- SI: m, s, rad, rad/s, m/s, m/s², N, N·m, A, V, kg, Hz; nhiệt độ ghi °C.
  Rate filter có thể dùng Hz hoặc time constant s nhưng phải ghi rõ.
- Gắn `frame` cho pose/orientation. Quy ước base dự kiến x tiến, y trái, z lên;
  phải xác nhận lắp đặt/driver thật. Không tự đổi dữ liệu raw để giống quy ước.
- Đối với thông số motor/caster hai bên, ưu tiên object theo ID thay vì mảng
  mà người đọc phải đoán bên trái/phải.
- Lưu nguồn: `measured`, `datasheet`, `driver_config`, `firmware_config`,
  `CAD_estimate`, `operator_report`; nguồn khai báo không tự thành đo thật.
- File YAML/Xacro hiện có là bằng chứng **config/simulation**, không tự là số
  đo phần cứng. Có thể tham chiếu chúng với nhãn đúng; không điền như đã hiệu chuẩn.

## 2. Chỉ cần bắt đầu như thế nào?

### Phiên đứng yên đầu tiên

1. Đặt `session_id` duy nhất, giữ `test_stage=stationary_inventory_no_motion_requested`.
2. Điền operator/robot ID/date nếu biết, ghi rõ chưa thử chuyển động.
3. Model nhìn được từ nhãn và thông tin nguồn đang có có thể điền ngay.
4. Các thông số chưa biết giữ `null`; chạy audit và bag để tìm phần tự đọc được.
5. Từ audit, bổ sung topic/frame/driver/command ownership; không biến thành kết
   luận axis/sign/watchdog/PI đã đúng nếu chưa có thử nghiệm tương ứng.

`pi_rate_hz`, motor latency, torque calibration, COM, friction, video contact,
held-out split… **không phải điều kiện để chạy một audit đứng yên**. Tuy nhiên,
thiếu feedback/limits/watchdog/power verification vẫn ngăn kết luận robot sẵn
sàng thử chuyển động. Chưa có independent body reference thì chưa đo slip tuyệt đối.

Không cần nhập lại toàn bộ trường bằng tay mỗi phiên. `hardware`, phần geometry
không đổi, mounting và cấu hình controller có thể tái sử dụng từ bản inventory
đã kiểm tra, kèm version/evidence. Cập nhật khi thay bánh/caster, firmware,
driver, gain/limits, sensor mount hoặc cấu hình nguồn. Ngày, payload, điều kiện
sàn, route/obstacle, mode và outcome phải phản ánh đúng phiên hiện tại.

## 3. Thông tin chung

### Metadata firmware khi dùng STM32 USB

`firmware_integration` là mục bổ sung, không cấu hình hoặc nạp board:

- `source_repository`, `reviewed_source_commit`: URL và commit đã đọc/build.
- `flashed_source_commit_and_evidence`, `flashed_binary_sha256_and_evidence`:
  bản thực sự đã nạp cùng log/provenance; chưa xác định thì giữ `null`.
  Checkout trên laptop và tên USB không xác nhận bản firmware trên board.
- `board_model_revision_and_mcu_part`: nhãn board, revision và mã MCU thực.
- `usb_vid_pid_serial_and_device_path`: descriptor, serial và đường dẫn
  thiết bị quan sát trong phiên, có thể kèm evidence/ngày.
- `agent_version_launch_domain_and_environment`: version/commit agent, lệnh,
  ROS domain và RMW/discovery thực dùng. Domain của host chưa chứng minh
  domain client firmware hoặc static library đã build.
- `motor_protocol_and_board_pinout_verified`,
  `boot_enable_and_rc_arbitration_verified`: evidence đối chiếu đúng firmware,
  wiring/motor và RC; chưa xác minh giữ `null`, không tự đặt `true` từ README.
- `collection_profile_and_claim_scope`: tên profile và phạm vi kết luận.
  Profile USB/IMU không chứng minh encoder/motor hoặc navigation hoạt động.

Xem [STM32_USB_INTEGRATION.md](STM32_USB_INTEGRATION.md) cho profile riêng.

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `session_id` | Chuỗi duy nhất | Tự đặt theo robot, bài thử, UTC và lần lặp; tránh dùng lại `EDIT_unique_id`. Đây là trường duy nhất collector bắt buộc không rỗng. |
| `test_stage` | Chuỗi | Giai đoạn đang làm: `stationary_inventory_no_motion_requested`, `clear_floor_response`, `single_obstacle`… là mô tả, không phải lệnh chạy. |
| `operator` | Chuỗi | Người chịu trách nhiệm thu; tên/tên viết tắt. Username Linux chỉ điền nếu đúng người vận hành. |
| `robot_id` | Chuỗi | ID bạn gán cho robot vật lý, giữ nhất quán qua các phiên; hostname của Pi không tự là robot ID. |
| `date_utc` | Chuỗi ISO 8601 UTC | Lấy thời gian hệ thống đã kiểm tra đồng bộ; dùng dạng `YYYY-MM-DDTHH:MM:SSZ` hoặc `+00:00`. Không dùng giờ Bangkok không có timezone. |
| `notes` | Chuỗi | Điều bất thường, unknown và lý do, thay đổi so với phiên trước, giới hạn phép đo. |

## 4. hardware — thiết bị, driver và encoder

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `pi_model_ram` | Object `{model, ram_GB}` | Model từ `/proc/device-tree/model`; RAM danh định từ nhãn/mã sản phẩm. `free -h` là RAM OS sử dụng được, không tự bằng dung lượng danh định. Có thể ghi cả hai có tên rõ. |
| `motor_model_left_right` | Object theo `left`/`right`, mỗi bên chuỗi/object | Đọc nhãn motor và gearbox; lưu hãng/model/gearbox, ảnh hoặc datasheet. Không suy model từ tên driver. |
| `motor_firmware_versions` | Object theo motor ID, mỗi version là chuỗi | Đọc version/status mà driver hoặc phần mềm hãng đã cung cấp. Nếu không có giao diện read-only/documentation thì để unknown; không flash firmware để tìm version. |
| `motor_driver_package_commit_and_launch_command` | Object `{package, version, commit, launch_command, config_file}` | Audit cho package/node hints; lấy command/config từ terminal/service khởi chạy thật. Commit từ checkout driver nếu dùng source; dùng package version nếu bản binary, không bịa SHA. |
| `imu_model_firmware_driver_launch` | Object `{model, firmware, package, launch_command, topic}` | Nhãn IMU + tài liệu + driver đang chạy + publisher của topic IMU. Firmware có thể null. |
| `lidar_model_firmware_driver_launch` | Object tương tự IMU | Nhãn LiDAR + driver thật và publisher `/scan` hoặc topic thực. |
| `can_usb_serial_baud_and_ids` | Object/list theo interface | Ví dụ các key `interface`, `device`, `bitrate_bps`, `motor_ids`. CAN bitrate từ cấu hình bus; serial baud từ config; USB product/serial từ inventory thiết bị. CAN IDs là ID thiết bị, không phải joint index. Không gửi lệnh CAN tùy ý để dò. |
| `wheel_joint_names_left_right` | Object `{left: string, right: string}` | Đọc `name[]` trong `/joint_states`, đối chiếu wheel vật lý/driver. Tên hiện có trong URDF chỉ là gợi ý. |
| `encoder_counts_per_motor_rev` | Object bên trái/phải chứa số nguyên | Datasheet/firmware: effective decoded counts cho một vòng **trục motor**. Ghi rõ CPR/PPR, quadrature x1/x2/x4 hoặc absolute encoder resolution. Không nhân quadrature hai lần. |
| `encoder_counts_per_wheel_rev` | Object bên trái/phải chứa số nguyên hoặc null | Tính từ counts motor × gear ratio chỉ khi định nghĩa/gear ratio khớp; đối chiếu raw counts nếu driver có. Encoder đặt trực tiếp ở bánh thì dùng resolution tại bánh. Position tính rad trong JointState không cho biết raw encoder resolution. |
| `gear_ratio_motor_rev_per_wheel_rev` | Object bên trái/phải chứa số | Datasheet hoặc số vòng motor / một vòng bánh. Direct drive chỉ ghi 1 khi đã xác nhận. Nếu ratio không nguyên thì giá trị tính counts/wheel có thể cần ghi rõ định nghĩa thay vì ép thành integer giả. |
| `encoder_and_motor_positive_direction_verified` | Object theo bên, với boolean và evidence | Kiểm tra sign convention trong driver rồi đối chiếu quay thực/quan sát có kiểm soát ở giai đoạn được phép chuyển động. `true` chỉ khi cả mapping/sign được kiểm tra; đứng yên không xác minh được. |
| `encoder_velocity_estimation_filter` | Object `{method, window_s, update_hz, source}` | Driver/firmware code: từ delta ticks hay motor-reported speed, smoothing/filter, cửa sổ, wrap handling, units/conversion. Topic rate không tự là encoder sampling rate. |

## 5. geometry_and_load — đo cơ khí

Thực hiện đo khi robot ở trạng thái phù hợp, motor không tự chạy. Không cần
đo COM/inertia/friction chi tiết trước audit. Khai báo payload của đúng phiên.

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `wheel_radius_unloaded_m_left_right` | Object `{left: number, right: number}` | Đo đường kính thực không tải bằng thước/thước cặp, chia 2; đổi mm sang m. Ghi vị trí đo/độ mòn. |
| `effective_loaded_radius_m_left_right` | Object bên trái/phải chứa số | Sau khi cho phép thử: lăn trên đoạn phẳng đo được D, có tải thật, dùng góc quay bánh Δθ rad; `r_eff=D/Δθ` trong điều kiện gần thẳng/ít slip. Ghi uncertainty, lặp đo; không coi radius này là đo tốt nếu slip đáng kể. |
| `wheel_track_contact_centers_m` | Số | Khoảng cách tâm vết tiếp xúc hai bánh chủ động, không phải bề rộng ngoài bánh hoặc hai joint origin. Đo hình học; effective kinematic track nếu hiệu chuẩn riêng cần ghi rõ phương pháp. |
| `footprint_polygon_base_frame_m` | Mảng `[[x,y], ...]` | Đo biên chiếu bằng robot và payload trong frame base khai báo. Dùng polygon bao các phần thật; safety padding ghi riêng, không nhập như kích thước đo. |
| `overall_length_width_height_m` | Mảng `[length,width,height]` | Thước đo kích thước ngoài, tính cả phần nhô/payload; đơn vị m. |
| `ground_clearance_loaded_m` | Số hoặc object theo bộ phận | Đo khoảng cách nhỏ nhất từ mặt sàn đến phần cứng không phải bề mặt lăn, dưới payload thật; chỉ rõ chassis/bracket. Không tự bằng chiều cao vật cản vượt được. |
| `total_mass_kg` | Số | Cân toàn bộ robot ở cấu hình phiên thu, gồm pin/payload. Không dùng mass link chassis thay total mass. |
| `payload_mass_kg_and_position_m` | Object `{mass_kg, position_m, frame, method}` | Cân payload; đo vị trí tâm tải trong frame base. `mass_kg=0` chỉ khi thật sự không có payload, không dùng để thay unknown. |
| `center_of_mass_estimate_base_frame_m` | Object `{xyz_m:[x,y,z], frame, method, uncertainty_m}` | CAD đã cập nhật khối lượng hoặc phép cân/phân bố tải thích hợp. Gắn nhãn estimate. Không suy COM đầy đủ, đặc biệt chiều cao z, chỉ từ một lần cân trên sàn. Có thể hoãn. |
| `caster_wheel_radius_m_front_rear` | Object theo ID caster thực, mỗi giá trị là số | Đo đường kính bánh caster chia 2. Tên field là lịch sử; mô hình Nino có `caster_left`/`caster_right`, nên dùng ID thực, không tự giả định front/rear. |
| `caster_swivel_positions_base_frame_m` | Object theo caster, giá trị `[x,y,z]` và frame | Đo vị trí trục swivel trong frame base, không phải tâm bánh lăn đang xoay. CAD/TF là reference, phải phân biệt với đo thực. |
| `caster_trail_m` | Object theo caster chứa số | Đo offset ngang theo hình học giữa trục swivel và wheel contact/axle projection, ghi định nghĩa/sign và orientation khi đo. Không nhầm với bán kính bánh. |
| `caster_initial_orientation_rad_and_evidence` | Object theo caster `{angle_rad, reference, evidence}` | Ảnh/video/thước góc ở đầu phiên; khai báo hướng zero và sai số. Không có caster encoder thì đây là quan sát thủ công, không phải channel triển khai. |
| `caster_free_rolling_swivel_friction_or_drag_evidence` | Object `{method, observations, measurements, files}` | Kiểm tra lăn/quay có cản, kẹt, rơ hoặc interference; có thể ghi lực kéo/cản theo phương pháp rõ. Không suy hệ số damping vật lý chính xác từ cảm giác quay tay. |
| `wheel_caster_load_distribution_N_and_method` | Object theo contact `{force_N, method, uncertainty_N}` | Nếu cần: cân/force sensor phù hợp tại các điểm đỡ, giữ support cùng cao độ. Khối lượng tương đương kg × gia tốc trọng trường cho lực N phải được ghi là phép quy đổi. Tránh đổi geometry/tải trong khi đo. Có thể hoãn. |
| `measurement_method_uncertainty` | Object, key là tên phép đo | Ghi dụng cụ, resolution, cách đo, số lần lặp, ngày, nguồn ảnh/file và sai số theo đơn vị của phép đo. Không dùng một uncertainty chung cho mọi kích thước. |

## 6. controller — lệnh, PI, limits và đáp ứng

Phân biệt **requested command → limited/executed reference → encoder actual
→ independent body motion**. Một kênh có tên `actual` vẫn cần biết nó đo gì.

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `control_source_manual_or_navigation` | Chuỗi | `manual`, `navigation` hoặc mô tả mode transitions có timestamp/file nếu đổi trong phiên. Điền theo thao tác thực. |
| `command_stack_profile_and_config_evidence` | Object `{files, hashes, launch_commands, changes}` | Lưu đúng `control.yaml`, navigation params và launch thực dùng, hash/commit nếu có; không coi file default là file node đã nạp. |
| `pi_location_and_evidence` | Object `{location, node_or_device, evidence}` | `Pi`, `motor_firmware`, `both` hoặc `unknown` có giải thích. Đọc code/config đang chạy và firmware; có parameters không chứng minh loop đang thực thi trên host đó. |
| `pi_gains_units_integrator_limits_and_reset` | Object theo loop/bên `{kp,ki,error_unit,output_unit,integrator_limits,reset_rule,source}` | Đọc code/config loop thực. Đơn vị phụ thuộc error/output. Nếu torque N·m theo speed error rad/s thì Kp là N·m/(rad/s), Ki là N·m/rad với tích phân theo giây; firmware scaled gains có thể khác. Không tự chép gain mô phỏng sang robot. |
| `pi_rate_hz` | Số hoặc object theo loop | Scheduler/firmware/control timer + telemetry update counter nếu có. `/joint_states` hay diagnostics rate chỉ là publication rate, không tự bằng PI rate. |
| `final_command_topic_type_and_owner` | Object `{topic,type,publishers,subscriber_driver,evidence}` | `ros2 topic info --verbose` + audit graph và đọc backend. Ghi mọi publisher; không gán một publisher duy nhất nếu có tranh quyền. |
| `actual_wheel_target_topic_fields_and_units` | Object theo channel `{topic,type,field,unit,meaning}` | Driver telemetry tại target sau các limit/filter thực. Nếu chỉ có `/cmd_vel`, ghi wheel target unavailable; chuyển đổi lý thuyết không tự thành target được firmware thực thi. |
| `feedback_topic_fields_and_units` | Object/list mapping `{topic,type,field,unit,source}` | Message interface + documentation/code + sample thật. Tách wheel position/velocity, current, torque estimate, body estimate. |
| `torque_current_speed_limits_and_units` | Object theo bên/loop, mỗi limit có unit/source | Đọc giới hạn đang áp dụng ở từng tầng: PI/output adapter, firmware, motor/controller. Ghi min/max hoặc magnitude, peak/continuous và derating nếu biết. Không lấy rated torque làm configured limit. |
| `limit_saturation_fault_fields` | List mapping `{topic,type,field,meaning}` | Driver status/bitmask definitions và telemetry; ghi rõ từng bit. Không có channel thì null, không tự diễn giải một số thành fault code. |
| `speed_acceleration_deceleration_jerk_limits` | Object chứa giá trị/đơn vị/tầng áp dụng | Đọc gate, smoother, governor và firmware thật. Ghi m/s, rad/s, m/s², rad/s², m/s³… đúng loại đại lượng. Nhiều tầng giới hạn cần liệt kê; không giả định chỉ một ramp. |
| `command_watchdog_s_and_verified_behavior` | Object `{timeout_s,location,configured_behavior,verified,evidence}` | Timeout từ code/firmware; hành vi quan sát từ thử mất lệnh có kiểm soát ở giai đoạn cho phép. Chưa test để `verified:null`. Gate timeout không thay watchdog motor. |
| `motor_control_mode` | Chuỗi hoặc object theo bên | Mode thực: velocity/torque/current/position hoặc chế độ hỗn hợp, lấy từ driver/firmware status/config. Tên topic không xác định mode. |
| `torque_channel_classification_command_estimate_or_measured` | Object theo channel `{kind,source,unit,evidence}` | Phân loại `command`, `estimate`, `measured` hoặc `reported_unverified`. Measured phải có phép đo/hiệu chuẩn phù hợp; JointState.effort không tự là torque sensor. |
| `torque_estimate_Kt_Iq_gear_efficiency_calibration` | Object `{Kt_Nm_per_A,current_definition,gear_ratio,efficiency,sign,calibration}` | Từ motor/firmware docs và đối chứng hiệu chuẩn nếu có. Kt×Iq chỉ là torque estimate theo convention phù hợp; DC bus current không tự bằng Iq. Efficiency không biết thì null, không tự đặt 1. Có thể hoãn nếu không có channel. |
| `latency_command_to_target_encoder_body_s_and_method` | Object theo từng độ trễ `{estimate_s,uncertainty_s,method,clock,files}` | Sau khi cho phép thử sàn sạch: log command/target/encoder và body reference độc lập, xác định onset cùng định nghĩa và clock. Ghi phân bố qua lần lặp; phân biệt delay và rise time, tránh cộng trùng filter/actuator effects. |
| `independent_body_speed_reference_and_uncertainty` | Object `{method,frame,rate_hz,uncertainty_m_s,sync,files}` | Camera/mốc khoảng cách đã hiệu chuẩn, external tracker, hoặc localization độc lập đã đánh giá. Odometry chỉ từ encoder không độc lập; tích phân IMU đơn thuần trôi. Không có reference thì null. |

## 7. sensors_and_clocks — mounting, tín hiệu và thời gian

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `imu_mount_position_orientation_base_frame` | Object `{frame,parent_frame,position_m:[x,y,z],rpy_rad:[r,p,y],source}` | Đo vị trí/hướng lắp IMU, so với TF/URDF đang dùng. Ghi rõ đó là pose của IMU trong base; TF khai báo chưa chứng minh lắp đúng. |
| `imu_axes_sign_units_verified_method` | Object `{verified,method,observations,files}` | Datasheet/driver conversion + đối chiếu hướng lắp/động tác đã biết khi được phép. Gyro rad/s và accel m/s² theo message contract phải đối chiếu thực; đứng yên chỉ hỗ trợ một phần. |
| `imu_acceleration_includes_gravity` | Boolean hoặc null | Đọc documentation/driver pipeline, đối chiếu norm vector đứng yên. Gần g là gợi ý có gravity, gần zero là gợi ý đã bù; bias/filter/frame có thể ảnh hưởng, không chỉ dựa một sample để kết luận. |
| `imu_sample_rate_filter_range_saturation_noise_bias` | Object `{hardware_rate_hz,publish_rate_hz,filter,accel_range_m_s2,gyro_range_rad_s,bias,noise,method}` | Hardware settings/driver docs cho sample rate, filter và range; bag đứng yên cho mean/std mỗi trục, duration và conditions. Ghi gravity handling: accel mean chứa gravity không tự là bias. Quan sát clipping và driver flag nếu có. |
| `lidar_mount_frame_scan_rate_time_increment` | Object `{frame,position_m,rpy_rad,scan_rate_hz,time_increment_s,source}` | Đo mount + TF; LaserScan header/scan_time/time_increment và timestamp bag cho rate. LiDAR spinning scan không phải mọi beam đo cùng lúc; zero time_increment chưa chứng minh scan tức thời. |
| `timestamp_source_per_driver_and_clock_domain` | Object theo driver `{source,clock_domain,conversion,evidence}` | Code/docs phân biệt hardware timestamp, firmware monotonic, ROS host/system hoặc receipt time; ghi translation/sync nếu có. Header tồn tại không chứng minh timestamp tại thời điểm đo. |
| `hosts_clock_sync_method_offset_uncertainty_s` | Object theo host/pair `{method,offset_s,uncertainty_s,evidence}` | NTP/chrony/PTP status/report nếu có. Cờ synchronized không cho biết offset bằng 0 hoặc uncertainty cụ thể. Nếu chỉ một Pi, vẫn cần xét hardware clock mapping của sensor. |
| `video_or_external_tracker_time_sync_method_uncertainty_s` | Object `{method,offset_s,uncertainty_s,frame_rate_hz,files}` | Mốc đồng bộ quan sát được ở cả hai nguồn hoặc hardware/software sync đã kiểm tra. Ghi FPS/timing uncertainty; timestamp bắt đầu file/video hoặc vỗ tay không tự bảo đảm sub-frame accuracy. Không dùng video thì null. |
| `independent_pose_localization_limitations` | Object `{method,frame,inputs,error_estimate,limitations,evidence}` | Mô tả AMCL/SLAM/tracker và input nào độc lập encoder, điều kiện tường/map và sai số đối chứng. Từ covariance topic không tự kết luận accuracy thật; LiDAR corridor có thể suy giảm quan sát dọc hành lang. |

## 8. power — nguồn điện

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `pi_supply_rated_V_A_and_cable` | Object `{model,rated_V,rated_A,cable,evidence}` | Nhãn bộ nguồn/USB power negotiation nếu có, loại/chiều dài dây. Phân biệt rated capability với điện áp/dòng thực tại Pi. Không điền 5A chỉ vì Pi cần cấu hình nguồn phù hợp. |
| `motor_supply_rated_V_A` | Object `{model,rated_V,rated_A,battery_details,evidence}` | Nhãn power supply/battery/controller + cấu hình motor. C-rate/Ah không phải dòng đang đo; ghi unit rõ. |
| `power_topology_shared_ground_isolation` | Object hoặc chuỗi kèm sơ đồ/file | Vẽ Pi/motor/battery/DC-DC/USB/hub/ground kết nối thực; mô tả shared rail, isolation, motor regenerating path nếu đã biết. Không suy cách nối chỉ từ cáp USB nhìn ngoài. |
| `voltage_current_idle_and_under_load_measurement` | Object `{channels,phases,summary,raw_files,method,uncertainty}` | Battery/driver telemetry có calibration hoặc đồng hồ/logger phù hợp. Tách Pi rail và motor rail, idle/khởi động/tải; giữ min/max/time series khi có. Kênh không đo được vẫn null; phần mềm Pi không tự đo mọi rail. |
| `battery_state_of_charge` | Object `{fraction,method,uncertainty,time}` hoặc null | BMS/fuel gauge hoặc phép ước lượng đã biết. Fraction 0..1; điện áp đơn lẻ chưa đủ suy SOC chính xác khi tải/chemistry khác. Dùng nguồn ngoài không pin thì null + ghi not applicable. |
| `undervoltage_fix_and_verification_evidence` | Object `{observed_issue,change,verification,logs,resolved}` | Lưu warning trước/sau, nguồn/dây đã thay nếu có, hwmon/kernel/get_throttled và đo rail liên quan. `resolved:true` chỉ với bằng chứng phù hợp; không có log không tự bằng đã sửa, bit lịch sử không tự là alarm hiện tại. |
| `temperature_cooling_and_throttling_evidence` | Object `{sensor,temperature_C,cooling,throttle_flags,logs,conditions}` | hwmon/thermal/driver/battery theo sensor có tên, audit snapshots và điều kiện tải/thời gian. Mẫu nguội lúc đứng yên không chứng minh không throttle khi chạy. |

## 9. scenario — điều kiện của lần thu

Phiên đứng yên/sàn sạch không có obstacle thì để các trường vật cản/contact
là null và ghi not applicable; không nhập height=0 như đã đo vật cản.

| Trường | Kiểu cần | Lấy từ đâu / cách điền |
|---|---|---|
| `surface_material_condition_slope` | Object `{material,condition,slope_rad,method,evidence}` | Mô tả sàn bê tông/gạch…, khô/ướt/bụi, ảnh; slope từ dụng cụ phù hợp. Không khẳng định slope=0 chỉ vì nhìn phẳng. |
| `friction_measurement_or_proxy_method` | Object `{method,results,conditions,limitations}` | Nếu thật sự cần thì dùng phép đo đã xác định mô hình hoặc proxy lực kéo/khả năng lăn. Lực cản caster/rolling không tự bằng hệ số Coulomb friction. Không có phép đo thì null, không lấy µ từ Gazebo. |
| `route_id_start_goal_and_approach` | Object `{route_id,frame,start,goal,approach_description}` | Route thực đã định nghĩa; pose `[x,y,yaw]` phải có frame/đơn vị. Đứng yên có thể chỉ ghi mô tả vị trí và chưa có goal. Nav2 goal và map lưu cùng phiên; không chép E1 simulator như tuyến thật. |
| `obstacle_id_rigid_cable_soft_wire_groove_or_pothole` | Object `{id,type,description}` | Gán ID vật cản thật, phân biệt rigid ridge/cáp mềm/groove/pothole. Đọc/quan sát vật thể; model cylinder trong sim không chứng minh dây thật cứng. |
| `obstacle_height_depth_width_length_radius_m` | Object `{height_m,depth_m,width_m,length_m,radius_m,method}` | Thước/thước cặp/profile đo vật thể. Với pothole dùng depth, vật lồi dùng height; chiều không áp dụng để null. Ghi biến thiên/độ lún nếu có. |
| `obstacle_edge_profile_angle_rad_and_spacing_m` | Object `{edge_profile,angle_rad,angle_reference,spacing_m,method}` | Ảnh/profile mép + đo góc so với trục approach đã khai báo. Spacing có thể là list khi nhiều vật; một vật không có spacing thì null. |
| `material_attachment_and_compliance` | Object `{material,attachment,compliance,evidence}` | Mô tả cao su/nhựa/kim loại/dây mềm, cố định hay tự do, biến dạng quan sát được. Stiffness N/m chỉ điền khi đã có phép đo thích hợp, không suy từ cảm giác tay. |
| `approach_pose_speed_payload_and_caster_state` | Object `{pose,frame,speed_m_s,payload,caster_state,evidence}` | Bag + reference độc lập/video trước tiếp xúc; tách commanded speed khỏi body speed đo. Caster state chưa quan sát được để null. |
| `video_file_contact_order_and_event_times` | Object `{files,time_origin,sync,events,uncertainty_s}` | Events là list có component, event type, time_s và evidence. Video bị che/không phân giải được contact thì ghi unknown; không suy contact force từ video. Không có video để null. |
| `arrival_stall_tracking_crossing_failure_or_stop` | Object `{outcome,arrival,stall,crossing_success,stop_reason,tracking,method,evidence}` | Điền sau thử theo định nghĩa đã chốt và reference vật lý. Phiên đứng yên không được ghi arrival=true hoặc crossing_success=true. Giữ failure, abort, timeout và missing riêng, không chỉ báo successful runs. |
| `stop_settling_duration_s` | Số | Thời gian thực đã ghi/quan sát robot đứng yên sau stop, theo tiêu chí và clock đã nêu. Thời gian dự định ghi chưa phải thời gian quan sát. |
| `dataset_split_development_or_held_out_test` | Chuỗi | `development`, `validation`, `held_out_test` hoặc `unassigned`. Chốt trước khi dùng để chọn tham số; dữ liệu đã xem/tune không tự đổi nhãn thành unseen test. |
| `paired_run_group_and_repetition` | Object `{group_id,controller,repeat,order,matching_conditions}` | Ghi thiết kế ghép cặp, repeat là integer, actual order và điều kiện giữ cố định. Chạy gần nhau không tự có cùng trạng thái caster/contact. Phiên inventory có thể null. |

## 10. Lệnh chỉ đọc để tìm thông tin ban đầu trên Pi

Source ROS và workspace driver thật trước. Dùng tên topic/node thực mà audit
đã tìm; các tên dưới là mặc định, không bảo đảm driver của bạn đã cung cấp.

```bash
source /opt/ros/jazzy/setup.bash
cat /proc/device-tree/model
free -h
date -u +'%Y-%m-%dT%H:%M:%SZ'
timedatectl show -p NTPSynchronized
ros2 node list
ros2 topic list -t
ros2 topic info /cmd_vel --verbose
ros2 topic info /joint_states --verbose
ros2 topic echo /joint_states --once
ros2 topic echo /imu/data --once --qos-reliability best_effort
ros2 topic echo /scan --once --qos-reliability best_effort
```

Rate quan sát (timeout chỉ kết thúc lấy mẫu, thường trả exit code 124):

```bash
timeout 8s ros2 topic hz /imu/data
timeout 8s ros2 topic hz /joint_states
timeout 8s ros2 topic hz /scan
```

Không có message sẽ chờ đến timeout; không tự kết luận driver chưa cài.
Publication rate khác hardware sampling/PI rate. Header age khác host không
phải latency đã hiệu chuẩn. Đọc cấu trúc message mà không cần phát lệnh:

```bash
ros2 interface show sensor_msgs/msg/JointState
ros2 interface show sensor_msgs/msg/Imu
ros2 interface show sensor_msgs/msg/LaserScan
ros2 interface show nav_msgs/msg/Odometry
```

Driver config/gains: dùng node thật từ audit để list/get hoặc dump parameter
chỉ đọc; ghi đúng file parameter của phiên. Không publish lệnh hoặc set gain
trong lúc chỉ kiểm kê. Không chia sẻ secret nếu parameter dump chứa chúng.

Audit có sẵn lưu nhiều dữ liệu này và power evidence:

```bash
export PYTHONPATH="$HOME/nino_data_tools/src/nino_pi${PYTHONPATH:+:$PYTHONPATH}"
/usr/bin/python3 -m nino_pi.hardware_audit \
  --duration 30 --output "$HOME/nino_audits/inventory_$(date +%Y%m%d_%H%M%S)"
```

## 11. Ví dụ cấu trúc và nguồn bằng chứng

Đây là **ví dụ hình thức**, không phải phép đo Nino. Điền phần đã biết và giữ
unknown; không lấy số simulation để làm đầy form.

```json
{
  "wheel_radius_unloaded_m_left_right": {"left": null, "right": null},
  "payload_mass_kg_and_position_m": {
    "mass_kg": null, "position_m": null, "frame": "base_link", "method": null
  },
  "command_watchdog_s_and_verified_behavior": {
    "timeout_s": null, "location": null, "configured_behavior": null,
    "verified": null, "evidence": null
  },
  "measurement_method_uncertainty": {
    "wheel_radius_unloaded_m_left_right": {
      "source": null, "instrument": null, "uncertainty_m": null, "evidence": null
    }
  }
}
```

Có thể cập nhật bản metadata sau khi xem log, nhưng giữ bản gốc và ghi phiên
bản bổ sung riêng (ví dụ `session.annotated.json`), không ghi đè file trong
dataset đã hash. Các kết quả post-run phải có evidence; không sửa điều kiện
thử nghiệm hồi tố để tạo cảm giác đã biết trước.

## 12. Tạo bản session đứng yên từ template, giữ unknown

Chạy trên Pi sau khi kiểm tra clock. Command này **chỉ tạo file JSON**, không
mở ROS node và không gửi lệnh motor. Đổi operator/robot ID bằng thông tin thực
sau khi tạo nếu muốn; chưa biết vẫn null.

```bash
/usr/bin/python3 - <<'PY'
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

template = Path.home() / 'nino_data_tools/src/nino_pi/config/real_session.template.json'
session = json.loads(template.read_text())
now = datetime.now(timezone.utc)
session['session_id'] = 'stationary_' + now.strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:8]
session['date_utc'] = now.isoformat()
session['test_stage'] = 'stationary_inventory_no_motion_requested'
session['notes'] = 'Initial stationary inventory. Unknown values remain null; no motion test requested.'
directory = Path.home() / 'nino_collection_config'
directory.mkdir(parents=True, exist_ok=True)
output = directory / (session['session_id'] + '.json')
with output.open('x') as stream:
    json.dump(session, stream, indent=2, ensure_ascii=False, allow_nan=False)
    stream.write('\n')
print(output)
PY
```

Sau đó truyền đường dẫn file mới vào `collect_real_data --session ...`.
Collector không tự xác minh thông số thủ công và không suy chúng từ bag.
