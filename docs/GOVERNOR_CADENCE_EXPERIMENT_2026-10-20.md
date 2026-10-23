# Thí nghiệm cadence governor: 100 ms và 20 ms

**Cập nhật thực thi 20/10: đã cấp release và chạy 9/12 attempts, dừng do
measurement hard stop tại attempt 9.** Cả chín đến đích/dừng ổn định;
slots 10–12 chưa chạy và không được retry/resume. Xem
[kết quả thực thi](GOVERNOR_CADENCE_RESULT_2026-10-20.md).
Ngưỡng giảm slip 10% / tăng thời gian 0,5 giây vẫn là đề xuất, không áp dụng.
Nội dung dưới đây lưu thiết kế và trạng thái **trước khi chạy**; không coi
snapshot offline là bằng chứng chất lượng governor đã xác nhận.

## 1. Câu hỏi cần trả lời

Governor cập nhật nhanh hơn có phát lệnh sớm hơn và tạo **thay đổi vận tốc
thân/bánh thực trước các contact tiếp theo**, đồng thời cải thiện trade-off
rung, slip và thời gian hay không?

Khảo sát cũ cho thấy lệnh giảm đầu tiên ở tick đầu sau contact, khoảng
74–84 ms ở input và 82–98 ms ở drive publication. Vì vậy kiểm tra cadence
có căn cứ hơn việc tự tăng penalty hoặc sửa recovery. Tuy nhiên:

- Confirmation vẫn **40 ms**, không đổi thành một frame 20 ms.
- Ramp vẫn **0,4 scale/giây**: bước tối đa 0,04 ở 100 ms và 0,008 ở 20 ms.
  Bước đầu nhỏ hơn và lượng tử hóa thời gian có thể làm mất lợi thế phát hiện
  sớm. Không chỉnh ramp hoặc confirmation để buộc ứng viên nhanh hơn.
- Caster contact sớm có thể vẫn xảy ra trước đáp ứng motor. Không tuyên bố
  tránh được first impact bằng IMU/encoder.

## 2. Ba controller và những gì giữ cố định

| Thành phần | PI cố định | Governor tham chiếu | Governor nhanh |
|---|---:|---:|---:|
| Arm | `full` | `reactive_100ms` | `reactive_20ms` |
| Governor decision period | 100 ms, profile full | 100 ms | 20 ms |
| Environment/scoring/history step | 100 ms | 100 ms | 100 ms |
| Path follower/reference update | 100 ms | 100 ms | 100 ms |
| Physics integration | 1 ms | 1 ms | 1 ms |
| World transaction chunk | 20 ms | 20 ms | 20 ms |
| IMU observation window | 100 ms¹ | 100 ms | 100 ms sliding |
| Target-acceleration lookback | 100 ms¹ | 100 ms | 100 ms |

¹ Profile full vẫn chạy core để có telemetry; không giảm scale theo detector.

**World transaction chunk không phải physics timestep.** Cả ba arm dùng
cùng cách chia 100 physics steps thành năm giao dịch 20 steps. Điều này
tránh so sánh controller nhanh với một lịch pause/ROS transaction khác.
Source/reference cập nhật governor 100 ms giữ nguyên hành vi mặc định,
nhưng các episode mới không được gọi là replay tất định của khảo sát cũ.

Giữ nguyên robot/caster, wheel PI, gain/integrator, torque/rate/speed limits,
IMU/encoder/LiDAR, geometry và estimator từ bundle 18/10. Fixed E1, cruise
0,4 m/s, một capsule cứng 6 mm tại x=3,10 m, góc +8°, sàn box, robot hash
giống reference. Không thêm terrain hoặc randomization trong screen này.

Các thông số governor giữ nguyên: target 0,90; ramp 0,4/s; hold min 0,8 s,
max 1,0 s **mỗi lần trigger**; startup 0,8 s; quiet 0,3 s; confirmation 0,04 s;
delay 0; ngưỡng detector và vertical-only setting không đổi. Rearming giữ
nguyên, kể cả khả năng retrigger khi đang HOLD. Bộ lọc giữ time constant
cũ; khác biệt rời rạc hóa theo dt là một phần giả thuyết cadence, không phải
thử nghiệm chỉ riêng transport latency lý tưởng.

