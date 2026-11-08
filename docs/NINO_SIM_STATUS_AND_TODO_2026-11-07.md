> **Continuation đã khởi chạy07/11:** user đã chốt một lượt20k→30k, cùng profile/Ki0,10, không warmup mới;6eval cuối. [Trạng thái/log](NINO_COMMON_STUDIO_CONTINUATION_2026-11-07.md). Đoạn “proposal chưa chạy” bên dưới là trước quyết định này.

> **Cập nhật mới07/11 — pilot20k đã hoàn tất:** 20.000transitions,10.000critic/5.000actor updates;6/6eval đạt task/stop. Tốt hơn B0 trong screen, chưa chứng minh hơn classical. Đề xuất continuation10k, chưa chạy thêm. [Đánh giá và bước tiếp](NINO_COMMON_TD3_20K_ASSESSMENT_2026-11-07.md). Các trạng thái “đang chạy/chờ dung lượng” dưới đây là lịch sử.

> **Cập nhật07/11 — pilot research20k đã khởi chạy:** đã dọn cache tải gói pip để đủ dung lượng; fresh common103D/1D seed11 đang chạy. [Trạng thái và log](NINO_COMMON_STUDIO_TRAINING_RUN_2026-11-07.md). Các đoạn nói thiếu dung lượng dưới đây là trước khi dọn cache.

> **Cập nhật mới — Studio common103D/1D đã nối và smoke Gazebo đạt:**
> learner mới64transitions,48critic/24actor updates,1launch; chưa eval/terminal.
> Pilot fresh20.000steps với Ki0,10 đã chuẩn bị nhưng chưa chạy: preflight
> cần khoảng7GiB trống, hiện còn khoảng5GiB. Chọn ổ lưu đủ dung lượng là
> bước tiếp, không cần thêm PI audit hoặc real dataset để bắt đầu nhánh này.
> [Kết quả, protocol và cách chạy](NINO_COMMON_STUDIO_PILOT_2026-11-07.md).
> Phần bên dưới giữ lịch sử trước lần tích hợp này.

> **Đính chính về TD3 — 07/11/2026:** đã có training thật nhưng quy mô rất nhỏ:
> A seed11: **1.024 transitions,960critic/480actor updates**; C partial:
> **840 transitions replay**, không gộp thành một learner hoàn tất.
> Eval A chỉ phản ánh checkpoint sớm đó. Chưa đủ để kết luận TD3 hội tụ,
> thất bại hoặc không thể thắng baseline. Ưu tiên tiếp: thiết kế pilot
> training có ngân sách trên baseline frozen. Validation Ki0,15 là nhánh
> riêng, không là điều kiện bắt buộc để train với Ki0,10.
> [Giải thích và bằng chứng](NINO_TD3_TRAINING_SCOPE_CORRECTION_2026-11-07.md).

# Nino — đánh giá tiến độ và công việc còn lại

**Cập nhật 07/11/2026.** Phạm vi kiểm tra mới nhất: nhánh Sim và GUI.
Không có lượt chạy robot thật, Gazebo hoặc training mới trong bước chuẩn bị
validation vừa hoàn thành.

## 1. Đánh giá hiện tại

Nino đã có pipeline Sim chạy được: baseline/follower → history và residual
contract → projection/governor theo cấu hình → wheel PI → Gazebo, cùng
recorder, evaluator, checkpoint và GUI. Code TD3/history đã có, nhưng chưa có study training đủ để đánh giá
khả năng học. Cần phân biệt kiểm pipeline chạy được với đánh giá thuật toán.

Tín hiệu tích cực mới nhất thuộc **tuning PI cổ điển**: Ki0,15 đạt screening
mô tả ở lịch dừng8s. Chưa đủ để thay baseline, kết luận tổng quát hoặc đưa
gain xuống motor thật. Kết quả pilot ngắn chưa đủ để quyết định TD3 có thể học tốt đến đâu.

## 2. Đã làm được gì?

