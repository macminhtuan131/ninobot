# Chuẩn bị kiểm soát approach/contact và đánh giá toàn chuỗi tiếp xúc

**16/10/2026 — chỉ chuẩn bị và kiểm tra offline, 0 simulation mới.**

## Quyết định giữ nguyên

- **Loại delay 200 ms**, default vẫn 0 ms; giữ detector, PI, robot và ramp.
- Không chọn candidate mới từ các metric bổ sung dưới đây.
- Trước một thử nghiệm can thiệp khác, cần đo repeatability của **PI với PI**,
  kiểm tra trạng thái approach và theo dõi cả contact/retrigger/recovery.
- Không coi cold starts cùng seed là khôi phục cùng snapshot. Không đưa
  contact identity/GT/caster state vào governor triển khai.

Định hướng này theo phần H2, paired trials và negative control của báo cáo
Deep Research đính kèm. Không xây predictor trước khi có control benefit
đủ lặp lại; cũng không cần chờ PPO thắng PI để tune controller cổ điển khi
logging/reset/physics đã đủ ổn định cho việc chọn tham số có ý nghĩa.

## 1. Đã chuẩn bị được gì?

1. **Protocol máy đọc được**, chốt trước các lượt tương lai:
   [protocol_before_future_runs.json](governor_approach_sequence_plan_2026-10-16/protocol_before_future_runs.json).
2. **Công cụ offline** `src/nino_rl/scripts/prepare_governor_contact_sequence.py`:
   đo approach, phân loại caster có/không mang tải, theo dõi mọi contact và
   mọi trigger, xác định contact end và phục hồi liên tục, giữ failures/missing.
3. **Hàm gate sau reset** đã có kiểm tra đơn vị, chưa nối vào luồng ROS online.
4. Đã thử công cụ trên **6/6 trace đã lưu**, không chạy lại simulator.
   **4 tests đạt; 311 file bảo vệ không đổi**; native/config/score study giữ nguyên.

**Chưa thực hiện:** gate online, bốn lượt PI mới hoặc can thiệp mới. Đây là
protocol đã chuẩn bị, chưa phải xác nhận repeatability đã đạt.

## 2. Kiểm soát reset và approach

### Sau reset, trước lệnh tiến đầu tiên

Đề xuất một initialization revision chung cho mọi arm tương lai:

- Giữ reset pose, PI reset/acknowledgment và hình học từ cùng frozen config.
- Sau **lần mutation/reset cuối**, giữ lệnh zero, step physics có kiểm soát
  và đòi đủ **0.5 simulation second liên tục** có đo đạc hợp lệ.
- Trong cửa sổ đó: |body speed| và |driven-wheel linear speed| ≤0.01 m/s,
  |yaw rate| ≤0.03 rad/s; commanded v/ω bằng 0, feedback age trong [0,0.1] s,
  không sample gap >50 ms, không NaN/future data.
- Tối đa **5 simulation seconds** chờ ở zero. Không đạt thì ghi readiness
  failure của attempt, dừng batch; không reset lại, retry hoặc thay episode.
- Đặt native episode-clock theo cùng quy ước sau initialization; ghi thời
  gian chờ riêng để không che startup cost. Không tăng stale tolerance hoặc
  bỏ các callback/epoch barrier đã có.
- Không ép xoay/teleport caster để làm kết quả lặp lại. Ghi caster swivel,
  rolling và floor-load state để biết phân bố trạng thái thực tế.

Các mức trên là **engineering limits cho protocol tương lai**, chưa phải
giới hạn phần cứng đã hiệu chuẩn hoặc tiêu chuẩn ngành. Hàm pure-Python đã
có; tích hợp ROS/lockstep và fault checks còn là bước triển khai kế tiếp.

**Không dùng 0.5 s trước episode epoch làm bằng chứng đã đứng yên sau reset.**
Trong trace cũ, cửa sổ đó có thể đi qua teleport/settling. Tool giữ các số đo
này như diagnostic và đánh dấu `post_reset_release_verified=false`.
Một cửa sổ cũ có max speed lớn không đủ chứng minh robot đang bất ổn khi
bắt đầu hành trình; cần xác định ranh giới reset trước khi kết luận.

### Approach trước first contact

