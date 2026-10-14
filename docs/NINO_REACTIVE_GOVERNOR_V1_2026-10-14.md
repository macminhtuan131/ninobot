# Nino reactive speed governor v1 — 14/10/2026

## Phạm vi

Governor phản ứng theo IMU/encoder và lệnh đã thực thi, xây theo kết luận
Deep Research: kiểm tra H2 trước predictor. Bản này không có risk predictor,
không train PPO, không mở Optuna và chưa được hiệu chuẩn/kiểm chứng trên robot
thật. Threshold/profile bên dưới là điểm bắt đầu thí nghiệm, không là giới
hạn vận hành được chứng nhận.

## Thành phần đã xây

- `nino_control/governor_core.py`: thuật toán thuần Python, không nhận pose,
  tọa độ vật cản, preview, ground truth hoặc contact oracle.
- `nino_control/speed_governor.py`: ROS node độc lập, không cần Torch/SB3.
- `nino_rl/governor_adapter.py`: chỉ chuyển các field sensor/drive hợp lệ vào
  core khi đánh giá PI trong lockstep.
- `nino_rl/governor_logger.py`: logger nghiên cứu riêng cho IMU, joints,
  drive diagnostics, odometry, ground truth và contact của bốn bánh/caster,
  hai bracket và chassis. Tránh giả định wheel contact luôn là first contact.
- `factory_floor_governor.launch.py`: world một vật cản, contact system
  nạp từ đầu world, contact bridge và logger. Không chạy ROS governor node
  đồng thời: evaluator trực tiếp gọi cùng core theo nhịp lockstep.
- Pi command stack có tùy chọn `governor:=true`: governor thay velocity
  smoother, output vẫn qua Collision Monitor. Mặc định cũ giữ nguyên.

## Thuật toán và tín hiệu

`CRUISE → HOLD → RECOVER → CRUISE`, thêm `STALL` tùy chọn và `FAILSAFE`.

Detector kết hợp vertical acceleration đã xử lý gravity/tilt, RMS/peak trong
khoảng quan sát, gyro x/y và sai lệch wheel-target so với encoder. Threshold
wheel error tăng khi wheel target đang đổi nhanh để giảm nhầm motor lag với
disturbance. Cơ chế này chưa phải model flat-floor response được nhận dạng;
cần negative controls tăng tốc/phanh/quay trên sàn sạch để hiệu chỉnh.

Trigger phải qua confirmation; dùng threshold thấp hơn để xác định quiet.
Hold có thời gian tối thiểu, thời gian tối đa và kiểm tra scale đã đạt target.
Rearm sau một khoảng quiet, không phụ thuộc phải đạt cruise 0.98. Recovery
đưa scale về 1.0. Zero reference không bị minimum-forward ghi đè.

Wheel stall chỉ nhận ra khi command tiến còn có nhưng hai bánh gần dừng.
Bánh quay mà thân đứng yên **không được giả vờ đo được** từ proxy này.
Evaluator vẫn chấm tiến triển/đến đích bằng pose vật lý độc lập. Mặc định
wheel stall kéo dài dẫn tới FAILSAFE. Profile minimum-forward tùy chọn bị
giới hạn scale/thời gian, chưa bật vì chưa có envelope vượt được xác nhận.

## Hai chế độ thực thi

### A. Gazebo/PI screening

Core chạy đồng bộ với `NinoGazeboEnv.step`, hiện 10 Hz. Input chỉ lấy từ
IMU/encoder/drive feedback; RMS/peak là dữ liệu khoảng action trước. Scale
được áp vào cả v và omega. V2 scale gửi xuống là 1.0, residual torque bằng 0;
launch mới còn đặt `accept_torque:=false` để tránh scale/residual lần hai.
Giới hạn wheel acceleration và torque rate của PI vẫn giữ nguyên.

Reference freshness dùng timestamp mô phỏng trong contract mới, tránh việc
render/service wall time khi physics đang pause làm reference giả stale.
Fresh-callback barriers, action clock checks và physical scoring vẫn còn.
Governor FAILSAFE được ghi thành task failure, không biến thành success.

### B. ROS node/Pi

Node mặc định disabled, publish 20 Hz; cần IMU và `/nino_drive/diagnostics`
đúng schema của effort driver, với wheel targets/actual velocity và command
sau scale. Hardware driver khác phải có adapter phản hồi tương đương.
`sim_time_s` trong schema là thời gian ROS: thời gian thật khi use_sim_time=false.
Chưa có adapter CAN/CyberGear hardware được xây trong công việc này.

