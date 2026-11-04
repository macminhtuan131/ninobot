# Hướng nghiên cứu Nino: baseline vận tốc, SysID và residual có giới hạn

> **Cập nhật 04/11 — [History / Governor / TD3 / GUI v5](NINO_RESIDUAL_IMPLEMENTATION_2026-11-04.md):** đã có environment chạy, optimizer smoke TD3/PPO, portable actor và kiểm ROS/Gazebo fixture. Xem tab **Xây project** để kiểm artifact hiện hành. Train nghiên cứu và learned residual trên robot vẫn chưa mở; dữ liệu thật chưa được thu thêm trong cập nhật này. Các mục có ngày trước bên dưới giữ bối cảnh lịch sử.

**Quyết định ngày 03/11/2026.** Đây là kế hoạch và phần mềm chuẩn bị offline,
không phải kết quả TD3, cấp ngân sách training, hoặc xác nhận Pi đang sẵn sàng.
Tài liệu này ưu tiên hơn định hướng cũ trong README và các review cùng ngày.
Kết quả, ledger, checkpoint và protocol đã đóng vẫn là lịch sử độc lập.

Quy ước: **[N]** bằng chứng Nino; **[T]** nguồn ngoài; **[S]** suy luận;
**[Đ]** đề xuất chưa kiểm chứng. Snapshot dữ liệu thật vẫn đến 02/11/2026.

## 1. Chốt cách tiếp cận

**[Đ] Câu hỏi chính:** một phần bù vận tốc bánh có giới hạn, dùng IMU,
encoder và lịch sử lệnh, có cải thiện tracking/chất lượng chuyển động so với
baseline cổ điển công bằng trong operating envelope đã đo không?

Ưu tiên theo thứ tự: **motion contract → đối chiếu wheel/body → SysID →
baseline cổ điển → so sánh residual trong sim → shadow → hardware giới hạn**.
TD3 với MLP và frame history là ứng viên chính; PPO là đối chứng học cùng
contract. SAC chỉ mở khi có lý do thực nghiệm. Không gắn tên “H-TD3” cho
frame stacking hoặc tuyên bố TD3 đã tốt hơn PPO trên Nino.

**[N]** Dự án đã có nền sim/contact, governor và acquisition; real inventory,
trục IMU thô, dấu Z và một số command/wheel traces đã được review.
Hai phiên có người vận hành báo tiến rồi tự dừng; một phiên khác có final
command/feedback tăng nhưng người vận hành báo không tiến. Chưa có bộ độ lặp
ba lượt đạt hoặc body-speed/slip reference độc lập đã kiểm chứng.
Xem [hồ sơ dữ liệu](NINO_REAL_DATA_STATUS_2026-11-03.md).

**[S]** Vì vậy đầu tư nhận dạng đường lệnh–bánh–thân có giá trị hơn huấn luyện
thêm ngay. Việc bổ sung GUI và contract không làm tăng mức trưởng thành
controller hoặc số phiên thật đã thành công.

## 2. Tổng hợp hai báo cáo và correction

| Nội dung | Quyết định / giới hạn bằng chứng |
|---|---|
| Residual thay policy toàn quyền | [Đ] Giữ như giả thuyết; B0/B1 phải đủ mạnh, cùng shaping và limits |
| TD3 cho action liên tục | [T/Đ] Có cơ sở thuật toán; chưa có so sánh Nino công bằng |
| STM32 PI/PWM 500 Hz | [N] Không áp dụng mặc định: source velocity path gửi SPD_REF qua CAN cho CyberGear; binary, internal PI/rate chưa readback đủ |
| IMU/encoder 100–200 Hz hoặc delay số cố định | [N] Phiên inventory quan sát khoảng 47,13 Hz; LiDAR khoảng 6,95 Hz. Đề xuất rate/latency không biến thành số đo |
| State 300D/preview hiện hành | [N] Là contract lịch sử theo profile/checkpoint, không đại diện mặc định governor proprioceptive |
| History 3–4 hay 5 frame | [Đ] Chọn một ABI 20×5=100 để chuẩn bị, sau đó ablation; chưa có bằng chứng K=5 tối ưu |
| Replay dùng action sau shield | [S] Phải định nghĩa MDP: ABI này coi projection là một phần environment; replay SB3 giữ proposal, trace lưu accepted/final/target riêng |
| Trọng số reward, seed count, số mẫu, ngưỡng % | [Đ] Chỉ là đề xuất; chưa chấp nhận làm gate hay ngân sách mới |
| Chạy thẳng/quay/tròn/S/vật cản ngay | [Đ] Là các thiết kế sau; diagnostic hiện tại không tự cấp các thao tác đó |
| RL giải thích governor survey thất bại | [N] Survey PI/reactive không có PPO chạy đồng thời; không dùng xung đột PPO để giải thích kết quả này |

