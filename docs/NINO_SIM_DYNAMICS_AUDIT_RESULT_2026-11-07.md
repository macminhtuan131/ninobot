# Chẩn đoán dynamics từ 9 run Sim — 07/11/2026

## Quyết định

**[N — dữ liệu Sim]** Nút cần ưu tiên trong bài clear-floor này nằm ở
target→wheel tracking và quá trình hồi phục sai số chậm. Bánh và body gần
nhau hơn nhiều trong sáu lượt classical có plateau cố định. Đã tái tạo đúng
primary của1.260row; không đổi objective hoặc chạy thêm Gazebo/TD3.

**[S]** Dữ liệu phù hợp với PI tích phân đang bù sai số/load sau ramp;
không đủ để đồng nhất encoder/reference ratio với một gain vật lý cố định.
Chưa tách độc lập PI, friction/caster và cơ học contact thành nguyên nhân.

**[Đ]** Ưu tiên một screen classical PI **chỉ trong Sim**, trước đầu tư tiếp
vào gain estimator/TD3. [Protocol draft](NINO_SIM_PI_SCREEN_DRAFT_2026-11-07.md)
có một candidate Ki và điểm dừng; **chưa release/chạy hoặc sửa controller**.
Correction hold/update trước vẫn đóng1/1, không chỉnh thêm ở đây.

## Dữ liệu và đồng hồ

- Source:9run clear-box đã seal,manifest `3865c03c6881502ac81544c9908a339bd62eb10afe529274da589c153d9e6ebd`.
- Giữ native whole14s và hai GT grids cũ. Window3,0..7,4s chỉ phục vụ
  chẩn đoán plateau; không thay primary hoặc chọn khoảng tốt nhất.
- Phân rã tại native snapshot theo identity đại số:
  `body−nominal = (reference−nominal)+(effective−reference)+(target−effective)+(encoder−target)+(body−encoder)`.
  Các phần không độc lập; RMS không cộng tuyến tính và không là attribution
  nhân quả/năng lượng. Native snapshot có skew drive/truth, nên raw kiểm riêng.
- Raw dùng GT source-header, wheel/drive gần nhất **không ở tương lai**;
  giữ support≤40ms, gain-map phải khớp stamp drive. Không nội suy, không dùng
  receipt timestamp thay source time. Age tối đa quan sát:wheel
  1.0ms,drive20.0ms.
  Đây là source alignment offline, không chứng minh thời điểm governor đã nhận mẫu.

## Vấn đề raw được giữ nguyên

Analyzer V1 dừng do cùng source stamp có payload wheel khác nhau. Failure,
source V1 và các file đã tạo được giữ ở root V1. V2 là correction **reader**,
không phải correction controller thứ hai hoặc sửa raw.

Tổng4stamp conflicting:3ngoài query-support,1trong plateau causal gain0,98.
V2 giữ tất cả variant; nếu query dùng một stamp ambiguous thì **toàn metric
raw của cell đó là UNKNOWN**. Không chọn latest/earliest variant, không lấy
sample cũ thay thế, không loại1mẫu rồi gọi toàn query đạt.

Có1981 GT-header query samples;
1980 có support duy nhất,1không có.
**8/9query đầy đủ;1/9unknown.** Không gọi đây là100%raw integrity của9run.
Native kết quả và gate đã seal không bị sửa; report native trước đây không
tự bảo đảm uniqueness của mọi header trong toàn raw stream.

## Độ lớn sai số — raw plateau, mm/s

| Gain | Arm | RMS target→encoder | RMS encoder→body | Tình trạng |
|---|---|---|---|---|
| 1.00 | B0 | 5.534 | 0.040 | Đủ support |
| 1.00 | Classical_scheduled | 5.433 | 0.152 | Đủ support |
| 1.00 | Causal_gain_candidate | 5.333 | 0.176 | Đủ support |
| 0.98 | B0 | 5.001 | 0.145 | Đủ support |
| 0.98 | Classical_scheduled | 5.238 | 0.180 | Đủ support |
| 0.98 | Causal_gain_candidate | UNKNOWN | UNKNOWN | Có payload cùng stamp khác nhau |
| 1.02 | B0 | 5.360 | 0.400 | Đủ support |
| 1.02 | Classical_scheduled | 5.523 | 0.293 | Đủ support |
| 1.02 | Causal_gain_candidate | 5.330 | 0.145 | Đủ support |

Sáu lượt B0/fixed: target→encoder khoảng5,00..5,53mm/s; encoder→body
khoảng0,040..0,400mm/s. Dữ liệu ủng hộ ưu tiên tracking ở low-level trước
cho bài này. Không suy thành “không slip” ở mọi time/floor/obstacle; radius
vẫn là geometry mô hình. Apparent body/encoder slope không là calibration
geometry hoặc bằng chứng traction độc lập trên robot thật.