Trong node, command limiter có giới hạn v/omega và accel/decel. Đây là một
owner của limiting reference; không thêm Nav2 smoother nối tiếp khi chọn
mode governor. Inner wheel/torque protections vẫn độc lập. Output sau node
là command được gửi đi, không phải phép đo vận tốc thân thực; drive diagnostics
và evaluator đo đáp ứng riêng. IMU mount phải căn với base axes như model
hiện tại; mount thật khác cần transform được đo trước khi dùng.

Node kiểm tra sensor timestamp và tuổi callback theo wall clock. Dữ liệu
stale/nonfinite, clock discontinuity hoặc publisher cạnh tranh trên output
đưa về zero/FAILSAFE. Fault có latch: disable → reset → enable, rồi cần lệnh
mới. Watchdog motor và physical e-stop phải hoạt động độc lập.

## Chạy thí nghiệm trên laptop

Đóng simulator/evaluation cũ trước. Build:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-select nino_control nino_description nino_rl nino_pi
source install/setup.bash
export ROS_DOMAIN_ID=80
export NINO_ROS_DOMAIN_ID=80
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_factory_governor_80
```

Terminal A, world một cáp, instrumentation:

```bash
ros2 launch nino_rl factory_floor_governor.launch.py \
  variant:=cable headless:=false \
  config:=src/nino_rl/config/factory_floor_governor_pi_check.yaml \
  output_directory:=rl_runs/governor_contact_lab
```

Terminal B source ROS/.venv/install và đặt cùng bốn biến môi trường, rồi:

```bash
ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/factory_floor_governor_pi_check.yaml \
  --route E1 --episodes 1 --seed 76000 --control-trace \
  --output rl_runs/governor_reactive_E1
```

`variant:=clear` là negative control sàn sạch. `pothole`, `groove`, `threshold`
có world instrumentation riêng. `mixed` dành cho mở rộng sau cơ chế riêng.
Core/evaluator và ROS node là hai owner thay thế nhau: **không chạy cùng lúc**.

Profiles H2 cùng geometry/PI/scoring:

| Config | Sau trigger |
|---|---|
| `factory_floor_governor_full.yaml` | Giữ scale 1.0; vẫn kiểm tra lỗi/wheel stall |
| `factory_floor_governor_moderate.yaml` | Target 0.85, hold rồi recover |
| `factory_floor_governor_deep.yaml` | Target 0.55, hold rồi recover |
| `factory_floor_governor_pulse.yaml` | Target 0.70, pulse ít nhất 1.0 s và đạt target trước recovery |
| `factory_floor_governor_pi_check.yaml` | Reactive target 0.70, quiet-based recovery |

Trước screen, kiểm tra `variant:=clear` khi tăng tốc/phanh/quay để hiệu chỉnh
false trigger. Kiểm tra native hiện tại đã có trigger trước cáp, nên detector
chưa đạt bước này; xem phần kiểm chứng bên dưới.

Sau negative controls, screen đề xuất 12 lượt: bốn profile H2, ba lần lặp/profile, một cáp và cùng
tốc độ tiếp cận. Đổi `--config` và `--output` cho từng profile; có thể dùng
`--seeds 76000 76001 76002`. Các seed không đóng băng Gazebo contact/noise.
Không gọi đây là exact snapshot branching. Đối chiếu trạng thái caster,
approach speed và first impact để phát hiện mismatch giữa reset.

## File kết quả và cách đọc

Evaluator ghi `config.yaml`, `metadata.json`, `episodes.csv`, trajectory
ước lượng/vật lý và `control_trace.csv`/`drive_trace.csv`. Control trace có
phase, scale, trigger ratio, command conditioning threshold, quiet/hold time,
fault và requested/governed command. Failed arrival/failsafe vẫn ở episodes.csv.
Mỗi evaluator có run ID riêng để không trộn các episode số 1 khi dùng cùng
logger cho nhiều profile.

Logger tạo thư mục UTC riêng, không ghi đè:

- `samples.jsonl`: timestamp và payload cảm biến/feedback/contact.
- `contact_events.jsonl`: bắt đầu/kết thúc cặp collision theo component.
- `metadata.json`: counts, code/config/world hashes và trạng thái đóng logger.
- `resolved_config.json` và `world_metadata.json`: provenance.

`complete=true` của logger chỉ nghĩa logger đóng sạch, không nghĩa controller
thành công. Contact plugin chỉ phát message khi có contact; end time từ
message kế tiếp là upper bound, không tự giả định thời điểm tách chính xác.
Force/wrench có thể thiếu; không tính impulse bằng dữ liệu thiếu hoặc đặt 0.
Named-positive annotation hỗ trợ cáp/bump. Pothole/groove cùng floor mesh
cần phân pha bằng vị trí contact và metadata hình học **offline**, không đưa
thông tin đó vào governor. Tất cả oracle chỉ có mặt ở logger/evaluator.

Phân tích dữ liệu đã lưu, không chạy thêm simulation:

```bash
python src/nino_rl/scripts/analyze_governor_experiment.py \
  --evaluation rl_runs/governor_reactive_E1/THU_MUC_EVALUATION \
  --logger rl_runs/governor_contact_lab/THU_MUC_LOGGER