| Hạng mục | Đã có bằng chứng | Giới hạn |
|---|---|---|
| Residual TD3 | Code, smoke/train/evaluate, checkpoint và GUI train | Các kết quả trước chưa thắng baseline mạnh; không có training mới trong bước này |
| Observation History | Contract hiện tại history5,10Hz,103D/1D; source/freshness/projection | Cùng shape không làm checkpoint cũ tương thích ABI mới |
| Governor | Reactive core và tích hợp reference/projection đã có | Predictive/contact-informed benefit chưa được chứng minh; không đồng nhất với tiến bộ PI/logger |
| Acquisition/evaluator Sim | Reset ACK+quiet, lockstep, source support, hash, closure và native/GT grids riêng | Không gọi toàn raw loss-free; query chạm conflicting payload phải UNKNOWN/fail closed |
| Gain baseline | Đã đóng9/9cell,1260native ticks; audit dynamics | Hiệu ứng phụ thuộc gain/grid; correction estimator chưa chứng minh motion benefit |
| PI screen stop8s | Đã chạy4/4Gazebo launches,560native ticks; Ki0,10/0,15 | Hai block mô tả, không phải statistical confirmation/generalization |
| Validation stop6s | Context/ABI, runner, protocol và release riêng;68software tests,18GUI tests; build đạt | 4cell/560decisions coordinator và560transitions wrapper đều synthetic; chưa chạy physics |
| GUI | Phân biệt screen8s đã chạy với validation6s mới chuẩn bị; mở protocol, hiển thị kết quả và bước tiếp | Không tự mở budget/training/hardware từ trang benchmark |
| Dữ liệu thật | Đã có các phiên raw IMU,feedback/status,LiDAR và kiểm trục/mounting theo hồ sơ trước | Cutoff của nhánh đánh giá này02/11; chưa đủ để kết luận body slip hoặc sim-to-real |

## 3. Kết quả PI cần hiểu đúng

Ở stop8s, Ki0,15 giảm native velocity RMSE **21,73% và19,46%** theo hai
block; cả hai GT grids cùng chiều. Tuy nhiên path RMSE cao hơn baseline,
tối đa **0,4554mm**. Nằm dưới gate nghiên cứu40mm không có nghĩa được nhà
máy chấp nhận hoặc tốt hơn mọi metric.

Giữ3conflicting joint stamps trong raw; không stamp nào là native
current/next wheel support, và GT scoring query không có conflicting payload.
Điều đó chỉ bảo vệ các query đã kiểm, không bảo đảm mọi raw SysID query hợp lệ.

[Kết quả và giới hạn screen8s](NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md).

## 4. Công việc tiếp theo, theo thứ tự

1. **Chốt pilot TD3 có ngân sách:** dùng baseline Ki0,10 frozen sẵn có;
   xác định contract/ABI, warmup, action coverage, timesteps, eval định kỳ
   và điều kiện giữ cố định trước khi chạy. Không tự tiếp root đã đóng.
2. **Train và theo dõi quá trình học:** ghi critic/actor updates, learning
   curves, action saturation/coverage, replay và checkpoint; các checkpoint
   sớm được dùng chẩn đoán, không là phán quyết về thuật toán.
3. **Đánh giá checkpoint theo protocol:** baseline cùng điều kiện, giữ
   evaluation tách training/checkpoint selection. Nhiều seed và training
   curves cần cho kết luận vượt pilot; số bước riêng nó không bảo đảm hội tụ.
4. **Quyết định sau ngân sách đã chốt:** improve/no improvement/unknown
   dựa trên bằng chứng; không tự thêm bước sau kết quả. Gate thắng baseline
   dùng cho promote/deployment, không yêu cầu thắng trước khi cho train.
5. **PI validation là nhánh riêng:** stop6s đã chuẩn bị nhưng chưa release;
   chỉ cần cho việc promote candidate Ki0,15. Có thể giữ Ki0,10 frozen cho
   pilot TD3, không chờ hoàn tất thêm tuning PI.
6. **Generalization và robot thật sau đó:** protocol riêng cho contact,
   nhiều route/điều kiện; backend motor thật và reference thân xe độc lập
   cần cho claim tương ứng. Không lấy pilot Sim làm hiệu quả nhà máy.

## 5. Việc giữ lại/tạm dừng

- Giữ classical baseline, raw acquisition, quality reporting, GUI và history contract.
- Giữ Ki0,15 ở mức candidate Sim cho validation duy nhất đã chuẩn bị.
- Chưa release training budget mới; ưu tiên chuẩn bị pilot TD3 có giới hạn.
- PPO, predictor, mở rộng estimator và tuning nhiều Ki không là ưu tiên hiện tại.
- Không deploy residual, đổi gain/current hoặc thu chuyển động thật trong giai đoạn này.

**Việc tiếp theo:** chuẩn bị protocol/ngân sách pilot training TD3 thực sự
với baseline frozen. Không kết luận thuật toán từ checkpoint1.024steps,
và không biến chuỗi audit/tuning PI thành điều kiện chặn training vô hạn.

---

## Nhật ký các mốc trước — giữ nguyên theo thời điểm

Các phần dưới là lịch sử. Dùng đánh giá và thứ tự công việc ở trên làm
hiện trạng mới nhất.

