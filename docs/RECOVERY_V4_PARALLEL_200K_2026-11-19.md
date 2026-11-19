# Recovery v4. Hai campaign 200k trên sàn sạch và gờ

## Mục tiêu

Hoàn thiện thiết kế slowdown v4, kiểm nghiệm rồi chạy hai campaign TD3 độc lập,
mỗi campaign có ngân sách 200.000 transition. Đây là nghiên cứu mô phỏng. Một seed
cho mỗi task không phải bằng chứng generalization hoặc kết quả trên robot thật.

## Contract được triển khai

- Runtime ABI `nino_recovery_slowdown_history107_v4`.
- Observation gồm 20 feature qua 5 frame thật, 6 phần tử trạng thái projector,
  và thời gian nhiệm vụ còn lại. IMU và encoder có timestamp. Không có vị trí,
  loại gờ, phase crossing hoặc ground truth trong actor.
- Bốn zero advance trong reset tạo history trước replay. Backend có thêm
  một giây để warmup không cắt ngắn nhiệm vụ 40 giây.
- Actor có một action trong [-1,1]. `-1` trung tính, `0` yêu cầu slowdown
  0,01 m/s, `+1` yêu cầu slowdown 0,02 m/s. Projection quyết định phần chấp nhận.
  Follower sở hữu yaw. Actor không xuất torque hay current.
- Baseline được shape độc lập. Correction cùng chiều hai bánh chỉ giảm tốc,
  giữ yaw sau shaping và chịu giới hạn slew.
- Mission law riêng tạo speed target cho reward và đánh giá. Target không
  phụ thuộc action. Nó phụ thuộc elapsed time và tiến độ thực của trajectory,
  nên các controller không có cùng một target time series tuyệt đối.
- Reward dùng progress high-water trong corridor, tracking, speed, time,
  accepted slowdown, biến thiên slowdown và stability. Không có recovery bonus.
- Replay lưu requested normalized action. Requested, accepted, shaped nominal
  và final reference được ghi riêng. Đổi ABI không cho resume v3.
- Sensor/command stale ở cả đầu và cuối transition bị chặn trước reward/replay.
  Ownership/fault intervention bị quarantine. Physical failure hợp lệ vẫn giữ.
- Deadline nội tại là terminated. Hết ngân sách campaign là truncated, giữ
  next observation thật và bootstrap. Metadata cutoff khớp replay timeout.

Core `recovery_v4_contract.require_release` vẫn chỉ bảo vệ phần pure software.
Release simulator thuộc campaign riêng và đòi receipt Gazebo, source hash,
raw QC, task outcome và closure. Không có release hardware từ các gate này.

## Phân phối và baseline

Bank có 24 layout. Mỗi family có 8 train, 2 tune và 2 heldout, seed tách biệt.
Training hoán vị không hoàn lại trong từng vòng bank, tái lập từ seed/cursor.
Chỉ stage 0 được dùng. Gờ là cylinder cứng đường kính 4–6 mm; vị trí x lấy
trong [0,8; 2,8] m, góc nằm trong cấu hình geometry hiện có. Không phải dây mềm.

Qualification chạy classical action -1, constant action 0 và reactive governor
sensor-only trên một tune layout mỗi family. Không có optimizer update trong
các lượt này. Classical phải đạt task success; mọi arm phải có outcome hợp lệ,
raw source QC và lifecycle đóng sạch. Đây là integration gate, không phải
kiểm định lợi ích của adaptation hoặc toàn bộ bank.

Pothole, mixed và slope chưa được release bởi campaign này.

## Hai job dài

| Trường | Sàn sạch | Gờ cứng nhỏ |
|---|---|---|
| Family | `clean` | `short_obstacle` |
| Training seed | 1511 | 2511 |
| Transition budget | 200.000 | 200.000 |
| Root | `~/nino_research/recovery_v4_clean200k_20261119_02` | `~/nino_research/recovery_v4_obstacle200k_20261119_02` |

TD3 dùng shared learning rate 0,0003, gamma 0,99, tau 0,005, batch 256,
replay 200.000, warmup 1.000, policy delay 2, target noise 0,2, clip 0,5,
exploration std 0,1, MLP [256,256] và một gradient step mỗi transition.
Đây là baseline nghiên cứu chưa tune, không phải bộ tham số tối ưu.

Mỗi job có trần 96 giờ, 2.000 launch và reserve 4 GiB. Giữ một checkpoint
ở episode boundary đầu tiên, boundary đầu sau warmup, các milestone khoảng mỗi 25k, hai boundary
gần nhất và checkpoint cuối/pause. Milestone nằm sau mốc ở boundary gần nhất.
Không ghi checkpoint lớn sau mọi episode.

Raw thành công được archive, kiểm hash rồi giữ lượt đầu theo family cùng hai
lượt gần nhất. Raw failure/censored được giữ; đạt trần raw 512 MiB thì pause,
không âm thầm xóa failure. Compact trace, summary, reset, QC, provenance và
TensorBoard được giữ. Archive pruning có receipt hash.