Đo cửa sổ **−300 đến −50 ms** so với first manifold, dùng cho audit offline:

| Đại lượng | Flag prospective cho từng run | Caliper giữa hai run cùng block |
|---|---:|---:|
| Body speed | 0.39–0.41 m/s | Chênh median ≤0.005 m/s |
| Lateral y | abs(y) ≤0.01 m | Chênh median ≤0.005 m |
| Yaw | abs(yaw) ≤2° | Chênh góc đã wrap ≤1° |
| Roll/pitch | ≤2° | Báo phân bố, không tự sửa cơ khí |
| Coverage | ≥98% | Không bù missing bằng số 0 |

Caster loaded/unloaded/mixed được báo riêng. Không dùng rolling thấp của
caster không mang tải làm lỗi; không so sánh góc qua ±π bằng phép trừ thẳng.
Đây là flags/balance checks, **không phải bộ lọc để bỏ run có outcome xấu**.
First-impact severity không được dùng làm matching criterion sau khi xem kết quả.

### Giới hạn đã thấy ngay trên dữ liệu cũ

6/6 run cũ và 6/6 cặp cùng seed đạt các flag approach thô ở trên. Tuy vậy,
GT-slip trong 50 ms đầu vẫn khác rõ giữa arm. Vì thế **đạt speed/pose
caliper không đồng nghĩa cùng contact state**. Không được lấy bảng flags
này để tuyên bố đã giải quyết reset/contact variability.

## 3. Đánh giá toàn chuỗi, không dừng ở trigger đầu

Giữ nguyên native/whole-route metrics và crossing cũ:
**first manifold +50 ms → body qua plane cách gờ 0.50 m**.

Bổ sung các diagnostic có revision riêng:

| Cửa sổ | Định nghĩa và mục đích |
|---|---|
| Negative control GT-slip | First contact → +50 ms, chỉ hợp lệ nếu mọi GT/joint support của quadrature trước reduced-command đầu. Không khôi phục metric IMU thiếu bằng GT-slip |
| Fixed horizon | First contact → +3.0 s, báo sampled peak/P95/RMS, slip integral/m, quãng đường và thời gian; giữ horizon chung để tránh RMS đẹp do kéo dài window |
| Toàn contact | First contact → max(clearance plane, last named-obstacle manifold end +0.2 s) |
| Contact và phục hồi | Kéo đến khi **đồng thời** CRUISE, scale ≥0.98, final executed v ≥0.392 m/s và body v ≥95% median approach, liên tục 0.3 s |

Định nghĩa 3 s và các khoảng quiet/recovery là **diagnostic mới đã chốt cho
protocol này**, không phải cách chấm lại history để chọn governor thắng.
Nếu chuỗi vượt 3 s, vẫn báo tail/contact/recovery riêng, không cắt mất nó.
Fixed 3 s có cả impact đầu không tránh được; không dùng riêng nó để chứng
minh lợi ích post-trigger. Trước stage can thiệp, phải chốt thêm window theo
trigger nhân quả, dùng cùng detector chạy quan sát ở PI để có mốc đối chứng;
không lấy thời điểm contact GT làm đầu vào kích hoạt controller.

- Giữ tất cả retrigger, kể cả khi xảy ra trong HOLD. Không ghép nhiều events
  thành một maneuver giả định đơn event.
- Lưu từng component/collision, manifold begin/end và sample có depth/lực
  dương. End timestamp là upper bound, sampled force không phải impulse.
- Unclosed contact, thiếu clearance hoặc chưa phục hồi trước terminal:
  ghi **censored/unavailable**, báo outcome đã quan sát; không gán impact=0.
- Arrival failure, stall, timeout và readiness failure đều ở lại ledger.
  Metric quality của phần quan sát không biến một failure thành success.
- Toàn tuyến vẫn báo arrival, 2 s stop, time, tracking, native/GT slip. Giữ
  mốc time ≤18.5 s và ≤1.05× PI, mean physical RMSE ≤1.05× PI.

