# Gain baseline qualification — kết quả Gazebo

06/11/2026 · **Đã đóng9/9,1.260 tick hợp lệ;0 actor/optimizer/train/hardware.**

## Quyết định

**[N — sim]** Task/measurement đạt ở cả9cell. Causal kém fixed tại gain1 và
0,98; tốt hơn tại1,02. Whole14s native/GT không chứng minh một phương án
causal tốt trên toàn dải. So B0 còn đổi dấu giữa native và GT tại1/0,98.
Kết luận `unknown_small_or_gain_dependent_effect`, **chưa promote/learner**.
Giữ fixed classical cho bài clear known-stop đã có; chưa gọi nó là lời giải
robust mọi gain. Ở1,02 fixed còn kém B0; không giấu kết quả này.

**[S]** Candidate hiện trộn cập nhật estimate với việc có gửi bù hay không;
các lệnh bù có thể làm history không còn steady và khiến bù bị rút. Ratio
encoder/reference cũng biến thiên trong khi gain injected cố định: chưa thể
đồng nhất nó với gain tĩnh hoặc body-speed gain. Chưa tách lag, PI và cơ khí
thành nguyên nhân độc lập.

**[Đ] Việc kế tiếp:** Thiết kế một correction cổ điển offline: tách cập nhật gain khỏi lệnh bù được giữ; kiểm độ ổn định encoder và ảnh hưởng lag. Trace replay chỉ kiểm hành vi, chưa là outcome mới. Chưa mở Gazebo v2, learner hoặc tăng residual.

## Thiết kế đã thực thi

[Protocol](NINO_SIM_GAIN_BASELINE_PROTOCOL_2026-11-06.md): gain1→0,98→1,02;
mỗi gain B0/fixed/causal. Clear-box trong factory lab, source stop8s,
horizon14s,nominal0,2m/s,common±0,005m/s,10Hz,history5,103D/1D.
Gain được áp đúng một lần trước wheel ramp/PI; yaw giữ nguyên trước limits.
Gain/GT chỉ evaluator metadata; controller dùng cùng packet causal.
Không phải mixed map, contact test hoặc phần cứng. Dải±2% là stress giả định.

Một run/cell; paired seed không exact-state branching, không nhiều lặp độc
lập, không CI/power/generalization. Wall thực thi khoảng392,74s là quan sát
của đợt, không cam kết tốc độ chạy. Ba cell gain1 là integration trongbudget.

## Metric từng cell

RMSE m/s; path mm. Cả9cell qua marker/path≤40mm/dừng yên2s/task horizon.
Native và GT giữ riêng; không chọn grid thuận lợi.

| Gain | Arm | Native | GT20ms | GT+10ms | Path |
|---|---|---|---|---|---|
| 1.00 | B0 | 0.0053058 | 0.0067892 | 0.0067941 | 0.042 |
| 1.00 | Classical_scheduled | 0.0040779 | 0.0058232 | 0.0058274 | 0.020 |
| 1.00 | Causal_gain_candidate | 0.0050141 | 0.0069393 | 0.0069443 | 0.330 |
| 0.98 | B0 | 0.0070579 | 0.0080484 | 0.0080542 | 0.021 |
| 0.98 | Classical_scheduled | 0.0053483 | 0.0068078 | 0.0068127 | 0.021 |
| 0.98 | Causal_gain_candidate | 0.0069414 | 0.0084326 | 0.0084387 | 0.043 |
| 1.02 | B0 | 0.0039467 | 0.0057354 | 0.0057395 | 0.048 |
| 1.02 | Classical_scheduled | 0.0043509 | 0.0058813 | 0.0058855 | 0.129 |
| 1.02 | Causal_gain_candidate | 0.0036844 | 0.0053253 | 0.0053291 | 0.240 |

Delta tương đối dương = causal có sai số cao hơn comparator.

| Gain | Causal/fixed native | GT20 | GT+10 | Causal/B0 native / GT20 |
|---|---|---|---|---|
| 1.00 | +22.96% | +19.17% | +19.17% | -5.50% / +2.21% |
| 0.98 | +29.79% | +23.87% | +23.87% | -1.65% / +4.77% |
| 1.02 | -15.32% | -9.45% | -9.45% | -6.65% / -7.15% |