> **Cập nhật07/11 — validation stop6s đã chuẩn bị offline:** 68software tests,18GUI tests; 4cell/560decisions coordinator synthetic và560transitions wrapper parity. **0Gazebo mới, release=false,0slot đã cấp**; chưa promote Ki hoặc trainTD3. Tiếp review/release riêng tối đa4lượt/560ticks. [Protocol/kết quả](NINO_SIM_PI_STOP6_VALIDATION_PREPARATION_2026-11-07.md). Các cập nhật bên dưới giữ lịch sử.

> **Cập nhật 07/11 — PI screen Gazebo đã đóng4/4:** 560native ticks; Ki0,15 giảm native velocity RMSE21,7%/19,5%, GT grids cùng chiều. Path RMSE cao hơn nhưng <0,46mm trong screen này. Candidate chưa promote; tiếp validation riêng stop6s, chưa budget/train/hardware mới. [Kết quả](NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md). Nội dung bên dưới giữ lịch sử.

> **Cập nhật 07/11 — PI runner/protocol đã kiểm offline:** 44 tests runner đạt; 4cell/560decisions synthetic, closure/timing/summary là fixture. Đã chuẩn bị ledger, source/install gates và release record có pins; **release=false/0slots**, chưa chạy Gazebo hoặc train. [Protocol/kết quả](NINO_SIM_PI_SCREEN_RUNNER_PROTOCOL_2026-11-07.md). Các đoạn bên dưới giữ lịch sử.

> **Cập nhật 07/11 — PI screen đạt parity offline:** 49 software tests; 3.600 callbacks kernel và 560 transitions wrapper synthetic. Ki0,10 giữ đúng kernel cũ; candidate0,15 chưa có outcome Gazebo. Tiếp bounded runner/protocol/release riêng cho tối đa4lượt/560ticks; chưa cấp slot hoặc train. [Kết quả](NINO_SIM_PI_SCREEN_OFFLINE_RESULT_2026-11-07.md). Các đoạn bên dưới giữ lịch sử.

> **Cập nhật mới nhất07/11 — Dynamics audit hoàn tất:** 1.260native rows giữ nguyên;8/9rawquery đầy đủ,1unknown do payload cùngstamp. Classical target→encoder RMS5,00–5,53mm/s; encoder→body0,040–0,400mm/s. Ưu tiên draft screen wheel PI trong Sim; chưa đổi gain/chạy thêm/train. [Kết quả](NINO_SIM_DYNAMICS_AUDIT_RESULT_2026-11-07.md). Nội dung dưới giữ lịch sử.

# Tiến độ Nino — Sim và bước kế tiếp

**Cập nhật 07/11/2026.** Thiết kế candidate có ID06/11; ngày này là ngày
kiểm offline và tổng hợp hiện trạng theo thời gian client.

## Kết luận hiện tại

Nino đã có một nền nghiên cứu tích hợp trong simulator: plant, follower,
wheel PI, history, residual projection, TD3, recorder và GUI. **Chưa có
controller học được chứng minh tốt hơn baseline mạnh trên envelope cần dùng.**
Nút thắt hiện tại là lợi ích và nhận dạng động lực/đánh giá, không phải thiếu
code TD3 hoặc Observation History. Chưa có learner/hardware release mới.

## Đã hoàn thành

| Hạng mục | Bằng chứng | Giới hạn |
|---|---|---|
| History/command contract | 103D/1D, history5,10Hz; common±0,005m/s, projection và source support | Không tự tương thích checkpoint100D/2D hoặc robot thật |
| TD3 và công cụ train | Đã có learner/checkpoint, smoke/train/evaluate và GUI | Kết quả cũ chưa chứng minh ưu thế; không train lại trong bước này |
| Reset/measurement | Drive ACK+quiet, hai observer, physics ACK, timestamp/closure/hash | Software và Sim; không là calibration robot thật |
| Gain baseline Gazebo | 9/9cell,1260tick;283hashes/3834support checks đạt | Một run/cell,clear-box; không contact/generalization |
| So baseline | Causal/fixed native +22,96% tại1,+29,79% tại0,98,−15,32% tại1,02 | Phụ thuộc gain; causal/B0 còn đảo chiều native/GT tại1/0,98 |
| Correction estimator | Source/spec riêng,44tests,143 quyết định synthetic,1260shadow | Chưa nối runner Gazebo/TD3/robot; chưa đo outcome của correction |
| Dữ liệu thật đã có | Raw IMU,feedback/status,LiDAR; mounting/sign và geometry gần đúng theo báo cáo trước | Cutoff02/11; không thu thêm thật trong nhánh này |

## Correction offline vừa hoàn tất

