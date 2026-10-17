# Audit offline seed 77320: trigger lần hai và chênh lệch trước phanh

**Ngày:** 16/10/2026. **Simulation mới: 0 episode.**

## Quyết định

**Giữ detector; chưa có căn cứ sửa hoặc chặn trigger thứ hai.**

Trong candidate 200 ms, trigger thứ hai gắn với biến động contact của bánh
chủ động phải khi rời/tái chịu tải giữa cáp và sàn. Kênh wheel-tracking error
tự nó đủ vượt ngưỡng; bánh đo được quay âm dù target vẫn dương. Các sample
contact có tải xuất hiện trước trigger, trong lúc lệnh tiến gần như không
đổi. Dữ liệu không hỗ trợ chẩn đoán một false trigger do chuyển BRAKE/RECOVER.

Đây là **bằng chứng ủng hộ liên hệ với contact transition**, không phải chứng
minh duy nhất lực nào gây đảo chiều, collision solver đúng với robot thật,
hoặc logic hiện tại đã tối ưu cho mọi chuỗi tiếp xúc.

Giữ quyết định loại candidate delay 200 ms. Default vẫn 0 ms; không sửa
detector, PI, rearming, ramp, native metric hoặc điểm study. Không chạy thêm
delay, simulation, Optuna, predictor hay PPO.

## 1. Phạm vi và phương pháp

Audit toàn bộ ba arm seed **77320** từ batch delay đã đóng: PI full,
governor 0 ms và governor 200 ms. Không lấy seed thuận lợi khác để thay thế.

- Dùng **governor input timestamp**, không dùng timestamp cuối action.
- Tái dựng quiet/confirmed/armed từ ratio và trạng thái disturbance đã ghi,
  kiểm tra khớp mọi hàng control của cả ba episode.
- Tách wheel ratio = recorded wheel error / recorded threshold; threshold
  có phần allowance theo thay đổi wheel target, giữ công thức cũ.
- Đọc đúng feedback stamp mà governor đã ghi từ raw drive diagnostics.
  Ghép joint/IMU bằng sample header-time gần nhất **không ở tương lai**;
  đối chiếu các scalar tái dựng với scalar detector đã lưu.
- Contact có tải: depth >0 và lực sample >1e−6 N. Tách manifold với loaded
  sample, không tích phân sample lực thưa thành contact impulse.
- Slip offline giữ GT timestamps gốc, chỉ interpolate joint tại các stamp
  đó theo cùng hàm đã dùng; không thay native score hoặc chọn grid khác.

Contact/caster/GT chỉ là thông tin diagnostic, không đưa vào governor.
Code audit: `src/nino_rl/scripts/audit_governor_second_trigger.py`.

## 2. Kênh kích hoạt và thời điểm rearm

Các thời điểm tương đối dưới đây tính từ first caster-left manifold
**13.727 s** của candidate.

| Mốc | Sau first contact | Phase sau update | Quiet timer | Wheel ratio | Body-rate ratio từ IMU gần nhất | Kết quả |
|---|---:|---|---:|---:|---:|---|
| Trigger 1 | +76 ms | DELAY | 0 | 3.759 | 0.234 | Wheel channel đủ kích hoạt |
| Quiet 1 | +476 ms | HOLD | 0.1 s | 0.168 | <1 | Chưa rearm |
| Quiet 2 | +576 ms | HOLD | 0.2 s | 0.177 | <1 | Chưa rearm |
| Quiet 3 | **+676 ms** | HOLD | **0.3 s** | 0.579 | 0.479 | **Rearm** |
| Sau quiet | +776 ms | HOLD | 0 | 0.872 | 0.807 | Armed vẫn true |
| Xung vertical | +876 ms | HOLD | 0 | 0.131 | <1 | Không trigger |
| Trigger 2 | **+976 ms** | **DELAY** | 0 | **6.317** | **0.0189** | **Wheel channel kích hoạt** |

Lúc trigger 2:

- Wheel error **0.394634 m/s**, threshold **0.062477 m/s**; allowance không
  bị bỏ qua. Wheel error là sai lệch actual–target, **không tự bằng slip**.
- Latest IMU stamp **14.700 s**, age 3 ms; body-rate xy **0.006612 rad/s**,
  thấp hơn ngưỡng 0.35 rad/s. Đây không phải yaw-rate z.
- Filtered vertical ratio 3.349, nhưng `vertical_only_trigger_enabled=false`.
  Vertical không đủ quyền gây event nếu wheel/body channel không vượt ngưỡng.
