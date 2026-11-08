# Kết quả screen PI trong Gazebo — candidate đạt, chưa promote

07/11/2026 · [Protocol đã khóa trước run](NINO_SIM_PI_SCREEN_RUNNER_PROTOCOL_2026-11-07.md).

## Quyết định

**Ki0,15 đạt rule screening mô tả so với Ki0,10** trên clear-box, nominal
0,2m/s, source stop8s/horizon14s, gain1 và B0 residual0. Native velocity RMSE
giảm21,73% và19,46% ở hai block; cả hai GT grids cùng chiều.

Giữ Ki0,15 là **candidate Sim** để validation riêng. Không thay baseline
frozen, không suy sang firmware/internal motor PI thật, không mở training
TD3 và không gọi đây là generalization hoặc chứng minh lợi ích nhà máy.

## Đã chạy và kiểm được [N — mô phỏng]

4/4 fresh launches ×140 native decisions = **560/560 ticks**, đúng thứ tự
Ki0,10→0,15→0,15→0,10, Kp0,30. Không extra smoke/retry/probe, actor load,
optimizer, training hoặc hardware action. Thời gian wall của job khoảng
190,57s, chỉ là quan sát của batch này.

- 133 file hashes khớp; nguồn, entry/install, dependencies và protocol khớp.
- 1.704 boundary support checks đạt; maximum joint support age2ms.
- 1.160 world-control requests được ACK/completed,0retry; 58.000 iterations
  ở các requests đã ghi, gồm reset/settle và evaluation. Không suy tổng mọi
  iteration trước quyền lockstep; không nhầm560 native ticks với physics steps.
- Đủ readback Kp/Ki và invariant từng condition; telemetry cached đúng Ki.
- Bốn lifecycle/observer đóng đúng, shutdown ACK đạt. Reset có5rounds,
  drive ACK+quiet liên tục0,5s; task/marker/path/stop và native replay đạt.
- Hai observer ghi cùng31.133 joint records mỗi bên; payload variant sets
  khớp trên31.128 common source stamps. **Không suy thành raw loss-free**.
- Release đã đóng `released=false`; ledger giữ4slots consumed, không retry.
- GUI có bảng native/GT/path/stop ở đầu trang, trạng thái candidate và bước
  tiếp;16 tests GUI đạt, build hai package thành công. Lệnh chạy lại qua CLI
  cũng bị chặn trước launch mới. Không gọi kiểm tra chặn này là smoke physics.

## Outcome — không gộp các grids

Velocity RMSE tính bằng **mm/s**; path RMSE bằng **mm**.

| Cell / block | Ki | Native velocity | GT20ms | GT+10ms | Physical path RMSE | Quiet cuối horizon |
|---|---:|---:|---:|---:|---:|---:|
| 0 / 0 baseline | 0,10 | 5,182 | 7,089 | 7,095 | 0,0248 | 4,0s |
| 1 / 0 candidate | 0,15 | 4,056 | 6,137 | 6,141 | 0,0933 | 4,0s |
| 2 / 1 candidate | 0,15 | 4,148 | 6,250 | 6,254 | 0,4554 | 4,0s |
| 3 / 1 baseline | 0,10 | 5,150 | 6,959 | 6,964 | 0,0304 | 4,0s |

| Cặp baseline/candidate | Native relative change | GT20ms | GT+10ms |
|---|---:|---:|---:|
| Cell0/1 | −21,73% | −13,44% | −13,44% |
| Cell3/2 | −19,46% | −10,19% | −10,19% |

Primary giữ whole14s native nominal-body velocity RMSE. Rule≥5% ở cả hai
cặp và hai GT grids giảm cùng chiều đã đạt; không đổi estimand/time grid
sau kết quả. Hai cặp chỉ mô tả, **không CI/power/statistical confirmation**.

**Trade-off phải giữ:** path RMSE của candidate cao hơn baseline, lớn nhất
0,4554mm so với baseline cùng block0,0304mm. Cả hai vẫn dưới gate nghiên cứu
40mm đã khóa, nhưng không được gọi candidate tốt hơn mọi metric. Gate40mm
chưa là yêu cầu nhà máy được chấp nhận. Quiet4s chỉ là thời gian quiet tích
lũy cuối horizon, không phải measured stopping latency.

