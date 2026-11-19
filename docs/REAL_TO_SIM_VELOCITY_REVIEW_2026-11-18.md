# Dữ liệu velocity thật và replay đối chiếu Sim

## Quyết định

Đã kết nối read-only Pi `d@192.168.0.112`, đối chiếu host key với robot trước,
và trích xuất sáu phiên Nav2 velocity ngày 17/11. Dữ liệu phục vụ nhận dạng
command-to-reported-wheel và replay kiểm tra Sim. Không đưa teleop, PI torque
hoặc SAC torque vào replay buffer TD3.

Chưa chấp nhận hệ số fit để sửa physics. Delay tốt nhất nằm ở biên tìm kiếm
0 s của cả hai bánh. Mô hình bánh trái dự đoán kém hơn đối chứng ở một trong
hai phiên giữ lại. Điều này không chứng minh motor không có delay hoặc bánh
trái có một hằng số cơ học cố định.

Campaign TD3 50k ngày 17/11 đã lỗi ở **2.922 transitions** do
`Startup source gap or tail exceeds bound: wheel`. Checkpoint boundary cuối
được giữ tại `~/nino_research/recovery100_train50k_20261117_01/checkpoints/step_002922_3f8d812f`.
Không coi campaign này hoàn tất 50k. Lượt đối chiếu dưới đây không resume nó.

## Dữ liệu đã kiểm

Inventory hiện tại có 66 thư mục phiên trong các root đã tìm. Chưa thấy thư mục
ngày 18/11. Audit đầy đủ ngày 17/11 ghi 61 SQLite bags và 5 thư mục JSONL.
Trong 61 bags có 53 đọc được và có metadata, 3 đọc được nhưng thiếu metadata,
5 lỗi SQLite. Đóng bag đủ không đồng nghĩa đạt chất lượng thí nghiệm.

Audit trước có 327/327 file hashes được khai báo ở vùng legacy và 816/816
hash config snapshot ở vùng mới khớp. 816 hashes không phải checksum raw bags.
Ngày 18/11 kiểm mới sáu raw bags dưới đây bằng SQLite integrity và SHA256
trước/sau trích xuất. Không sửa bag, reindex, bật motor hoặc phát lệnh trên Pi.

| Phiên ngày 17/11 | Vai trò đã định trước | Kết quả kiểm dữ liệu |
|---|---|---|
| `120235_ry42tV` | Fit | 1.334 cặp command/wheel hợp lệ |
| `121346_5eVAXV` | Fit | 2.377 cặp hợp lệ |
| `121720_h1RvN8` | Fit dự kiến | Loại toàn phiên khỏi fit do command gap 4,125 s; giữ diagnostic |
| `122123_NbHSXj` | Fit | 1.229 cặp hợp lệ |
| `122526_OwllD9` | Holdout | 1.297 cặp hợp lệ; dùng làm input replay Gazebo |
| `122752_FYBrKr` | Holdout | 1.321 cặp hợp lệ |

Mỗi session ID đầy đủ có tiền tố `20261117_`. Source trên Pi nằm trong
`/home/d/nino-real-test/runs/nav_only/<session>/rosbag/rosbag_0.db3`.

Ghép causal as-of `/cmd_vel` vào thời điểm receipt của `/motor_fb`. Chỉ chấp
nhận tuổi lệnh tối đa 150 ms và không có khoảng trống nội bộ sau ghép.
Không nội suy wheel feedback hoặc tạo target telemetry. Các mẫu biên chưa
có lệnh hoặc sau khi luồng lệnh kết thúc được đếm riêng trong metadata.
Không chọn holdout hoặc loại phiên theo kết quả fit.

Twist không có header thực thi. Delay ở đây bao gồm transport, shaping,
receipt scheduling và dynamics chưa tách được. Nguồn stamp được kiểm riêng,
không dùng như thể đã đồng bộ với thời điểm motor thực thi.

## Kết quả nhận dạng mô tả

Geometry dùng đổi body reference sang wheel reference là số khai báo thật
`radius_l=radius_r=0,060 m`, `separation=0,345 m`. Đây chưa phải calibration
bán kính lăn hoặc wheel separation hiệu dụng.

| Bánh | Gain fit | Tau fit | Delay fit | RMSE holdout 122526 | RMSE holdout 122752 |
|---|---:|---:|---:|---:|---:|
| Trái | 0,9416 | 0,1155 s | 0 s, biên | 0,3113 rad/s | 0,6331 rad/s |
| Phải | 0,9952 | 0,0300 s | 0 s, biên | 0,2262 rad/s | 0,3662 rad/s |