- Confirmation timer =0.1 s sau một mẫu disturbed. Với control 100 ms và
  `confirmation_seconds=0.04`, đây là logic một lần update; không được gọi
  là chứng minh có 40 ms sensor disturbance liên tục.

**Vì sao trigger lần hai được phép?** Ba mẫu quiet đã rearm ngay trong HOLD.
Việc quiet kết thúc sau đó không tự hủy armed. Khi wheel error vượt ngưỡng
ở +976 ms, core cho phép HOLD → DELAY và reset HOLD timer. Đây là logic đã
có, không phải timer chạy sai hoặc replay event cũ.

Ở +876 ms, vertical ratio khoảng 3.335 vẫn không tạo event vì motion channel
không đủ ngưỡng. Mẫu này củng cố việc attribution không thể dựa riêng vào
`governor_trigger_ratio` tổng lớn hơn 1.

## 3. Contact và lệnh thực thi: thứ tự quan sát

| Sau first contact | Quan sát |
|---:|---|
| +276 ms | Candidate bắt đầu giảm scale; từ +476 ms đã giữ 0.90 |
| +612 ms | Bánh chủ động trái bắt đầu manifold với C1 |
| +777 ms | Bánh chủ động phải bắt đầu manifold với C1 |
| +814 ms | Kết thúc manifold cáp bánh trái được quan sát |
| +938 ms | Manifold sàn bánh phải bắt đầu, **chưa có tải dương** ở sample đó |
| **+960 ms** | Bánh phải có loaded floor sample, tổng magnitude lực điểm contact khoảng **24.31 N** |
| **+972 ms** | Bánh phải có sample tải cả cáp (**39.87 N**) và sàn (**44.04 N**), depth dương |
| **+975 ms** | Joint bánh phải đo **−0.381798 rad/s** |
| **+976 ms** | Governor tạo event 2 |
| +977 ms | Drive sample ghi target phải **+5.9526 rad/s**, actual **−0.3818 rad/s** |

Các tổng magnitude lực là tổng sample qua contact points, không phải impulse,
không phải force threshold an toàn. Event `end` chỉ là upper bound của logger.

Input event 2 dùng target phải **+5.932345 rad/s** từ feedback stamp
**14.684 s** (+957 ms), và joint stamp **14.702 s** (+975 ms). Từ hai dữ
liệu đó tái dựng đúng 0.394634 m/s wheel error. Target +5.9526 ở drive
sample sau trigger không được dùng để giải thích ngược quyết định trước đó.

Trong **200 ms trước trigger**, executed linear reference nằm trong
**0.359706–0.359818 m/s**, executed yaw reference **0.050775–0.064571 rad/s**.
Scale giữ 0.90; chưa RECOVER, không có lệnh đảo chiều. Dao động thân/bánh
không thể quy thành một lệnh phanh/tăng tốc lớn vừa phát ra ở thời điểm đó.
Thay đổi yaw reference lớn hơn ở input sau +1076 ms xảy ra **sau** trigger.

Vì vậy, cách mô tả sát dữ liệu là **nhiễu mới trong phần tiếp xúc sau của
cùng C1**, liên quan chuyển tải bánh phải. Không phải vật cản thứ hai; cũng
không chỉ còn một xung IMU cũ mà không có thay đổi contact thực được ghi.
Chưa tách được ảnh hưởng riêng của cáp, sàn và caster lên lực tổng.

## 4. Chênh lệch trước phanh: đã có trước mọi reduced command

Để tránh đánh đồng hậu quả candidate với chênh lệch ban đầu, dùng cửa sổ
**first manifold → +50 ms** làm negative control GT-slip. Đã kiểm tra cả
mẫu hỗ trợ tích phân: GT/joint cuối được dùng là +52/+69/+53 ms cho PI,
governor 0 ms và candidate; đều trước reduced-command sớm nhất **+76 ms**.
Các run vẫn ở scale 1; cùng seed không đảm bảo cùng pose/contact state hoặc
yaw correction.

| Arm seed 77320 | GT slip² integral, 0→50 ms (s) | GT slip RMS trong cửa sổ | Coverage |
|---|---:|---:|---:|
| PI full | 0.001994 | 0.19970 | 100% |
| Governor 0 ms | 0.006684 | 0.36562 | 100% |
| Governor 200 ms | **0.008356** | **0.40880** | 100% |

Candidate đã có integral cao **4.19× PI** và **1.250× governor 0 ms** trước
lệnh giảm tốc đầu tiên. Không thể coi chênh lệch này là kết quả của delay
200 ms đã tác động lên robot; vào thời điểm đó candidate chưa giảm speed
reference. Điều này cũng không chứng minh mọi phần chênh lệch sau đó độc
lập với controller.