## 3. Triển khai không đổi clock chấm điểm

- Không đổi `control_hz: 10.0`, deadline, số bước tối đa hoặc physics dt.
- `governor.cadence_experiment` chỉ bật trên arm nhanh. Tick tại đầu và
  +20/+40/+60/+80 ms của mỗi action; +100 ms thuộc action kế tiếp.
- Path follower giữ cùng tham chiếu trong 100 ms; chỉ speed governor điều
  chỉnh scale của v/omega. Vẫn một nguồn phát motion command.
- Native slip snapshot, trajectory, IMU score integration và episode counters
  vẫn chạy **một lần mỗi 100 ms**, không cộng năm rolling windows vào score.
- Coarse `control_trace.csv` giữ input-boundary đầu action, không ghi đè bằng
  tick +80 ms. Mọi tick nhanh vào **`governor_update_trace.csv`** riêng và
  topic state đã có; không suy ra 50 Hz actions từ trace 10 Hz.
- IMU RMS/peak tại tick nhanh dùng cửa sổ 100 ms vừa qua. Target acceleration
  dùng target history cách 100 ms, không vô tình rút xuống 20 ms.
- Input đầu giữ empty IMU summary như baseline; target history warmup dưới
  100 ms được gắn cờ, nằm trước startup 800 ms. Reset xóa toàn bộ history;
  không tái dùng dữ liệu trước reset. Thiếu/stale/future feedback dừng với
  zero motion reference; không tự advance thêm hoặc retry.

Các thay đổi runtime đều opt-in, có snapshot source trước/sau. Bài kiểm tra
so sánh core mặc định với source 18/10 cho kết quả giống hệt trên 400 frame;
AST guard giữ nguyên đoạn native scoring và đường `_governor_command` cũ
sau nhánh opt-in. Điều này kiểm tra tương thích phần mềm, chưa chứng minh
ROS/Gazebo integration hoặc chất lượng vật lý của arm mới.

## 4. Schedule cố định — tối đa 12 attempts

Hai seed block **77600/77601**, mỗi block hai triad lặp. Mỗi triad đủ ba
controller; mỗi attempt cold start riêng. Seed là nhãn lần chạy, không phải
hai geometry mới hoặc khôi phục cùng trạng thái caster/contact.

| Attempt | Seed | Lặp | Arm |
|---:|---:|---:|---|
| 1 | 77600 | 1 | full |
| 2 | 77600 | 1 | reactive_20ms |
| 3 | 77600 | 1 | reactive_100ms |
| 4 | 77601 | 1 | full |
| 5 | 77601 | 1 | reactive_100ms |
| 6 | 77601 | 1 | reactive_20ms |
| 7 | 77601 | 2 | reactive_100ms |
| 8 | 77601 | 2 | full |
| 9 | 77601 | 2 | reactive_20ms |
| 10 | 77600 | 2 | reactive_20ms |
| 11 | 77600 | 2 | reactive_100ms |
| 12 | 77600 | 2 | full |

Thứ tự sinh bằng RNG cố định 20261020, mỗi arm có bốn lượt; số lần xuất hiện
ở từng vị trí triad là 1/1/2. Với bốn triad không thể chia đều ba vị trí;
không tuyên bố cân bằng order tuyệt đối. Không retry, replacement, resume
hoặc smoke episode riêng. Các lượt đầu kiểm tra integration **trong 12 slots**.

Giữ gate sau reset: zero, yên liên tục 0,5 s, tối đa 5 sim seconds, không
reset thử lại. Giữ đo dừng 2 sim seconds sau arrival. Ledger và authorization
snapshot được ghi bền vững trước launch; claim theo protocol hash không cho
chạy lại cùng budget bằng cách copy/đổi tên release. Chỉ cleanup process sở hữu.

## 5. Phân tích khóa trước dữ liệu

Ba contrast: nhanh − tham chiếu, tham chiếu − PI, nhanh − PI. Ghép theo seed
**và** repeat: bốn cặp mỗi contrast. Giữ 12 slots, mọi failure, missing và spike.