Trong `evaluation_result.comparison`, `grid_sensitive` kiểm causal/fixed.
Audit bổ sung kiểm causal/B0 và xác nhận đảo chiều ở gain1/0,98; không thay
primary, không sửa sealed result hoặc gộp tỷ lệ sau khi thấy outcome.
Rule5% chỉ đề xuất nghiên cứu, chưa là yêu cầu ứng dụng được chấp nhận.

## Cơ chế fallback quan sát được

Audit tái tính request từ chính `equal_observation` và geometry danh nghĩa;
khớp action đã ghi, không cấp injected gain/GT cho hàm controller.

| Gain | Proxy valid | Reference chưa steady | Nonzero→fallback tick kế | Range estimate valid |
|---|---|---|---|---|
| 1.00 | 11/50 | 39/50 | 7 | 0.95224..0.99233 |
| 0.98 | 8/50 | 42/50 | 8 | 0.93429..0.97032 |
| 1.02 | 31/50 | 19/50 | 3 | 0.96891..1.01313 |

History reference được yêu cầu có spread≤0,002m/s; residual có thể đổi tới
0,005m/s. Chuỗi action và invalid reason phù hợp với giả thuyết tự làm mất
điều kiện cập nhật. Đây là cơ chế có thể kiểm fixture; **không phải** kết quả
counterfactual rằng giữ bù sẽ cải thiện outcome. Các phase-cost và sai khác
pre-window được giữ trong verification; không dùng để đổi metric hoặc coi
cost ngoài window là trần benefit. Nguồn hỗ trợ và dữ liệu cuối phiên đủ
cho audit này; chưa có failure mới yêu cầu xây thêm logger.

## Integrity và phần mềm

- **283 hashes**,3834 support checks đạt;
  joint source age lớn nhất2.0ms, giữ gate cũ.
- 2610 physics requests ACK/completed/iteration delta đúng;
  **0retry**.
- Primary/independent cùng70,038 records mỗi observer;
  70,034 source stamps giao nhau,**0payload mismatch**.
  Boundary records không tự gọi là packet loss; không vá bằng observer khác.
- Reset ACK+quiet, gain readback, map once, target/torque envelope,
  source causality, task, cả hai GT grids và lifecycle/observer closure đạt.
- **17 runner tests**,53GUI tests trước release;54GUI tests sau bổ sung trang
  result. Một lỗi thứ tự dòng GUI trước release đã sửa, log lỗi giữ nguyên;
  không phải failure scientific/Gazebo. Build nino_rl/nino_pi đạt.
- Release đã đóng,false; root giữledger và không chạy lại. Không đổi gain,
  current,reward,QoS,action bound hoặc old checkpoint.

## Provenance

- Artifact: `/home/tuanmac/nino_research/sim_gain_baselines_v1/20261106T142659151112Z_sim-gain-baselines`.
- Manifest SHA256:`3865c03c6881502ac81544c9908a339bd62eb10afe529274da589c153d9e6ebd`.
- Runner fingerprint:`96d525607c57a943b7c681fdd9632086f74607a48913d2753842b317d4add805`.
- Context frozen:`deccb94680a263042ab4fd688bca7669e79f562602a713f23c4d4dc4243f469f`.
- ABI:`99e8488b9d2945d967273b2388d107183b14688bbedab5ecdde76b29d5c55219`.
- Audit,XML,GUI log/screenshot và replay estimate nằm trong QA
  `artifacts/sim_gain_baselines_2026-11-06` của workspace client.

Real cutoff vẫn02/11;hardware residual authority0. Các số ở đây là **Nino
simulation** và kiểm phần mềm, không phải dữ liệu robot thật hoặc TD3 mới.

## Điểm dừng kế tiếp

[Draft correction offline](NINO_SIM_GAIN_ESTIMATOR_NEXT_2026-11-06.md).
Một correction thiết kế có fixture causality/hold/update/reset/stop, rồi
quyết định lại. Nếu thiếu excitation hoặc estimator vẫn gộp lag/bias, báo
unknown và chọn envelope/baseline đơn giản; không tự nâng bound,history,
mở PPO/Optuna hoặc tăng sample size. **Chưa có budget physics v2/TD3.**
