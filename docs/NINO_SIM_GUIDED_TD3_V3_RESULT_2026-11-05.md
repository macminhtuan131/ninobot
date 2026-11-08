# TD3 V3 guided — kết quả pilot 05/11/2026

## Quyết định

**TD3 V3 đã được triển khai, train và evaluate thật trong Gazebo. Chưa promote.**
Giữ guided B0 trên sàn sạch; contact outcome còn unknown vì một B0 qua gờ
biến thiên mạnh và vượt gate chất lượng. Không tăng train/history/PPO từ
kết quả này. Không có SSH, hardware motion hoặc real data mới.

Việc tiếp theo đề xuất là **ablation frozen actor full / common-only / B0
trên clear**, tối đa6 lượt, optimizer0, protocol/root mới. Chưa chạy ablation.
Mục đích là phân biệt tác hại của differential residual trước khi học thêm;
không dùng riêng lượt B0 gờ xấu để tuyên bố TD3 có ích.

## Đã xây và đã kiểm gì?

- `guided_td3_contract.py`: reward nominal velocity/yaw, zero-init actor head
  và target sync, kiểm task identity ngoài ABI, replay proposal semantics.
- `residual_guided_td3.py`: wrapper guided Gym task, ba stage hữu hạn,
  optimizer/train/evaluator, kiểm save/load và dependency manifests.
- YAML/script riêng; không sửa source/cấu hình/checkpoint V1/V2 hoặc parent
  guided baseline. GUI có Contract → Train → Đánh giá, xem bảng8 lượt và
  khóa cả stage lỗi/hủy đã tiêu thụ. Sửa lỗi GUI dùng biến result làm mất
  bảng trạng thái job khi đọc contact result; có regression test.

[Protocol trước chạy](NINO_SIM_GUIDED_TD3_V3_PROTOCOL_2026-11-05.md).
Root `~/nino_research/sim_guided_td3_v3`:

| Stage | Artifact | Kết quả |
|---|---|---|
| Offline contract | `20261105T022312787033Z_sim-v3-contract` | 12 input100D, actor/target zero, critic giữ nguyên, save/load/portable parity; physics/optimizer0 |
| Train | `20261105T022329071579Z_sim-v3-train` | 512 transition, 496 critic updates, seed7, h5, fresh model/replay |
| Evaluate | `20261105T022715745474Z_sim-v3-evaluate` | 8 fresh launches, 1120 tick, guided B0/TD3 × clear/gờ6mm ×2 |

Profile integration giữ [32,32], LR chung0,0003, batch32, learning_starts16,
buffer2048, exploration sigma0,1. Đây không phải parameter tối ưu hoặc nhiều
training seed. Zero-init chỉ đúng deterministic actor **trước optimizer**;
16 bước warmup dùng random action, training có noise.

Ba episode train đầy đủ đều task success/stop; đoạn cuối92 tick dừng vì hết
ngân sách512, được lưu **right-censored**, không đổi thành episode failure
hoặc success. Replay512 rows khớp obs/action/reward/next-obs/done/timeout.
Save/load giữ actor/target, twin critics/target, optimizer và replay;
portable actor sai khác lớn nhất khoảng7,45e−8 trên fixture đã kiểm.

## Điều kiện và reward

Cùng causal wheel+gyro-Z estimator, estimated-pose follower, history100D,
normalization/projection/PI và actuator limits của parent. Nino/caster trong
controlled factory hall, sàn box và single rigid cylinderØ6mm x0,65m;
không là full mixed factory map hoặc dây mềm.

Robot/tuyến yaw0; path3m; source0,5–8s, cruise0,2m/s; task14s gồm6s pha
dừng. GT chỉ reset/reward/evaluator. **Marker0,95m không là arrival goal3m.**

Target reward lấy từ shaper nominal riêng trên baseline follower trước
residual, không từ accepted command do policy thay đổi. Follower vẫn phụ
thuộc trajectory đang chạy, không phải counterfactual bất biến. Reward gồm
velocity/yaw tracking, proposal size/change và terminal penalties; không
thưởng tổng progress. Deadline14s là true terminal, timeout0.

Checkpoint kiểm thêm task/reward/baseline/guidance/estimator/source hashes;
ABI100D không đủ để nhận checkpointV2. Replay lưu proposal đã chọn gồm
warmup/exploration; projected/accepted/final/actuator readback tách riêng.

## Kết quả từng lượt

RMSE trên toàn task14s, gồm stop. Thứ tự bảng đúng thứ tự chạy. Gate engineering
đề xuất giữ max path40mm, estimate position50mm/yaw0,05rad và marker/stop2s.

| Arm | World/lặp | RMSE v (m/s) | RMSE yaw (rad/s) | RMSE path (mm) | Max path (mm) | Max estimate pos (mm) | Marker + stop | Gate chất lượng |
|---|---|---:|---:|---:|---:|---:|---|---|
| B0 | clear/1 | 0,005009 | 0,001733 | 0,722 | 1,075 | 3,472 | Đạt | Qua đề xuất |
| TD3_h5 | gờ6mm/1 | 0,021405 | 0,021138 | 9,988 | 15,730 | 8,684 | Đạt | Qua đề xuất |
| TD3_h5 | clear/1 | 0,005840 | 0,023702 | 12,606 | 19,287 | 2,917 | Đạt | Qua đề xuất |
| B0 | gờ6mm/1 | 0,016030 | 0,010166 | 3,996 | 5,983 | 6,496 | Đạt | Qua đề xuất |
| B0 | gờ6mm/2 | 0,059912 | 0,092930 | 30,892 | 58,202 | 12,055 | Đạt | **KHÔNG ĐẠT** |
| TD3_h5 | clear/2 | 0,005999 | 0,024283 | 12,759 | 19,366 | 3,624 | Đạt | Qua đề xuất |
| TD3_h5 | gờ6mm/2 | 0,021337 | 0,019300 | 10,484 | 16,582 | 6,907 | Đạt | Qua đề xuất |
| B0 | clear/2 | 0,005218 | 0,000122 | 0,040 | 0,052 | 3,744 | Đạt | Qua đề xuất |

