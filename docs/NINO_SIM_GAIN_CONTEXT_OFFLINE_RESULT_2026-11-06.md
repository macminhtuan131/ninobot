# Backend/context gain — parity offline đã đạt

06/11/2026 · **41 software tests đạt; chưa qualification Gazebo hoặc training mới.**

## Đã triển khai

```text
Follower → shared window/projection → /cmd_vel
  → watchdog/ownership của motor backend
  → common gain map duy nhất
  → wheel speed clamp → target ramp → velocity PI → torque/slew limits
  → wheel effort controller trong sim tương lai

Driver pre-map execution reference → last_final trong observation
Gain/effective map/post-limit target → telemetry cho evaluator, không vào actor
```

- `gain_reference_map.py`: chỉ đổi common bằng gain0,98/1/1,02, yaw giữ nguyên
  **trước** limiter từng bánh. Zero/reverse/pure turn có kiểm toán riêng.
- `gain_drive_kernel.py`: bản sao kernel PI frozen; AST đối chiếu xác nhận
  **chỉ một call tạo wheel target** được thay. Không thêm PI vận tốc chồng lên,
  không sửa gain PI/current/torque cap của motor cũ.
- `gain_effort_drive.py`: node chuẩn bị cho **sim domain129/partition/context
  riêng**, gain parameter read-only; giữ watchdog, reset và stop kế thừa.
  Telemetry `/nino_drive/gain_map` tách pre-map/effective/unlimited target/
  post-limit target và flags clip/ramp. Đây là reference/target, không phải
  body-speed hoặc torque đo độc lập.
- `gain_factory_backend.py` và `training_sim_gain.launch.py`: backend/launch
  riêng; tắt node motor cũ khi node gain được dùng. Constructor backend chặn
  mặc định nếu không có quyết định physics rõ ràng từ runner tương lai.
  Chờ gain và drive diagnostics cùng source stamp, age≤40ms; không retry physics.
- `gain_context.py`: context identity mới dù shape vẫn103D/1D/history5. Gain và
  condition chỉ vào evaluator metadata; không chia encoder/last_final cho gain
  để tạo input “đẹp”. Driver diagnostics pre-map giữ ý nghĩa execution-reference,
  chưa là measured motor/body response.

Reference shaping trước map là giới hạn của lệnh yêu cầu; ramp/speed/torque
sau map là giới hạn motor backend. Không gọi effective reference sau map là
requested command không đổi, hoặc gọi target ramp là body acceleration đã đo.

## Bằng chứng phần mềm

| Phép kiểm | Quy mô | Kết quả được phép kết luận |
|---|---:|---|
| Kernel PI thật: cũ và gain1, cùng clock/feedback giả lập | 1.200 callback mỗi kernel | State/effort/diagnostics/odometry bằng nhau chính xác trên chuỗi thử |
| Kernel mới: gain0,98/1/1,02 | 3×1.200 callback | Map chạy một lần khi có feedback; zero/yaw/ramp/speed/torque/slew giữ contract |
| Wrapper thực: B0/fixed classical/causal candidate, gain1 | 3×140 paired decisions =840 old+new transitions | Observation, reward, projection, reference và terminal khớp; context ID khác |
| Faults và leakage | Trong41 tests | Missing/stale/mismatched gain ACK, source lạ, double-map, target/future/ABI drift bị chặn |

**Tổng4.800 callback là software stimulus**, không phải Gazebo physics ticks
hoặc mẫu motor thật. **840 transitions là fixture old/new**, không phải840
eval mới trên Nino/caster. Không load actor/optimizer, `rclpy.init`, ROS node,
world hoặc hardware trong preflight. Các raw/manifest/checkpoint cũ được giữ.

Các lần test đầu có lỗi fixture gọi `super()` trên `SimpleNamespace`; đã sửa
fixture thành instance tạo bằng `__new__` không khởi tạo ROS. Log lỗi giữ
riêng; đó không là failure vận hành robot/Gazebo hoặc bằng chứng sửa physics.

## Phần chưa được chứng minh

- Chưa chạy launch mới: discovery, startup order, service readback, gain-topic
  delivery, reset/closure và tải thêm50Hz telemetry phải qua integration thật
  trong budget qualification. Parity offline không là exact-state Gazebo parity.
- Fixture wrapper gain1 không chứng minh động lực học ở gain0,98/1,02. Phép map
  kernel có kiểm đại số/limit riêng; outcome body của cả ba gain còn thiếu.
- Static gain là reference calibration map giả định, không là motor torque
  constant, traction, payload hoặc tham số CyberGear đã đo trên robot thật.
- Baseline causal hiện vẫn có giả thiết steady/aligned encoder–reference;
  lag/slip/geometry có thể làm estimator sai. Chưa chứng minh lợi ích mới.

## GUI và bước tiếp theo

GUI **Xây project → Nhánh Sim → Bước kế tiếp → Quyết định benchmark** hiển thị
“Offline đạt; Gazebo chưa chạy”, số callback/fixture và nút mở kết quả này.
Không tự mở motor, physics, training hoặc checkpoint resume.

**Việc tiếp theo:** triển khai runner và release riêng theo
[draft qualification baseline](NINO_SIM_GAIN_BASELINE_QUALIFICATION_DRAFT_2026-11-06.md):
tối đa9 fresh launches/1.260 ticks,0actor/optimizer/retry/hardware; gain1 trước,
first cells là integration trong budget. Một failure đóng các slot còn lại.
Chưa có budget train/seeds/holdout mới. Giữ cổ điển cho clear known-stop;
không dùng parity để kết luận TD3 cần thiết hoặc governor đã có ích.

## Artifact

- Root: `~/nino_research/sim_gain_context_preflight_v1/offline_2026_11_06/`.
- Manifest SHA256: `e130108934e4d12da74d802f621156a39da41ed51606607c0d472fda485f2ec4`.
- Context fingerprint: `deccb94680a263042ab4fd688bca7669e79f562602a713f23c4d4dc4243f469f`.
- ABI SHA256: `99e8488b9d2945d967273b2388d107183b14688bbedab5ecdde76b29d5c55219`.
- QA: client workspace `artifacts/sim_gain_context_2026-11-06/`.
- Real-data cutoff vẫn02/11/2026; hardware residual authority vẫnzero.