- Arrival, stall/timeout, stop, physical tracking và thời gian.
- Slip/rung toàn tuyến, post-contact, crossing và toàn chuỗi contact–recovery.
  Native metric và fixed post-contact `[first manifold +50 ms, +3 s]` giữ nguyên.
- GT timestamp gốc, joint interpolation, clipping/coverage/quadrature và grid
  sensitivity cũ giữ nguyên. Không chọn grid hoặc subset thuận lợi.
- Dùng full micro-command trace để kiểm tra input → drive receipt/publication
  → wheel targets. Đối chiếu body/joint theo timestamp nhân quả trước command
  và trước manifold tiếp theo có tải. Command sớm hơn không tự bằng motor hay
  body response sớm hơn; một contact dip có trước lệnh không được quy cho lệnh.
- Cửa sổ trước can thiệp của mỗi contrast kết thúc ở offset can thiệp sớm nhất
  của **cả hai arm**, tính từ first contact riêng. Vẫn giữ nguyên quadrature;
  nếu interpolation support vượt qua command thì gắn cờ contaminated, không
  lén cắt metric hoặc gọi đó là causal negative control.
- First 50 ms chỉ là fixed diagnostic: với arm nhanh nó có thể đã chứa can
  thiệp, nên không mặc định là negative control.
- Bootstrap 10.000 draws, RNG 20261020, resample **nguyên triad** trong block,
  hai block bằng trọng số; cùng draws cho mọi contrast/metric. Chỉ hai triad
  mỗi block nên CI mô tả, không bảo đảm power/coverage. Thiếu required pair thì
  estimand/CI unavailable; không lấy mean riêng các lượt thành công.

Executor kiểm tra đúng năm micro-updates mỗi action nhanh, cửa sổ quan sát,
sensor ages, không future lookup và scoring interval 100 ms. Native replay và
provenance giữ nguyên. Setup/sensor/cadence/physics/cleanup fault gây hard stop;
failure nhiệm vụ thông thường vẫn được giữ, không thay lượt.

Sau 12 attempts dừng. Kết quả trái chiều hoặc chưa phân biệt được phải báo
chưa đủ bằng chứng; không mở thêm pilot, tuning, predictor hoặc PPO. Không có
time-matched PI trong budget này nên chưa xác lập lợi ích ngoài tác động đi
chậm hoặc H3. Phần robot thật tiếp tục hold.

## 6. Artifacts và kiểm tra hiện tại

- [Protocol + schedule](governor_cadence_experiment_2026-10-20/protocol.json).
- [Manifest](governor_cadence_experiment_2026-10-20/prepared_manifest.json).
- Ba config tại `governor_cadence_experiment_2026-10-20/inputs/`.
- [Kết quả kiểm tra offline](governor_cadence_experiment_2026-10-20/verification.json).
- [Dry run tổng hợp](governor_cadence_experiment_2026-10-20/offline_dry_run/summary.json):
  **12 synthetic adapter calls, 0 simulation launches**. Không phải 12 episode
  vật lý hoặc bằng chứng governor có ích.

**39 tests đạt**, gồm production step-prefix với fake IO cho cả ba arm:
100 physics steps/score interval, năm world chunks chung, một governor
decision ở full/reference và năm ở fast; không tick kép tại 100 ms. Có test
legacy core, scoring invariants, fixed feature windows, confirmation/ramp,
reset/missing/stale/future, full trace, failure retention, hard stop, ledger,
budget/release pending và CI missing-data. ROS environment imports đã kiểm
tra mà không tạo node/simulator. Live integration chưa được xác nhận.

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/prepare_governor_cadence_experiment.py \
  --validate docs/governor_cadence_experiment_2026-10-20
```

Lệnh kiểm tra trên không chạy simulation. Runner mặc định chỉ chạy tổng hợp;
live mode đòi release 12 attempts riêng khớp protocol hash. Chưa tạo release.
Source runtime mới có hash khác snapshot 18/10; không dùng lại release 16
attempts cũ. Dữ liệu và điểm khảo sát cũ không bị ghi lại.

Đính chính liên quan audit trước: attempts 8 và 10 có hai event bên trong một
vùng HOLD liên tục; đã sửa câu “không retrigger” trong báo cáo 20/10. Không
đổi integral, metric, biên pha hoặc cấu hình rearming từ đính chính này.