## Mô hình hằng so với hồi phục theo thời gian

Đây là phân tích exploratory sau khi có data, không preregistered experiment.
Các model/window được cố định trong spec trước khi chạy analyzer trên đủ9run.
Fit3,0..5,4s; báo dự báo5,4..7,4s. Đây là time-block trong cùng trajectory,
**không phải independent holdout/generalization hoặc so controller outcome**.
Không fit causal có reference thay đổi vào model plateau.

So `encoder=k*target` với error `A*exp(−(t−3)/tau)` và biến thể thêm offset.
Tau-grid0,1..10s/81điểm chỉ là search hữu hạn; SSE-profile5% không là CI.

| Gain / arm | Static later RMSE mm/s | Exp zero-offset later RMSE mm/s | Tau zero-offset s | Tau free-offset s | Rank gain+bias |
|---|---|---|---|---|---|
| 1.00 / B0 | 3.552 | 0.407 | 3.35 | 4.73 | 1 |
| 1.00 / Classical_scheduled | 3.273 | 0.254 | 3.16 | 3.55 | 1 |
| 0.98 / B0 | 3.129 | 0.274 | 2.99 | 5.01 | 1 |
| 0.98 / Classical_scheduled | 3.487 | 0.265 | 2.82 | 9.44 | 1 |
| 1.02 / B0 | 3.181 | 0.567 | 3.16 | 1.58 | 1 |
| 1.02 / Classical_scheduled | 3.534 | 0.489 | 3.35 | 10.00 | 1 |

Model hồi phục zero-asymptote dự báo tail tốt hơn static ở6/6lượt.
Tau2,82..3,35s chỉ mô tả hồi phục phần sai số còn lại, **không phải latency,
deadtime, braking time hoặc time constant motor thật**. Thêm asymptote làm
tau rất khác, có profile đụng grid boundary; chưa nhận dạng asymptote/physicalgain.
Reference hằng làm design matrix `[target,1]` rank1 ở6/6: không tách được
gain và bias affine trong từng plateau. Pool nhiều run closed-loop không
tự xóa confounding hoặc biến thành excitation open-loop có kiểm soát.

## PI state proxy — evidence có giới hạn

Source/readback giữ Kp0,3,Ki0,1,conditional_v1,500Hz. Khi PI output không
clamp, suy ra state thuật toán:
`I=(reported_pi−Kp*(target−actual))/Ki`.
Trong6plateau classical,ΔI≈0.327..
0.360rad; residual so với tích phân
trapezoid của error từ telemetry tối đa
0.001318rad. Kp/Ki=3s.
Điều này phù hợp với cơ chế integral buildup và thời gian hồi phục quan sát;
chưa chứng minh PI là nguyên nhân duy nhất. Đây là state/effort **mô phỏng**,
không torque/current motor thật đo độc lập hoặc lý do tăng torque cap.

## Giữ / tạm dừng / tiếp

- Giữ measurement/native+GT reporting,history/projection và fixed baseline
  của clear known-stop; không mở lại root9/9 hoặc sửa checkpoint cũ.
- Tạm dừng đầu tư gain inversion như true physical-ID hoặc mở rộng learner
  cho bài này. Hold/update chỉ đạt software; chưa có motion outcome mới.
- Tiếp chuẩn bị protocol một-factor Ki trong Sim, có baseline B0 và stop
  constraints. Nếu classical đủ tốt, ưu tiên classical. Một gap chưa giải thích
  hoặc return đẹp không cấp lý do train TD3.
- Không cần real dataset mới để làm quyết định Sim này; trước sim-to-real
  vẫn cần verify backend/geometry/motor response/body reference trên hardware.

## Nghiệm thu / provenance

- 34softwaretests cho numerical V1 và reader V2; source/failed-artifact được
  hash-pin. Không hạ support40ms hoặc thay nguồn bằng observer khác.
- 16 kiểm tra GUI chọn lọc đạt; build `nino_rl` và `nino_pi` thành công.
  GUI hiển thị riêng8query đủ/1UNKNOWN và draft PI chưa release.
- [Biểu đồ source-time và model](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_dynamics_audit_2026-11-07/chain_dynamics.png>).
- Artifact:`/home/tuanmac/nino_research/sim_chain_dynamics_audit_v2/analysis_2026_11_07`.
- Manifest:`da0c20ff6deb089e52353c9d984f1c4c4178b302f23ffc48bbc58c079b22a2ab`.
- Fingerprint:`dc152cfab982d0022008623d6c3adf1f3a13b1c868894a16f8c17e996ae4e379`.
- Không đổi controller,PI gain,current,limit,reward,primary hoặc raw.
- **0Gazebo/physics/actor/optimizer/train/hardware mới.** Real cutoff02/11.