Đối chứng danh nghĩa là wheel reference tức thời tính từ cùng final ROS
reference. RMSE trái của đối chứng là 0,2485 và 0,6945 rad/s; phải là
0,2381 và 0,3709 rad/s. Mô hình trái tệ hơn khoảng 25,3% ở holdout đầu.
Không dùng mô hình này làm hiệu chỉnh đã được xác nhận hoặc CI giữa các
thử độc lập. Sàn/tải/caster không có annotation đủ để nhận dạng riêng.

## Phần đã nối vào Sim

`nino_rl.real_velocity_replay` tạo CSV SI units, metadata, quality từng phiên,
kết quả fit và lịch replay từ nguồn thật. Lịch 278 references ở 10 Hz dùng
causal command tại `t`, so feedback thật tại `t+0,1 s` với feedback Sim cuối
bước đó. Mẫu thật có tuổi ghi rõ; không lấy mẫu tương lai.

`nino_rl.real_velocity_sim` chạy lịch đó trên clean-floor world của recovery,
dùng RealReferenceBackend kế thừa RecoveryBackend và EpisodeLifecycle hiện có. Giữ clock dependency pin,
source guard từ epoch sau settle, PI, torque cap, ramp và observer độc lập. Một lượt tối đa 350
steps, wall deadline 600 s, một launch, không tự retry. Không load actor TD3.

Đây là replay cùng reference, không phải cùng trạng thái vật lý/caster và
không phải rollout closed-loop Nav2. Backend replay không chạy goal follower;
nguồn command duy nhất là lịch reference đã đóng băng. Follower training
không thay đổi. Sim dùng nominal radius 0,0625 m
và separation khoảng 0,3427 m. Chênh geometry được ghi riêng trong result.
Không thêm một vòng velocity PI trên firmware thật hoặc copy gain xuống motor.

Artifacts tại máy phát triển:

- `~/nino_research/real_velocity_sysid_20261118_02` chứa dataset, fit,
  schedule và registry có input SHA256.
- `~/nino_research/real_velocity_sim_inputs_20261118_05` chứa bank/pins mới.
- `~/nino_research/real_velocity_gazebo_replay_20261118_04` chứa replay hiện tại.
- Replay `_01` được giữ với lỗi serialization reset trước bước chuyển động.
- Replay `_02` được giữ với 123 steps và lỗi follower corridor. Raw ghi
  `Outside declared guidance corridor/overshoot`. Tuyến Nav2 thật không phải
  tuyến recovery thẳng 4 m; backend replay riêng đã loại phụ thuộc follower
  khỏi phép đo wheel response, giữ source/drive/physics guards.
- Replay `_03` không phát forward, lỗi startup wheel gap 68 ms tại
  `0,022..0,090 s`, trước task epoch. Raw được giữ. Đây tái hiện gate đang
  chặn campaign 50k; chưa chứng minh nguyên nhân publisher hay discovery.

Diagnostic cuối dùng contract `post_settle_wheel_response_v1`. Xe phải settle
với drive ACK và physical quiet như cũ. Cửa sổ đo bắt đầu sau settle, không
tái dựng pose từ lúc spawn hoặc dùng estimated pose làm command/score.
Nguồn task vẫn phải qua guard 40 ms và PI control gap tối đa 4 ms. Startup
journal vẫn giữ, không nội suy hoặc vá mẫu thiếu. Contract này không làm
checkpoint/campaign recovery vượt gate startup và không được dùng thay
contract training có follower. Việc tách epoch dựa trên claim wheel-response
hẹp hơn, không phải chấp nhận khoảng trống cho pose reconstruction.
- Workspace `artifacts/real_to_sim_20261118` chứa exporter read-only,
  JSON trích xuất, inventory và host key đã xác minh.

## Kết quả replay Gazebo đã đóng

Lượt `_04` hoàn tất 278/278 bước, tương ứng 27,8 s Sim. Sau khi bỏ phần
đầu dưới 1 s, còn 269 cặp để so. Không có actor, optimizer hoặc thao tác
phần cứng. Lifecycle và observer độc lập đều đóng sạch.

| Đại lượng | Trái | Phải |
|---|---:|---:|
| RMSE Sim so với reported wheel thật | 0,34784 rad/s | 0,33252 rad/s |
| Mean Sim trừ reported wheel thật | -0,11793 rad/s | -0,11784 rad/s |