**Kiểm tra trên trace cũ:** tool xác định contact end khoảng **1.972–2.253 s**
sau first contact; phục hồi đồng thời xác nhận khoảng **2.272–2.693 s**.
Fixed 3 s có GT-slip/IMU coverage đủ ở cả 6 lượt. Điều này chỉ xác nhận công
cụ đọc được dữ liệu; không đảo quyết định loại delay 200 ms.
Recovery confirmation chỉ bắt đầu xét sau contact-end đã định nghĩa; vận
tốc thực có thể hồi trước đó. Không diễn giải số này thành motor latency.

## 4. Batch đầu tiên được đề xuất: PI-only, tối đa 4 attempts

Chưa chạy. Giữ đúng world 6 mm/x3.10 m/+8° và frozen config/hash đã lưu.
Tất cả dùng **full PI 0.4 m/s**, cold start riêng, một simulator tại một lúc.

| Thứ tự | Seed development | Lần lặp | Controller |
|---:|---:|---:|---|
| 1 | 77400 | 1 | PI full |
| 2 | 77401 | 1 | PI full |
| 3 | 77401 | 2 | PI full |
| 4 | 77400 | 2 | PI full |

Mục đích là đo **PI–PI run-to-run differences**, không tìm tham số. Hai lần
lặp/seed chỉ cho một khoảng biến thiên thô, không đủ variance/power estimate
chính xác, confidence interval đáng tin hoặc tuyên bố generalization.

Điều kiện và điểm dừng:

1. Gate post-reset online phải được tích hợp/kiểm tra trước batch. Không
   chạy bốn lượt bằng cách giả định cửa sổ trước epoch đã đủ điều kiện.
2. Lỗi readiness, reporting/provenance hoặc physical gate: dừng, giữ attempt
   và danh sách chưa chạy; **không retry/thay thế**.
3. Approach lệch hoặc contact regime không nhất quán: báo tất cả outcomes,
   dừng lập kế hoạch intervention; chọn tối đa một setup correction nếu có
   bằng chứng. Không sửa detector chỉ vì số trigger khác nhau.
4. Nếu approach phù hợp nhưng quality vẫn biến thiên, báo raw PI–PI ranges,
   contact timing và negative-control differences. Không tự tăng số lượt.
5. Trước batch intervention riêng, phải chốt smallest worthwhile effect và
   budget dựa trên biến thiên, measurement fidelity và chi phí ứng dụng.
   Chưa có dữ liệu yêu cầu cơ khí/production để chọn ngưỡng đó thì ghi thiếu;
   không dùng 10–15% như chuẩn ngành hoặc lấy một cặp PI làm noise floor chính xác.
6. Không phân biệt được lợi ích điều khiển trong budget hợp lý: dừng nhánh
   predictive-governor H2 này, không lặp vô hạn hoặc chuyển sang PPO để né vấn đề.

Stage can thiệp tiếp theo **chưa chọn candidate hoặc số lượt**. Nếu có căn
cứ để chuẩn bị, dùng block-randomized comparisons trên development scenarios,
giữ test bank độc lập; không chọn candidate từ batch delay đã bị loại.

## 5. Bước triển khai kế tiếp

**Nối hàm gate sau reset vào harness dùng chung**, ghi boundary reset/zero
command window và readiness outcome; giữ logic controller/scoring. Đây là
initialization contract mới, phải ghi version riêng trước khi chạy bốn PI
attempts. Không sửa vị trí/caster geometry hoặc tiếp tục tuning trong bước đó.

## Artifacts

- [Trạng thái chuẩn bị](governor_approach_sequence_plan_2026-10-16/preparation_status.json).
- [Protocol tương lai](governor_approach_sequence_plan_2026-10-16/protocol_before_future_runs.json).
- [Đọc toàn chuỗi trên 6 trace cũ](governor_approach_sequence_plan_2026-10-16/historical_sequence_demonstration.json).
- [Approach balance: không phải bằng chứng contact giống nhau](governor_approach_sequence_plan_2026-10-16/approach_balance_demonstration.json).
- [4 tests](governor_approach_sequence_plan_2026-10-16/tests.log).

Bản draft đầu được giữ riêng tại `governor_approach_sequence_plan_2026-10-16_draft/`;
bản hiện tại phân biệt rõ pre-epoch window với post-reset gate và yêu cầu
command/body recovery đồng thời. Không có runtime hoặc native artifact bị đổi.