```

Output `governor_analysis.json` giữ failures, coverage/missing-data và timing
first recorded positive contact → HOLD/body slowdown. Horizon 2 s mặc định
chỉ là diagnostic window, cần chốt từ H2 để đánh giá chính thức. Timing có
liên hệ không tự chứng minh slowdown do governor hoặc chất lượng tốt hơn PI.

## Điều kiện đi tiếp

Screen này kiểm tra wiring, response và H2; không tự chứng minh ride quality.
Đo physical contact → sensor trigger → governed command → wheel/body response.
So impact/slip/arrival/time sau contact và toàn route, giữ failures và dữ liệu
thiếu. Nếu effect vượt repeatability và crossing không suy giảm, mới mở rộng
scenario và tune reactive governor. Predictor chỉ làm sau H2 và bằng chứng
history có giá trị chọn action; PPO/Optuna lớn vẫn giữ lại.

## Kiểm chứng đã thực hiện và giới hạn

- **59 tests passed** trong bộ kiểm chứng cuối, gồm state machine, freshness, giới hạn scale,
  observation không có oracle, profile chung physical contract, command owner,
  xacro có 7 contact sensors và parser giữ missing data. Parser không nội suy
  qua khoảng mất IMU quá 0.1 s để tuyên bố coverage đầy đủ.
- ROS wrapper với feedback giả đã kiểm tra HOLD tới 0.70, recovery, bắt xung
  IMU ngắn, stale-data stop, reset và publisher cạnh tranh. Đây là test phần
  mềm, không phải đo đáp ứng motor thật.
- Native Gazebo reactive check chạy 25 bước/2.5 s: scale nhỏ nhất 0.70,
  physical x=0.669 m; sai lệch clock lớn nhất khoảng 8.9e-15 s. Tuy nhiên,
  HOLD bắt đầu khi physical x≈0.215 m, **trước cáp x=2.9 m**. Đây là false
  trigger cần kiểm tra trên sàn sạch, không phải H2 được xác nhận. Bracket và
  chassis không phát contact trong đoạn này; không ghi force/impact giả bằng 0.
- Một episode full-speed reference hoàn tất đánh giá nhưng **rollover** ở
  19.70 s, physical endpoint error≈0.304 m. Failed arrival được giữ nguyên;
  không giảm gate và không quy nguyên nhân cho controller/contact khi chưa
  audit. Run này dùng instrumentation 4 bánh trước bản 7 component cuối.
- Pi command stack được launch trên máy phát triển: governor và command gate
  disabled, Collision Monitor active, không có velocity smoother thứ hai.
  Không có driver/feedback thật; chưa phải validation trên Raspberry Pi.
- Các process kiểm chứng đã đóng. Gazebo báo segfault trong lúc shutdown
  sau check; logger đóng sạch. Lỗi shutdown này còn cần theo dõi, không tính
  thành lỗi crossing hoặc bằng chứng governor tốt hơn.

Bản ghi nhỏ được lưu tại
`docs/governor_implementation_verification_2026-10-14/`; các raw logs lớn
giữ trong `/tmp/nino_governor_*verify/` trên máy hiện tại. Cần archive raw
logs trước khi xóa `/tmp` nếu dùng chúng trong báo cáo nghiên cứu.

**Bước tiếp theo:** hiệu chỉnh detector từ negative controls và audit failed
full-speed reference; sau đó mới chạy screen H2 ghép cặp. Predictor, PPO và
Optuna chưa được chạy bởi triển khai này.

## Nguồn kỹ thuật

Contact system/topic placement theo
[Gazebo Harmonic sensors](https://gazebosim.org/docs/harmonic/sensors/) và
[Contact system source](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/contact/Contact.cc).
Đây là tài liệu instrumentation, không là bằng chứng governor có ích.