QC source trong task đạt. Giữ 13.907 wheel samples và 1.391 mẫu cho từng
kênh IMU/truth/drive. Max source gap wheel 2 ms, các kênh còn lại 20 ms.
Kiểm lại 37/37 manifest hashes và 278/278 cặp reference với drive ACK khớp.
16 software tests của dataset/replay và residual integration đạt.

Đồ thị đối chiếu và `verification.json` nằm trong workspace artifact
`artifacts/real_to_sim_20261118/replay_review/`. Đồ thị giữ các spike thật.
Feedback thật có transient khi đổi yaw và cuối lượt mà Sim danh nghĩa chưa
tái hiện đầy đủ. Chưa có ngưỡng RMSE được chấp nhận để gọi đây là model match.

**Quyết định hiện tại.** Nối real data ở tầng diagnostic replay/validation,
giữ physics danh nghĩa. Không promote mô hình first-order đang không đạt
đối chứng nhất quán trên holdout. Dataset, source hashes và lịch replay đã
sẵn để so riêng từng candidate sau này. Không gộp các phiên lỗi hoặc torque
để tăng số mẫu của velocity SysID.

**Ưu tiên tiếp theo cho Sim.** Trước khi resume một campaign 50k, phân biệt
nguyên nhân startup wheel gap đã tái hiện ở `_03` bằng primary/independent
journal và lifecycle publisher. Không dùng replay post-settle để tuyên bố
gate training đã qua. Với hiệu chỉnh motor, thí nghiệm tiếp theo cần các lượt
tiến-dừng lặp lại cùng điều kiện để tách transient khỏi thay đổi yaw/owner;
chưa cần thêm bài obstacle thật chỉ để fit response velocity này.

## Giới hạn trước khi gọi Sim đã hiệu chỉnh robot thật

- IMU mounting trong config 17/11 là identity và translation zero, khác yaw
  +90 độ cùng XYZ được kiểm ngày 27/10. Chưa dùng accel XYZ để sửa noise hoặc
  reward body vibration của Sim khi xung đột này còn mở.
- Encoder odometry, `/odom` fused và AMCL không phải body ground truth độc lập.
  Chưa suy ra slip, ma sát contact, body latency hoặc stopping distance.
- Các phiên PI torque/SAC có contract khác. Không gộp với velocity dataset.
- Cáp mềm, gờ, hõm và dốc thật chưa được kiểm bằng các phiên sàn này.
- Profile fit đang là candidate, chưa được loader training tự áp dụng.
- Đây là log closed-loop navigation với excitation không được thiết kế riêng.
  Kết quả fit là mô tả dự đoán theo session, chưa xác lập nhân quả motor.

## Các quyết định triển khai

Áp dụng **Model the Domain** bằng cách tách velocity dataset, diagnostic replay
và training contract. Replay post-settle không thể được hiểu là qualification
cho startup pose reconstruction của TD3 recovery.

Áp dụng **Build the Lever** bằng exporter, module chuẩn bị dataset và runner
replay có thể chạy lại. Áp dụng **Prove It Works** bằng đọc raw bag, đối chiếu
SHA256, kiểm trực tiếp drive ACK và source coverage trong Gazebo. Không dùng
software tests thay cho lượt physics hoặc coi fit là calibration đã đạt.

## Tái lập

Từ repo đã source ROS Jazzy và install overlay, tạo output mới cho mỗi lượt.
Giữ nguyên dữ liệu và kết quả cũ.

```bash
PYTHONPATH=src/nino_rl:src/nino_control:$PYTHONPATH .venv/bin/python -B \
  -m nino_rl.real_velocity_replay --export /path/to/velocity_export.json \
  --output /path/to/new_sysid_output

PYTHONPATH=src/nino_rl:src/nino_control:$PYTHONPATH .venv/bin/python -B \
  -m nino_rl.recovery_runner prepare --output /path/to/new_bank_root

PYTHONPATH=src/nino_rl:src/nino_control:$PYTHONPATH .venv/bin/python -B \
  -m nino_rl.real_velocity_sim --schedule /path/to/new_sysid_output/sim_replay.json \
  --bank /path/to/new_bank_root --output /path/to/new_replay_output
```

Khi thay implementation, source pins của bank cũ sẽ bị từ chối. Đây là kiểm
truy xuất nguồn gốc, không phải lý do bỏ kiểm hash hoặc dùng lại epoch cũ.