Hai attachment gốc được ghi hash trong `project_evidence.json`, kèm phạm vi
truy cập. Không tự biến citation trong attachment thành công trình đã đọc.

## 3. Kiến trúc và baseline

```text
teleop / path follower → B0 hoặc B1 → nominal body (v, omega)
                                    ↓
                residual common/diff → reference projection
                                    ↓
                  shaping / Collision Monitor → final ROS reference
                                    ↓
                      STM32 arbitration → motor velocity backend

raw IMU / encoder / command history → actor (deployable)
sim GT / contact / external body reference → reward, labels, evaluation
```

**[Đ] B0:** backend velocity hiện có + giới hạn/ramp chung.
**B1:** B0 + feedback yaw/heading đơn giản khi có estimator/reference thích
hợp. Tuning chỉ dùng development set và cùng budget/limits. B1 không được
dùng GT mà residual actor không được dùng; oracle đặc quyền báo riêng.
Đối chứng gồm baseline chậm/time-matched nếu chất lượng đổi do chậm đi.

**[N]** Pi wheel PI xuất torque trong sim và velocity loop bên trong motor
thật là hai backend khác nhau. Không copy gain hoặc chồng velocity PI trên
Pi vào motor velocity mode. Governor state machine giữ làm baseline/nhánh
cơ chế riêng; chưa ghép governor và residual cùng toàn quyền điều khiển.

**[Đ]** Ngay lúc này hardware residual authority **0**; không deploy actor.
Collision Monitor, ownership, watchdog và nút dừng vật lý không bị bypass.
Mất GUI/SSH chỉ dẫn tới yêu cầu đóng process/zero; không chứng minh xe đã dừng.

## 4. ABI nghiên cứu mới, tách checkpoint lịch sử

`nino_residual_velocity_v1`, source
[`residual_velocity.py`](../src/nino_control/nino_control/residual_velocity.py).
Đây là pure core offline, không tạo ROS publisher.

| Nhóm feature | Số | Ý nghĩa |
|---|---:|---|
| baseline v, omega | 2 | Requested baseline, m/s và rad/s |
| raw wheel L/R | 2 | rad/s, mapping/freshness phải hợp lệ |
| body gyro XYZ; accel XYZ | 6 | rad/s; m/s² còn gravity, không giả thành body velocity |
| last observed final ROS v/omega | 2 | Không phải actuator target |
| previous policy proposal common/diff | 2 | Chuẩn hóa [-1,1] |
| previous accepted reference correction common/diff | 2 | Sau projection/rate limit; khác proposal |
| IMU/wheel receipt age | 2 | s, không thay source clock uncertainty |
| nominal yaw consistency; wheel asymmetry | 2 | Proxy dùng geometry danh nghĩa, không là slip |

**[Đ]** 20 feature × 5 frame, oldest→newest; 10 Hz đề xuất nên span 0,4 s,
không phải 0,5 s. Fixed normalization lưu theo contract/checkpoint; clipping
là preprocessing, không bảo đảm physical bounds. Epoch/reset/source change,
duplicate/reversed timestamp hoặc gap phải reset history và refill. Padding
tensor không được coi là năm mẫu thật. Không thêm GT pose/contact/caster,
terrain preview hoặc target chế tạo từ `/cmd_vel` vào actor.