Tách việc **cập nhật estimate** khỏi **gửi request dựa trên estimate được
giữ**. History reference thay đổi không tự làm mất cache hợp lệ; cập nhật
mới yêu cầu từng bánh cũng ổn định. Lease tối đa0,6s là giả thiết phần mềm
có giới hạn từ5frame và handoff; chưa phải latency hay ngân sách an toàn
thật. Wheel-spread0,002m/s là proposal cùng thang với ref-spread cũ, chưa
hiệu chuẩn từ noise. Không tăng bound/history hoặc đổi shared projection.

Stop/window đóng/zero-baseline/stale/fault/mất owner/reset/clock lỗi xóa
estimate; sau lỗi cần refill5packet tin cậy. Không publish hoặc enable motor.
Spec, candidate và preflight mới nằm trong `held_gain_candidate.py`,
`held_gain_preflight.py`, `sim_held_gain_candidate_v1.json`.

| Gain của source cũ | Request cũ kháczero | Request shadow kháczero | Update / Hold / Zero trong50tick mở |
|---|---|---|---|
| 1.00 | 11/50 | 46/50 | 8 / 38 / 4 |
| 0.98 | 8/50 | 40/50 | 7 / 33 / 10 |
| 1.02 | 31/50 | 40/50 | 28 / 12 / 10 |

Đây là **request trên các observation cũ**, không phải trajectory mới, không
phải bằng chứng giảm rung/slip/tracking error. Không tính RMSE motion cho
correction từ những trajectory đó. Fixture lag cho thấy steady encoder có
thể chặn một transient minh họa; fixture hai hidden-dynamics cho cùng packet
cho thấy **không bảo đảm nhận dạng gain thật** từ history hữu hạn này.

Kết luận: `offline_behavior_passed_identification_unknown`. Một correction
đã dùng; không nối physics tự động hoặc chỉnh tiếp vô hạn để làm đẹp kết quả.

## Còn phải làm — theo thứ tự

1. **Chốt câu hỏi/tiêu chí Sim:** tracking hay chất lượng contact; effect đáng
   quan tâm, thời gian/path/stop constraints. Hiện rule5% chỉ là proposal.
2. **Chẩn đoán động lực từ9run đã có:** tách requested→effective→target→wheel
   và body; kiểm lag/bias/geometry/excitation. Không gọi encoder là body GT.
   Nếu dữ liệu không tách được, ghi unknown; không mở training để thay đo lường.
3. **Quyết định baseline/envelope:** giữ fixed cho known-stop hiện có; chưa
   gọi fixed robust mọi gain. Nếu không có khoảng trống đáng làm, dừng nhánh
   gain-learning. Không mặc định phải dùng correction mới hoặc TD3.
4. **Chỉ khi có cơ chế và useful authority:** viết protocol/root/budget physics
   riêng để so baseline và candidate. Đây là việc chưa được chạy/release;
   không mở lại root9/9, không dùng shadow làm outcome hoặc tự tăng sample size.
5. **Learning có điều kiện:** baseline mạnh còn gap có ý nghĩa mới chốt budget,
   training seeds, validation/holdout, checkpoint selection và action coverage.
   Sau đó mới history ablation/robustness/contact/generalization theo envelope.
6. **Nhánh thật song song:** wheel/body diagnostic có reference độc lập,
   repeatability rồi SysID/calibration. Chỉ deploy sau shadow/latency/owner/stop
   gates. Không cần chờ full real dataset để làm các bước Sim/offline ở trên.

## Artifact và nghiệm thu

- Correction artifact: `/home/tuanmac/nino_research/sim_held_gain_offline_v1/qualification_2026_11_07`.
- Manifest SHA256: `414a468cc0dbf885a7aa70be5999ecf9a44a04ca44fa82bdfa37894fad6e6623`.
- Fingerprint: `38b5ccf4d2dc90d6217570d1b99e6da7386694da2d823c36019d8b4da39e6452`.
- Nguồn9/9: manifest `3865c03c6881502ac81544c9908a339bd62eb10afe529274da589c153d9e6ebd`; source và raw không sửa.
- 44softwaretests đạt;143syntheticdecisions,1260shadowdecisions.
- 14 kiểm tra GUI chọn lọc đạt; build `nino_rl` và `nino_pi` thành công.
  GUI hiển thị riêng proof offline, không đổi thành physics/learning pass.
- **0Gazebo/physics/actor/train/optimizer/hardware mới**;real cutoff02/11.
- [Kết quả Gazebo9/9](NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md).

**Việc nên làm tiếp:** chẩn đoán lag/bias và điều kiện nhận dạng từ9run đã
seal, rồi quyết định giữ cổ điển hay có lý do cho protocol mới. Không train
dài chỉ vì code/GUI đã có hoặc correction software đã pass.
