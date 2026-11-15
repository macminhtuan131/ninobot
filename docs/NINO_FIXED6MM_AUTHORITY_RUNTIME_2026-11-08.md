# E2 — adapter/runner đã kiểm offline, chưa chạy Gazebo

Ngày08/11/2026. Tiếp [protocol E2](NINO_FIXED6MM_AUTHORITY_PREPARATION_2026-11-08.md).
**Đã có runtime riêng; 0/12 allocated, 0 physics mới, 0 optimizer, 0 hardware.**

## Thành phần đã xây

| File | Trách nhiệm |
|---|---|
| `obstacle_authority_runtime.py` | Identity mới; mailbox contact theo receipt; adapter common có biên; wrapper task; kiểm command/driver/limits và neutral parity |
| `obstacle_authority_metrics.py` | QC từng slot; primary GT-header causal20ms/+10ms với độ phủ thời lượng; giữ native riêng và phát hiện source reversal |
| `obstacle_authority_runner.py` | Qualification offline; kiểm release/source/install/disk; chạy đúng một slot; timeout, closure, ledger và review theo hash |
| `obstacle_authority_runner.sh` | Launcher localhost/domain129; dùng checkout Nino và ML environment hiện có |
| `fixed6mm_postmanifold_runtime_release_v1.json` | **Mẫu khóa**: released=false, rules chưa chấp nhận, allocation0 |

Các module/script thuộc `src/nino_rl`; draft JSON và planner của lượt chuẩn
bị trước giữ nguyên. Không sửa v1/v2 controller, checkpoint hoặc PI kernel.

### Luồng thực thi E2

```text
IMU + wheel + command/status → history100D → reference pipeline hiện có
C1 manifold → mailbox có receipt → oracle schedule riêng → common0/±0.005
common → projection/shaping → driver gain1, PI Ki0.10 → Gazebo
GT + raw contact/driver/joint → QC/metric và đối chiếu riêng
```

Không load actor, checkpoint hoặc replay. Oracle là đặc quyền thí nghiệm,
không vào100D feature packet; không tương thích checkpoint103D chỉ vì dùng
cùng history nền. Đây là feasibility **sau manifold**, không phải governor
sensor-only, first loaded contact, traction control hay TD3 performance test.

## Các chi tiết quyết định tính hợp lệ

- Cutoff monotonic được lấy dưới cùng lock với ghi contact. Event nhận sau
  cutoff phải chờ quyết định sau; không backdate trigger theo source cũ đến muộn.
- Oracle source, decision source và receipt có trường riêng. Native100ms
  không biến thành control20ms; GT50Hz không được nâng độ phân giải bằng nội suy.
- Initial history padding chỉ nằm trong warmup kế thừa; thiếu history sau
  warmup hoặc mất health sẽ latch tắt intervention. Source-zero/withdrawal
  vẫn giữ ưu tiên, không tự phục hồi tiến.
- Ki0.10 dùng `OraclePiBackend` kế thừa backend PI đã có; readback/diagnostic
  phải khớp. Torque field là command PI trong Sim, không phải torque đo độc lập.
- Mỗi slot tạo một `EpisodeLifecycle` mới và một independent observer; không
  auto-reset episode thứ hai, không dùng wrapper PI B0-only cho residual khác0.
- Giữ row lỗi trước kiểm; thiếu telemetry/GT/contact hoặc closure lỗi đóng
  ledger. Không thay unknown bằng0 hoặc chạy lại slot đã claim.
- Primary theo `tc..tc+3s`,20ms/+10ms causal ZOH; tích phân dt có support,
  coverage≥98%, GT gap≤40ms. Grid+10ms có prefix0.01s chưa phủ, phải báo thật
  (full-support case:2.99/3s), không nhân giả thành3s. Source reversal bị giữ
  thành lỗi; không sửa bằng sorting. Native100ms báo riêng.