Action chuẩn hóa `(c,d)` tạo phần bù wheel-linear `(c-d,c+d)` m/s, **không**
rad/s, torque hoặc PWM. L1 scaling giới hạn từng bánh; authority alpha và
residual bound được ghi trace. Với full track `b`:
`v=(uL+uR)/2`, `omega=(uR-uL)/b`.
Geometry `.060/.345` trong YAML là danh nghĩa, chưa hiệu chuẩn.

Projection giới hạn reference wheel/body, wheel acceleration và freshness;
history chưa đủ thì baseline only. Baseline zero không tạo locomotion từ
residual. Permission/freshness/fault không hợp lệ → zero và latch, không
minimum-forward/recovery tự động. Latch cần epoch/reset rõ; không tự rearm.
Đây là reference contract, **không phải chứng nhận an toàn**.

Log bắt buộc phân biệt:

1. baseline và **policy proposal**;
2. phần bù đề xuất và **accepted reference** sau projection;
3. **final ROS command** sau toàn bộ shaping/monitor;
4. **actual actuator target** nếu thực sự readback được; thiếu giữ `null`;
5. measured/reported wheel, body reference, intervention reason và các clock.

**[S] Replay:** ở environment composite này transition nhận proposal rồi
project. SB3 lưu proposal tương ứng transition; accepted/final nằm trong info
và trace. Đổi replay thành executed action mà vẫn bootstrap một proposal
policy tạo contract khác và phải thiết kế lại critic/target. Không sửa replay
SB3 bằng câu khuyến nghị chung của báo cáo.

[`residual_experiment.py`](../src/nino_rl/nino_rl/residual_experiment.py) chuẩn
bị contract, reward labels, Gym adapter interface và model factory.
**Chưa có backend Gazebo/ROS implement contract được xác nhận**, chưa chạy
training. `prepare_residual` chỉ xuất JSON; legacy `train.py` từ chối YAML
mới để tránh vô tình dùng env/checkpoint torque cũ. PPO/TD3 có parameters
riêng; mặc định training disabled, budget null, authority zero. Full training
runner và adapter thật chỉ mở ở R5 sau protocol/budget mới.

## 5. Dữ liệu cần ở mỗi tầng

| Tầng / claim | Đã có | Cần tiếp / không được kết luận |
|---|---|---|
| Inventory/sign | [N] Raw, bridge comparison, axes và dấu Z | Không lặp sign vô hạn. Kiểm live freshness/owner khi khởi động |
| Command→reported wheel | [N] Một số waveform, ACK và STOP traces | [Đ] Diagnostic có video bánh/thân/mốc sàn để giải thích no-motion conflict; không tự gọi encoder là body |
| Body/SysID | Chưa có reference định lượng đã kiểm | [Đ] Reference đồng bộ, displacement/speed uncertainty, geometry/load/caster/block; endpoint tape chỉ displacement |
| Residual/PPO/TD3 | Chưa có real residual dataset | [Đ] ABI/hash/features/history/proposal/accepted/final/target distinct, failures và grouped split |

`stm32_usb_collection.json` là inventory profile; không yêu cầu full Nav2,
`/scan` deskew hoặc fused `/odom`. Profile diagnostic riêng yêu cầu raw IMU,
motor feedback/status, source→selected→smoothed→final, enable, scan_raw và
mounting TF. Event command/enable chỉ cần xuất hiện khi thao tác tương ứng;
không phát giả để đủ recorder-ready. Target/current/mode tùy driver cung
cấp; thiếu không suy từ lệnh vận tốc. Optional research topics chưa tồn tại
không làm phiên hiện tại fail và không được tự tạo cho đủ schema.

