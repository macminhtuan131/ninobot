# Contract software của slowdown v4

Module là `nino_rl.recovery_v4_contract`. Config là `src/nino_rl/config/recovery_v4.yaml`. Contract ID là `nino_recovery_slowdown_v4_software_contract`, schema phiên bản 1 của phần contract software này.

Trạng thái phát hành là `software_contract_only`. Module không tạo actor observation, Gym environment, replay buffer, ROS publisher hoặc learner. `require_release` từ chối các yêu cầu Gazebo, optimizer và hardware. Contract này chưa thay thế campaign v3 hoặc GUI hiện có.

## Action và projection

| Đại lượng | Ngữ nghĩa |
|---|---|
| Proposed action | Một float trong [-1, 1], cũng là action replay dự kiến |
| `NEUTRAL_ACTION` | -1, yêu cầu slowdown bằng zero |
| Action 0 | Yêu cầu nửa slowdown tối đa |
| Action +1 | Yêu cầu slowdown tối đa |
| Requested slowdown | `max_slowdown_m_s * (action+1)/2`, giữ nguyên trước giới hạn tốc độ khả dụng |
| Accepted slowdown | Phần giảm common speed thực được projector chấp nhận, trong [0, max] |
| Final body reference | Reference vận tốc, chưa phải wheel feedback hoặc body motion đo được |

`project_slowdown(settings, state, nominal_body_reference, action, dt_s, health)` trả `ProjectionResult` có `next_state`. Hàm không mutate input. `nominal_body_reference` là tuple gồm v và yaw rate. Build đầu yêu cầu hai bánh không quay lùi; không phát hành reverse hoặc quay tại chỗ bằng hai bánh ngược chiều.

`ProjectionState` chứa reference bánh nominal trước, reference bánh final trước và latch. Nominal được shape độc lập với actor action. Khi feasible, projector giữ differential của nominal đã shape và chỉ giảm common speed. Nó giới hạn wheel speed và slew; health STOP có thể vượt giới hạn slew của reference. Điều đó không phải chứng nhận quãng dừng vật lý.

Các reference limit trong YAML giữ giá trị sim đã dùng trước đó, gồm wheel speed 0,4 m/s, forward limit 0,4 m/s, yaw limit 0,5 rad/s, slew 0,1 m/s² và separation 0,34273666 m. Max slowdown 0,02 m/s giữ authority sim trước. Các số này không là cấu hình motor thật được chấp nhận.

`Health` yêu cầu permission, emergency stop, fault, tuổi IMU, tuổi encoder, tuổi command và số frame thật của history. Health không hợp lệ hoặc control interval vượt 0,15 s làm latch STOP. Sensor hợp lệ nhưng chưa đủ năm frame chỉ cho baseline và `learning_eligible=False`. Dùng `ProjectionState()` mới để bắt đầu epoch mới; tự khôi phục freshness không gỡ latch.

`ProjectionState.to_dict()` cùng `from_dict(..., settings)` hỗ trợ JSON round-trip và từ chối state không hợp lệ. Kiểm này chỉ chứng minh tái dựng phần nhớ của projector. Dynamics của robot vẫn có state ẩn.

## Mission reference

`MissionReference.target(elapsed_s, route_progress_m)` dùng luật spatial protocol cố định, gồm startup ramp, cruise và approach về endpoint. Hàm không nhận actor action hoặc accepted command. Cùng progress và mission time cho cùng target.

Luật hiện dùng startup acceleration 0,1 m/s², cruise 0,2 m/s, route length 4 m, approach distance 0,4 m và deadline 40 s. Approach distance là đề xuất software mới, chưa có rollout qualification. Hai controller ở progress khác nhau có thể có target khác theo thời gian.

Progress phải do adapter sau này tính từ phép chiếu lên route thẳng. Module này nhận label progress đã tính, không xác nhận source, contact hoặc geometry. Target evaluation có thể dùng progress từ body truth; actor phải dùng estimate deployable. Cần ghi cả nguồn và luật reference khi nối environment.

## Reward và outcome