Source của cả hai job được bind chỉ đọc từ snapshot riêng. Job gờ có network,
IPC, PID namespace, DDS shared memory và simulator lock riêng. Job sạch dùng
host lock. Output, replay, RNG và checkpoint tách riêng. Chỉ writer tổng hợp
đọc hai progress file để tạo `parallel_status.json`.

## Theo dõi và dừng

Trong Studio, vào tab Train TD3 và chọn engine Recovery v4. Combo worker cho
phép chuyển giữa hai job. Global steps và actor/critic counters lấy từ native
`progress.json`. Bản đồ lấy world hash và trace đúng episode; bảng episode và
checkpoint không coi training return là bằng chứng policy tốt hơn baseline.
Đóng GUI không dừng job ngoài GUI.

Để pause một job, tạo file `STOP` trong root tương ứng. Worker chờ terminal
đã lưu, source QC và optimizer boundary rồi lưu checkpoint. Không dùng kill
toàn bộ Gazebo hoặc xóa lock. Resume chỉ bắt đầu episode vật lý mới; model,
optimizer, replay và RNG được khôi phục, không snapshot/restore Gazebo.

Artifact điều phối nằm tại
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_v4_parallel_200k_20261119`.
Đọc `parallel_status.json` và `VERIFICATION.json` để biết số bước quan sát thật.
Ngân sách 200k không có nghĩa đã hoàn thành 200k.

## Kiểm chứng và phạm vi kết luận

- Test hồi quy, stale incoming IMU/wheel/command, stale frame cuối reset,
  action/projection/reward, bank split, cutoff và Studio có artifact JUnit.
- Software smoke 64 transition có 32 critic và 16 actor update.
- Fixture resume so với 600 transition liên tục có policy tensors và replay
  prefix bằng nhau, 568 critic update. Không phải physical bit-exact resume.
- Namespace và source bind được kiểm bằng namespace ID, shared-memory inode,
  private-lock inode và source inode thực trong worker.
- Sau launch phải kiểm native counters của cả hai vượt warmup và có actor/
  critic update, đồng thời kiểm checkpoint boundary đầu và raw QC.

Các con số và receipt cuối được ghi trong `VERIFICATION.json`; không suy
kết quả Gazebo hoặc 200k completion chỉ từ test phần mềm.

Sau campaign, so checkpoint đã chọn trên tune trước, rồi đánh giá frozen trên
heldout cùng classical, constant và governor. Báo task success/failure,
speed RMSE và bias, tracking, elapsed time, intervention và saturation của
requested action riêng với actuator saturation. Chưa promote policy thật từ
return, arrival hoặc việc optimizer chạy thành công.


## Correction trước bàn giao

Generation 1 được giữ nguyên làm bằng chứng. Sàn sạch dừng tại 588 transition
do cộng số thực làm credited progress vượt seen progress 4,34×10⁻¹⁹ m.
Reducer đã clamp kết quả vào seen progress, giữ nguyên guard từ chối trạng
thái đầu vào không hợp lệ. Không tăng tolerance hay đổi reward weight.
Job gờ được pause sạch tại 1.186 transition với checkpoint có 186 critic
và 93 actor update. Không resume hai job này qua source hash mới.

Generation 2 có bank, qualification, source snapshot và output riêng.
243 test hồi quy đạt sau correction. Fixture 600 transition so liên tục với
resume có policy và replay bằng nhau. Review độc lập còn so 2.400 transition
và xác nhận hai optimizer cùng replay bằng nhau. Đây đều là fixture phần mềm.

Hai worker sở hữu progress riêng. Chỉ launcher gờ ghi file tổng hợp, với
pending file có PID riêng. Source bind giữ /dev thật để ROS truy cập
/dev/null và entropy. Isolation và source inode được kiểm ngay trong worker.

## Bản đồ triển khai

| File | Trách nhiệm |
|---|---|
| `recovery_v4_contract.py`, `recovery_v4.yaml` | Pure projection, mission law, reward reducer và ABI có hash |
| `recovery_v4_environment.py` | History thật, observation 107D, action 1D và admission trước replay |
| `recovery_v4_runtime.py` | Ghép lifecycle Gazebo hiện có với contract v4 |
| `recovery_v4_bank.py` | Bank geometry và split train/tune/heldout |
| `recovery_v4_campaign_contract.py` | Budget, readiness và checkpoint inspector |
| `recovery_v4_campaign.py` | Smoke, qualification, training và deterministic evaluation |
| `recovery_campaign.py` | Cơ chế replay, optimizer boundary, checkpoint và retention dùng chung |
| `recovery_v4_studio_contract.py`, `recovery_v4_training_studio.py` | Request và adapter Studio cho v4 |
| `td3_training_panel.py`, `training_live.py` | Chọn worker và native training counters |
| `training_dashboard_data.py` | Đọc trace từng episode, world đúng phiên và compact statistics |

Không chỉnh learning rate, history length hoặc reward weight trong lúc hai
job này chạy. Thay đổi semantics cần source generation và ABI mới.
Sau budget, dùng tune để chọn checkpoint theo protocol đã khóa, rồi heldout
để so classical, constant và governor. Training reward không tự promote model.