Wheel-target RMSE native (L/R,rad/s) lần lượt:
baseline0:0,07782/0,07839; candidate0:0,06190/0,06237;
candidate1:0,06220/0,06195; baseline1:0,07880/0,07951.
Đó là secondary từ summary đã ghi, không thay body GT bằng encoder.
Maximum torque tại native publications khoảng0,0878–0,1030Nm; không suy
đó là peak continuous torque hoặc torque đo thật.

## Timestamp ambiguity: giữ và giới hạn claim

Raw joint có **3 conflicting source stamps** (đều có cùng variants trong
hai observer): task~8,872s ở cell0;6,789s ở cell1;4,053s ở cell2. Cell3
không có conflict kiểu này trong joint records đã kiểm. Toàn bộ variants
và spikes được giữ, không chọn first/last payload để làm đẹp dữ liệu.

Phép đối chiếu cụ thể xác nhận:

- Không stamp xung đột nào là wheel source của native current/next packet.
- Không có conflicting GT payload trong query interval của từng run; GT
  header diagnostic tái tính đúng giá trị đã ghi, không nội suy body.
- Chưa chứng minh mọi callback PI/estimator nội bộ có joint timestamp duy
  nhất. Query raw SysID/secondary mới chạm stamp mơ hồ phải unknown/fail
  closed; không áp kết luận native/GT này cho toàn stream.

Không hạ coverage/gate, không vá bằng observer khác, không bỏ sample/run.
Các qualification cũ và audit8/9raw-query/1UNKNOWN của batch gain được giữ
riêng; đó không phải kết quả của batch PI này.

## Artifact và pins

Root: `/home/tuanmac/nino_research/sim_pi_screen_v1`.

Run: `20261106T233559049444Z_sim-pi-screen` — UTC filename vẫn06/11;
batch/report theo ngày client07/11, không gộp với batch gain06/11.

- Manifest SHA256: `6762f5d2903c8bef3bb4208736f14d1e3e13985146243d395fa8ef2afe4da644`.
- Runner fingerprint: `86db564afa9e1a7980b16351db4cf466869c9b6c08c4f9bae27843cde326014f`.
- Protocol SHA256: `7a150aef70ecbb70d06a09476c7b082d82c577d4a49a60dee13bc775c04fb6a6`.
- QA: workspace `artifacts/sim_pi_screen_2026-11-07` có release trước/đã
  cấp/đã đóng, prelaunch, run log, verification và source_ambiguity audits.
  Không sửa raw hoặc artifact đã seal.

## Suy luận và bước tiếp [S / Đ]

**[S]** Giảm đồng thời wheel-target error và body velocity error phù hợp
với giả thuyết chỉnh PI cổ điển giải quyết một phần transient trên sàn sạch.
Chưa tách ảnh hưởng caster/numerics hoặc chứng minh nguyên nhân duy nhất.
Không có căn cứ lấy kết quả này để tăng current/gain hardware hay train TD3.

**[Đ] Một việc tiếp theo:** chuẩn bị protocol validation độc lập cho **lịch
dừng6s**, giữ gain1/nominal0,2m/s/horizon14s/B0zero, so đúng hai Ki với cùng
gate và tối đa4fresh launches/560ticks được đề xuất. Đây là scenario đã từng
có trong dự án nhưng chưa dùng để chọn Ki ở screen này; không gọi unseen
test bank hoặc generalization nhà máy. **Chưa cấp budget/chạy validation**.

- Giữ candidate Ki0,15, không quét thêm Ki hoặc tăng số lặp tự động.
- Validation thuận và task/stop/tracking đạt mới xem xét baseline Sim có
  ID mới cho envelope tương ứng; baseline/artifact/checkpoint cũ giữ nguyên.
- Validation adverse/unknown thì giữ Ki0,10 cho baseline frozen; không mở
  vòng tuning hoặc sample-size escalation. Mở learner chỉ khi có gap ứng
  dụng/mechanism đáng làm mà baseline mạnh còn chưa giải quyết.

**Chưa kết luận được:** gain±2%, stop schedule khác, contact/cáp/rãnh, payload,
route rẽ, nhiều seeds hoặc sim-to-real. Real-data cutoff vẫn02/11; không có
dữ liệu thật hoặc thao tác robot mới trong bước này.