`score_reward(settings, state, labels)` trả state mới, total, các term và end flags. Input phải hữu hạn và clock tăng. Output reward vô hạn bị từ chối trước khi trả transition.

`RewardState` lưu high-water đã thấy và phần đã được credit riêng. Progress ngoài corridor không được credit và không được nhận bù khi quay lại cùng vị trí. Tiến–lùi trong vùng đã đi qua không thu lại reward tiến độ. Đây là objective có state, không phải chứng minh potential shaping bất biến policy.

Các term gồm progress chuẩn hóa theo route length; cost cross-track, heading, speed error và thời gian; accepted slowdown fraction; tích phân bình phương đạo hàm accepted fraction; stability cost; terminal outcome. Không có clearance hoặc recovery bonus. Weight còn là đề xuất software, chưa tối ưu.

Accepted action cost dùng mức slowdown đã chấp nhận, không dùng bình phương affine actor action. Neutral request có thể còn slew tail từ reference trước; cost phản ánh tail thực đó.

`RewardLabels` phải đến từ scorer đã kiểm measurement. Pure reducer không xác nhận robot tới đích hay dừng thật. Khi nối environment cần giữ physical success, source QC và continuous quiet từ backend, không tạo success bằng requested command.

| `EndReason` | Kết quả |
|---|---|
| `ONGOING` | Transition hợp lệ, chưa kết thúc |
| `SUCCESS` | Terminated, không bootstrap |
| `PHYSICAL_FAILURE` | Terminated, không bootstrap |
| `INTRINSIC_DEADLINE` | Terminated, không bootstrap |
| `EXTERNAL_SAMPLING` | Truncated, có thể bootstrap với next observation hợp lệ |
| `CAMPAIGN_CUTOFF` | Truncated, không ghi thành physical failure |
| `INVALID_SOURCE` | Không tạo reward transition |

Deadline nội tại được ưu tiên khi trùng external cutoff. Success sau deadline bị từ chối. Đã kết thúc episode thì scorer yêu cầu reset trước khi nhận label mới. Actor adapter cho nhiệm vụ hữu hạn phải biểu diễn thời gian còn lại; hiện `state_metadata` mới cung cấp metadata đó.

## Identity và cấu hình

`load_config` yêu cầu đúng key và type, không nhận placeholder, null, key trùng hoặc field ngoài schema. Config có một `learning_rate`; không nhận alias actor hoặc critic learning rate độc lập chưa thực thi.

`identity` chứa config hash, implementation hash và hash các mô tả action, projection, reward, observation spec. `observation_spec_sha256` là hash mô tả metadata cần cho adapter tương lai, không có nghĩa đã tạo actor tensor mới. `require_identity` từ chối mọi mismatch, gồm identity v3.

Không relabel hoặc resume replay v3 sang v4. Giai đoạn environment và training cần identity mới cho feature, normalization, backend, bank, split và runtime package version.

## Kiểm executable

Chạy từ root repository.

```bash
rtk env PYTHONPATH=src/nino_rl:src/nino_control .venv/bin/python -m pytest -q src/nino_rl/test/test_recovery_v4_contract.py src/nino_rl/test/test_review_recovery_v4.py
```

Kết quả lượt 19/11 được lưu trong workspace đánh giá tại `artifacts/recovery_v4_report_review_20261119`, gồm test XML, script `verify_contract.py`, trace và receipt software. Các case dùng synthetic labels. Số case software không phải số lượt vượt gờ hoặc số episode TD3 đã học.

## Điều kiện nối vào training

Environment v4 phải tạo observation có causal history thật, reset warmup riêng, khai báo observation space đúng và kiểm đủ state cần cho projection. Runner cần physical source QC, invalid-transition rejection, close/reset và split provenance. Sau đó cần qualification deterministic trong Gazebo trước optimizer smoke.

GUI chỉ nên thêm v4 train khi runner và identity tương ứng hoạt động. Bản sửa này giữ GUI dùng v3 hiện tại; không gắn v4 vào engine 100D cũ bằng đổi tên profile.