Cửa sổ 0→76 ms vẫn được lưu trong JSON như diagnostic ban đầu, nhưng hàm
quadrature dùng sample GT kế tiếp ở +89–93 ms để tính biên. Vì support đó
vượt mốc +76 ms, **không dùng window này làm negative control nhân quả**.
Kiểm tra support được lưu riêng, không thay định nghĩa native hoặc score.

Trong window candidate trigger → onset (+76→276 ms), integral là
0.018039 s candidate, 0.005846 s PI và 0.005580 s governor 0 ms. So candidate
với governor 0 ms ở đây có thêm khác biệt hành động; so với PI vẫn bị
confound bởi trạng thái contact/steering khác từ trước. Không gán một tỷ lệ
phần trăm nhân quả cho delay từ ba cold start này.

GT-slip window 0→50 ms cũng đủ coverage, nhưng **không khôi phục diagnostic
IMU first-impact** vốn thiếu trong batch trước. Không thay đổi trạng thái
unavailable của các metric IMU đã báo cáo.

Precontact body speed gần nhau không đủ bảo đảm contact states giống nhau.
Audit trước ghi caster-right rolling khác nhau và sampled floor support
trước contact bằng 0 ở cả ba arm: bánh caster không mang tải có thể quay
khác nhau; chỉ riêng rolling thấp không chứng minh caster trượt hay damping sai.

## 5. Kiểm chứng và giới hạn

- Replay quiet/armed khớp toàn bộ ba control traces. Không dùng end-action
  joint snapshot để thay input-state joint.
- Tại các mốc trigger/rearm và mọi hàng +400→1200 ms của candidate, wheel
  error và threshold tái dựng khớp đến tolerance 1e−10 m/s. Threshold khớp
  mọi hàng focus; total ratio tái dựng khớp mọi hàng focus.
- 27/28 hàng focus candidate tái dựng wheel error khớp; một hàng +2476 ms
  chênh **0.0004853 m/s** khi ghép latest raw joint. Không tuyên bố mọi
  callback identity được lưu đầy đủ hoặc mọi input khớp tuyệt đối.
  Sai khác đó ngoài cửa sổ quyết định và không thay attribution event 2.
- Ba tests mới đạt: lookup không chọn future/stale sample; replay rearm
  trong HOLD và vertical-only disturbance; từ chối timer không khớp.
- Invocation đầu audit dừng vì feedback trước action đầu không nằm trong
  action-window CSV. Đã dùng **đúng stamp raw diagnostics được lưu**, giữ
  ghi chú lỗi; không interpolate target, không sửa dữ liệu hoặc simulation.
- **302 file bảo vệ không đổi**; native metrics, study scores và runtime
  controller/config giữ nguyên. Script và test audit mới được snapshot/hash.

## 6. Hành động tiếp theo

1. **Không correction detector trong bước này.** Không thêm refractory time
   hay cấm retrigger trong HOLD chỉ để biến hai events thành một event.
2. **Giữ loại delay 200 ms.** Việc detector bắt được contact disturbance
   không làm candidate trở thành controller tốt; lần hai còn kéo dài giữ
   tốc độ thấp và cần được tính vào toàn bộ maneuver.
3. Trước khi có budget can thiệp mới, chuẩn bị một thiết kế ghép cặp có
   kiểm tra approach/contact variability và đánh giá **toàn bộ chuỗi contact**,
   thay vì giả định mọi run bắt đầu cùng trạng thái tại first contact.
   Báo cả negative-control trước hành động, mọi failures và tất cả lần
   retrigger; không chọn bỏ run theo kết quả.
4. Nếu chưa phân biệt được hiệu ứng điều khiển với biến thiên đó, dừng nhánh
   can thiệp mới; không tự chuyển sang delay khác hoặc predictor/PPO. Theo
   Deep Research, H2 vẫn cần được xác nhận trước khi đầu tư predictor.

## Dữ liệu kiểm tra

- [Decision máy đọc được](governor_second_trigger_2026-10-16/decision.json).
- [Trigger evidence](governor_second_trigger_2026-10-16/trigger_evidence.json).
- [Timeline CSV](governor_second_trigger_2026-10-16/candidate_detector_timeline.csv).
- [Contact transitions](governor_second_trigger_2026-10-16/contact_transitions.json).
- [GT window comparison](governor_second_trigger_2026-10-16/window_comparison.json).
- [Kiểm tra support trước hành động](governor_second_trigger_2026-10-16/negative_control_support.json).
- [Kết quả batch delay](GOVERNOR_BRAKE_DELAY_2026-10-16.md).