Source header, bag receipt và monotonic time lưu riêng. Twist không header
chỉ cho receipt timing, không execution latency. Source gaps/freshness/
coverage phải đánh giá theo window; rate quan sát không phải bandwidth thật.
Video thường hỗ trợ quan sát; muốn body speed/slip cần calibration và sync
uncertainty. LiDAR scan matching là estimator có failure mode, không tự là GT.

## 6. Lộ trình tối đa sáu giai đoạn

| Giai đoạn | Việc / artifact | Gate / khi fail |
|---|---|---|
| 1 · R0–R1 | GUI workflow, một diagnostic nguyên profile + raw/video/trace/QC | Final input hợp lệ và wheel/body được đối chiếu. Không tiến/STOP/fault/thiếu raw → unknown, giữ dữ liệu; không retry tự động |
| 2 · R2–R3 | Protocol độ lặp riêng và body reference; SysID command→wheel→body, estimate lag/ramp/geometry có uncertainty | Identifiable trên development và kiểm held-out; nếu không, dùng combined model/giảm claim, không fit mọi tham số cùng lúc |
| 3 · R4 | B0/B1 tuned công bằng, Pareto time/tracking/quality, envelope cơ khí | Cổ điển đủ ứng dụng thì dừng learning; negative obstacles/dây mềm có envelope riêng |
| 4 · R5 | Adapter sim mới, contract validation, TD3/PPO same inputs/actions/limits/reward và fixed budget | Reward sanity/model discrepancy/held-out split đạt; chưa đủ thì không train diện rộng |
| 5 · R6 | History/alpha/domain-randomization ablation, OOD, shadow zero authority | Có benefit và useful authority trong envelope (H2 riêng cho claim contact); không có thì bỏ predictor/residual, ưu tiên shaping/route memory |
| 6 · R7 | Demo hardware giới hạn đã chốt, latency/ownership/stop/body metrics | Protocol deployment riêng; không suy alpha/tốc độ từ số trong YAML sim |

Assistant làm offline: schema/core/config, GUI, QC, protocol, phân tích raw
đã có. Người vận hành: nguồn/RC/stop, vùng thử, video và explicit motion click.
Reference/body, actual stop, backlash/caster và sim-to-real cần dữ liệu thật;
không thay chúng bằng thêm software tests.

### Tối đa ba thí nghiệm tiếp theo

**E1 — một diagnostic wheel/body, chi phí thấp.** Một arm, đúng một lượt
mới; không dùng các slot cũ. +0,05 m/s, ramp0,10 m/s², source2s, bag60s.
Giữ sàn/tải/pose; ghi caster unknown nếu chưa biết. Video thấy bánh, thân,
mốc sàn và mốc đồng bộ. Primary reported-wheel window và source support
theo contract hiện có; body chỉ claim theo chất lượng reference. Pass narrow:
raw đóng/hash/required valid, actual input có support, không STOP/confound và
quan sát giải thích được. Lỗi/không tiến/bất đồng → unknown, giữ phiên; tối đa
một correction có nguyên nhân được chứng minh trước một protocol mới, không
auto retry. Q2 không đóng E1 physical gate.

**E2 — độ lặp + reference, phụ thuộc E1.** Đề xuất tối đa ba lượt independent
reset/pose, cùng profile, mỗi lượt review trước lượt tiếp; protocol chưa mở.
Ưu tiên reference video có calibration/sync; no-motion/intervention giữ thành
failure, không đổi objective. Report từng L/R, giữa-lượt range và uncertainty,
body displacement/stop chỉ khi đủ reference. Ba lượt là pilot, không đủ power
để khẳng định equivalence/safety; không dùng CV/asym threshold ngoài làm gate.
Không fit radius/lag/slip đồng thời từ một input2s thiếu excitation.