**Sàn sạch:** TD3 RMSE path12,61–12,76mm so B0 0,04–0,72mm; RMSEv
0,00584–0,00600m/s so0,00501–0,00522m/s. Cả hai lượt TD3 đều cao hơn từng
lượt B0. Chưa có minimum effect được chấp nhận, không diễn giải CI/power.

**Gờ:** TD3 RMSEpath9,99–10,48mm; B0 4,00 và30,89mm. B0 lần2 maxpath
**58,20mm >40mm**, dù task/stop vẫn đạt. Giữ toàn bộ lượt này. Không lấy
pooled mean hoặc riêng failure B0 để promote TD3; hai trajectory không là
exact-state counterfactual và hai lượt không chứng minh giảm variance.

Cả8 đạt marker/stop; **7/8 qua gate chất lượng đề xuất**, trong đó TD3 4/4.
Task success và quality pass là hai kết luận riêng.

### Bias residual và B0 contact outlier

Offline audit trên frozen traces (không thêm physics/optimizer):

- Trên clear, policy có contribution yaw differential trung bình khoảng
  **−0,0141 đến−0,0145rad/s** trong pha motion; baseline follower đồng thời
  sinh correction yaw dương khoảng0,0106–0,0115rad/s. Đây là decomposition
  reference của trajectory hiện có, không là hiệu ứng body counterfactual.
  Zero-init đã ngăn bias trước học, chưa ngăn bias hình thành sau optimizer.
- B0 gờ tốt/xấu trước first manifold có maxcross khoảng0,024/0,041mm;
  pose/swivel gần thẳng, nhưng caster wheel rotations/velocities khác nhau.
  Approach giống không là cùng trạng thái tải/contact/PI đầy đủ.
- Từ first manifold, B0 tốt/xấu maxcross5,98/58,20mm và RMSEv
  0,0181/0,0694m/s; max|body yaw rate|0,041/0,307rad/s. Sai khác rõ sau
  contact nhưng chưa tách caster, PI, friction/contact numerics thành nguyên
  nhân độc lập. Manifold không là first loaded contact/force.
- Max effort ở publication B0 xấu khoảng1,57Nm, dưới torque cap4Nm.
  Publication50Hz không loại trừ transient giữa mẫu. Không có căn cứ tăng
  torque/current/gain, hạ gate hoặc bỏ spike từ audit này.

Chi tiết giữ ở `analysis.json`, `contact_outlier_audit.json` và plot trong QA.
Contact baseline cũ4/4 pass là evidence của batch cũ, không xóa failure mới.

## QC, phần mềm và giới hạn

- **178/178 file** trong ba manifests khớp SHA256.
- **3384/3384** physics requests ACK/completed, đúng iteration/clock,
  retry0;24/24 read-only parameter calls completed.
- **8160 estimator updates** kiểm support causal, dt/age và receipt;
  boundary source/estimate age tối đa19ms. Clock mới sau reset được giữ
  riêng; không lấy diff của các epoch nối nhau thành source gap.
- Counts/gaps/closure không là chứng nhận continuous coverage98% của
  contract khác, hoặc logger loss-free trong mọi điều kiện. Không có
  impact/slip/loaded-contact quality claim từ screen này.
- **69 sim/contract +13 GUI tests đạt**, build `nino_pi`/`nino_rl` và
  source/install match được kiểm riêng. Lần unit suite đầu có2 fail do
  fixture chạm shared lock của job sim đang chạy; đã cô lập đường tài nguyên
  trong test, giữ JUnit lỗi. Không đổi runtime/controller/physics hoặc retry
  experiment vì việc sửa test này.
- Chỉ một training seed và hai launches mỗi arm/world đã thấy. Chưa calibration
  thực, multi-seed/generalization, history ablation hoặc hardware shadow.

[Verification](NINO_SIM_GUIDED_TD3_V3_VERIFICATION_2026-11-05.json).
QA:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_guided_td3_v3_2026-11-05`.

## Một việc tiếp theo có điểm dừng

Chuẩn bị **một** protocol/root ablation clear-floor mới: frozen checkpointV3
full actor, cùng actor nhưng differential residual bị mask0, và guided B0;
hai fresh launches/arm, thứ tự cân đối, tối đa6×140=840tick, optimizer0.
Giữ cùng PI/history/geometry/clock; lưu actor raw proposal và command sau
mask riêng, không ghi đè proposal gốc hoặc tái dùng làm replay học.

Primary: path RMSE; secondary: nominal v/yaw tracking, progress/time và stop.
Giữ gate engineering hiện có, failures và source rules; không mở rộng sang
contact hoặc thêm lượt khi effect không rõ. Đó là đề xuất chưa chạy, không
là kết luận common-only sẽ thắng. Nếu mask differential không giải thích
được lệch tuyến thì dừng nhánh giả thuyết đó; không tăng train để che vấn đề.
Nếu nó giải thích được, cân nhắc action tối giản trong protocol learning mới.

Đồng thời giữ contact outcome là unknown; audit caster/PI/contact hiện có
chưa đủ xác định một correction cơ khí/physics cụ thể. Không promote policy
hoặc deployment chỉ vì all8 task/stop hoặc return.