QC mỗi slot chỉ trả `measurement_pass_pending_review`. Nó **không** tự
chứng minh body authority hoặc nominate controller. Cần đủ candidate/B0,
approach caliper, timing trước drive contact, cả block/stop/grid và constraints
đã đề xuất. Công cụ comparison cuối screen còn là bước riêng; chưa có dữ liệu E2.

## Budget, release và điểm dừng

`qualify` chỉ chạy fixture và tạo/kiểm XML world, không khởi chạy ROS node
hoặc Gazebo. Qualification kiểm source/install và XML test có runtime/fault
injection. Danh tính source/protocol, test report và artifact được pin lại.

`run-next` chỉ nhận release riêng khớp checkout, root mới, qualification và
đúng12 slot đã định trước; mẫu đangfalse/0 nên bị từ chối **trước allocation**.
Không có cờ bỏ qua gate. Neutral E2-01 nằm trong12, không thêm smoke bên ngoài.

Sau một slot, ledger ở `awaiting_review`. `review` kiểm hash summary và mọi
file trong manifest trước khi cho trạng thái ready; nó không tự gọi lượt sau.
Một failure đóng ledger và tiêu thụ slot đã claim. Readiness lỗi trước claim
không tiêu thụ slot. Crash để lại `running` cũng chặn tiếp, không tự resume.

Cap kế thừa:300s wall/slot, tổng active wall≤3600s, tối đa1680 task ticks;
thời gian dừng để review không cộng vào active wall. Close backend/observer
vẫn bắt buộc khi có lỗi. Disk preflight dùng estimate+reserve, không hứa bound
dung lượng tuyệt đối. Giữ raw từng slot để audit; đây không là raw train rác.

## Bằng chứng phần mềm và giới hạn

Qualification hiện hành: `qualification_v2/qualification.json` trong audit.
Neutral parity chính xác **140 paired decisions ở stop6 và140 ở stop8**
(560 inner fixture transitions), gồm history/reference/reward/termination.
Đây là reduced-order software fixture, không nhận dạng contact hoặc Ki dynamics.

Các test bao gồm future/late receipt, mailbox capacity/cursor, health/history,
withdrawal, source packet không chứa oracle, driver NaN/gain/limits, source
clock, grid integration, release sai và closure/slot fault injection.
Sửa lỗi clock cộng dồn trong fixture; bổ sung giữ source reversal trong QC.
Qualification đầu giữ lại là lịch sử trước correction QC; không tính hai lần
qualification là hai lượt Gazebo hoặc hai block vật lý.

Kết quả cuối: **161 test được chọn đạt**, trong đó29 test E2; build hai package
đạt,7 cặp source/install khớp.54 file bảo vệ,197 file gốc E1 giữ lại và source
engine v2 cũ đều không đổi;66 file raw thiếu đúng retention cũ. Preflight
read-only kiểm disk/install/process inventory đạt, chưa kiểm graph sau launch.

GUI outline hiển thị runtime đã kiểm offline và0/12; kiểm hash qualification,
source files và test report trước khi gắn trạng thái đã xác minh. Chưa có nút
chạy physics mới trong Studio. Chưa gọi đây là GUI→Gazebo end-to-end.

## Bước kế tiếp

1. Chốt allocation riêng và research rules đã cụ thể trong draft; lặp preflight
   ngay trước launch. Không tự biến ngưỡng nghiên cứu thành yêu cầu nhà máy.
2. **Chỉ E2-01 neutral**: một fresh launch,140 task ticks, Ki0.10, gờ6mm;
   kiểm cutoff/trigger, independent source coverage, readback, task/stop và closure.
3. Chỉ sau review hợp lệ mới xét E2-02; lỗi/unknown thì giữ toàn bộ bằng chứng
   và đóng release theo protocol. Chưa train dài hoặc thêm Ki0.15/DR vào screen.

Không cần robot thật để thực hiện bước Sim này. Không yêu cầu người dùng thu
data mới ở thời điểm hiện tại.

Audit:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_authority_runtime_2026-11-08/`.