**E3 — classical feasibility hoặc contact authority, phụ thuộc E2.** Chọn
**một** câu hỏi sau model fit: B0/B1 tracking trên sàn sạch, hoặc H2 sau first
contact trong sim có matched backend. Đề xuất 2 arm × 2 block × 2 repeats =
tối đa8 lượt cho screen, thứ tự counterbalanced; budget chưa cấp. Giữ payload,
route, limits và measurement; primary/meaningful effect phải khóa trước.
H1 predictor chỉ mở nếu H2 còn horizon hữu ích; H3 cần baseline/time-matched
và held-out riêng. Hiệu ứng nhỏ/grid-sensitive → unknown hoặc ưu tiên cổ điển;
không tăng sample size, bỏ spike, đổi metric hoặc mở curriculum tự động.

## 7. Quyết định từng nhánh và đóng góp

| Nhánh | Quyết định |
|---|---|
| Reactive governor | Giữ frozen làm comparator; chưa promote/deploy |
| Rough PPO/BC, action torque cũ | Giữ kết quả/checkpoint lịch sử; tạm dừng training |
| TD3 residual velocity | Chuẩn bị ABI/API offline; chưa train/flash/hardware |
| PPO mới | Comparator cùng ABI; không so return giữa reward khác |
| SAC / recurrent / predictor/MPC | Chưa ưu tiên; cần lý do vượt baseline đơn giản |
| Optuna | Giữ cho bounded classical tuning development; không tự mở search |
| Observation history | K5 proposal, validity explicit; ablation sau, không nhồi feature |
| Sim map/curriculum | Tái sử dụng sau, không coi nhiều layout config là generalization |
| Acquisition | Giữ raw/clock/provenance và failure; dừng audit khi đủ claim hiện tại |
| Navigation / route memory | Dự phòng khi first-contact quá muộn; phải có localization uncertainty |
| GUI software authority | Advanced opt-in, firmware chưa live validated; collector chính dùng RC hiện có |
| Laya | Theo dõi, không realtime motor controller |

**[Đ] Đóng góp có thể bảo vệ:** benchmark/contract đo wheel–body dưới reference
projection và partial observability trên robot nhỏ; hoặc residual chỉ cho
phase còn authority. Tính mới thuật toán hiện **chưa đủ cơ sở**. TD3, residual
RL, frame stacking và system ID đều đã có; giới hạn phần cứng/caster không tự
tạo novelty. Phải tìm phản chứng và so paper gần nhất trước claim công bố.

**[T]** TD3 xử lý overestimation/function approximation bằng clipped double
critics, delayed policy updates và target smoothing; điều này không chứng minh
khả năng vượt cáp hay superiority trên Nino. [Fujimoto et al., ICML2018](https://arxiv.org/abs/1802.09477).
SB3 TD3 chuẩn nhận continuous Box và không hỗ trợ recurrent policy sẵn có;
MLP history là frame stacking. [SB3 TD3 documentation](https://stable-baselines3.readthedocs.io/en/master/modules/td3.html).
Rover case trong bản v3 của Omi2026 là simulation-based, không là thực nghiệm
caster/cáp Nino. [Bài gốc](https://arxiv.org/abs/2307.15931v3).
WHILL/AWSIM/Bayesian ID là bài toán và cơ chế khác, không xác nhận H2 contact
Nino. [Bài gốc/abstract](https://arxiv.org/abs/2609.28969).
Ngày kiểm nguồn03/11/2026; không thực hiện lại full systematic literature review
trong đợt sửa phần mềm này, không xác nhận mọi citation của hai attachment.

## 8. Việc ngay và điều kiện đổi ý

**Một diagnostic có video đối chiếu bánh/thân/mốc sàn qua GUI v4** là bước
ưu tiên, sau khi inventory/owner/scene live hợp lệ. Artifact: rawbag60s,
metadata/hash, source/final/wheel trace, QC và operator observation, video
riêng với mốc đồng bộ. Nếu wheel/body vẫn bất đồng thì dừng cấp motion pilot
mới và giải thích backend/mapping/reference. Nếu classical baseline đã đủ
nhu cầu thì kết thúc nhánh learning. Nếu H2 không còn horizon hữu ích, ưu tiên
preview từ memory/shaping/cơ khí thay vì predictor sau contact.
