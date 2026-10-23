# Review ngân sách cadence: tối đa 12 attempts — 22/10/2026

## 1. Quyết định

**Đề xuất giữ trần 12 attempts cho một khảo sát mô tả mới, với gate
instrumentation ở ngay hai lượt đầu. Chưa cấp ngân sách, chưa khởi động
simulation.** Không mở smoke riêng hoặc dùng slot của batch đã đóng.

Trong review phát hiện một lỗi phần mềm tại biên reset đã được tái hiện
và sửa offline. Vì vậy, bản cần review/release là **v2**, không phải v1:

- [Protocol v2](governor_isolated_cadence_contract_v2_2026-10-22/protocol.json).
- SHA-256: `e573217d959e5b4a26e52f733d5cb4c4387284f9f1e27c1643cf72397f85ba0c`.
- `execution_authorized=false`, `budget_released=false`, `simulation_attempts=0`.
- Các input robot/controller/world byte-identical với parent đã đóng.
- Ngưỡng 10% / +0,5 s vẫn là đề xuất; không dùng để quyết định H2 đạt/không đạt.

## 2. Vấn đề đã sửa trước khi đề xuất chạy

Trong lockstep, world đang pause nên joint/GT ghi **trước** marker reset
có thể mang đúng timestamp bắt đầu episode. Pipeline v1 kiểm tra toàn raw
capture trước khi chọn epoch; vì vậy có thể báo wrong epoch dù view không
định dùng mẫu đó. Đây là lỗi đã tái hiện bằng dữ liệu tổng hợp, **chưa phải
lỗi đã quan sát trong Gazebo**.

Correction duy nhất của v2: khi bật đường selected-epoch tường minh, chọn
epoch tương ứng marker reset trước khi gọi validator. Raw/decode vẫn giữ
mọi frame, source timestamp, CRC và hashes. Mẫu epoch cũ không làm support
interpolation; dữ liệu joint/GT phải có thực trong epoch mới. Không đổi
scoring, cadence, controller, sampling hoặc coverage.

Hai test mới kiểm tra:

1. Joint/GT epoch cũ cùng timestamp start được giữ raw nhưng không được
   đưa vào view; view chỉ có payload của epoch hiện tại.
2. GT cũ ở timestamp start không thay được GT bị thiếu trong epoch mới;
   trường hợp đó vẫn fail closed.

Đường decoder legacy mặc định vẫn từ chối raw có epoch cũ chồng window;
không diễn giải lại archive cũ. **125 tests đạt**, gồm hai test mới và các
nhóm native replay, coverage từng window, lifecycle, fault, cadence, executor,
stopping và sequence đã kiểm tra trước. `git diff --check` đạt; freeze v2
được validate với source/dependency hashes hiện tại.

Fixture ROS giả trước đó nhận 159/160 joint và 16/16 GT vẫn được giữ đúng
trạng thái lịch sử. Không chạy lại nó để thay kết quả; không suy từ counts
đó rằng coverage từng cửa sổ trong Gazebo sẽ đạt.

## 3. Ngân sách và lịch đã khóa

**2 block seed × 3 controller × 2 repetitions = tối đa 12 attempts.**

| Attempts | Seed | Repeat | Thứ tự controller |
|---|---:|---:|---|
| 1–3 | 77600 | 1 | PI cố định → governor 20 ms → governor 100 ms |
| 4–6 | 77601 | 1 | PI cố định → governor 100 ms → governor 20 ms |
| 7–9 | 77601 | 2 | governor 100 ms → PI cố định → governor 20 ms |
| 10–12 | 77600 | 2 | governor 20 ms → governor 100 ms → PI cố định |

- Cold start riêng từng attempt; mọi arm dùng cùng acquisition hai process.
- Lượt 1 và 2 là integration checks **nằm trong 12**, không phải lượt bonus.
- Mỗi arm có 4 lượt, mỗi contrast có 4 cặp seed/repeat; hai cặp mỗi seed.
- Thứ tự đã xác định, không đổi sau khi nhìn kết quả. Với bốn bộ ba, không
  thể cân bằng tuyệt đối ba vị trí: tần số vị trí của mỗi arm là 1/1/2.
- Hai seed là block lặp trên cùng geometry, không phải hai map độc lập hoặc
  bộ kiểm tra generalization mới. Cùng seed không có nghĩa cùng caster/contact.
- 12 là trần, không phải cam kết chạy đủ. Integrity fault có thể dừng ở 1–2
  attempts; các slot còn lại không được dùng để retry hoặc bù batch.
- Không có đủ throughput đã đo để hứa thời gian chạy. Không suy runtime
  dự kiến từ timeout của tiến trình.

## 4. Điều kiện đi tiếp trong batch

Sau từng attempt, phải đóng file/process trước khi kiểm tra:

| Gate | Yêu cầu |
|---|---|
| Setup | Standstill sau reset, feedback và config/model đúng contract |
| Readiness/lifecycle | Hai PID khác nhau; đúng session; fresh joint/GT; ACK reset/end khớp |
| Closure/provenance | Hai nguồn đóng sạch; primary health; capture CRC/SHA/epoch; nguồn không đổi |
| Native replay | Tái tạo native RMS/accumulator theo tolerance gốc |
| Timestamp/cadence | Age/skew hợp lệ; fast trace đủ 5 updates mỗi score interval 100 ms |
| Coverage | Gate 98% gốc cho từng window bắt buộc; route đạt không bù crossing thiếu |
| Stopping | Hai lượt integration đầu phải xác nhận stopping; cửa sổ gốc 2 simulation seconds |

Không dùng publisher count hoặc manifest complete để thay coverage. Lỗi
integrity/setup/cadence/physics/cleanup thì dừng; không retry. Mọi spike,
failure, thiếu dữ liệu và slot chưa chạy vẫn có trong ledger. Native failure
không bị ghi lại thành success hoặc bị xóa khi logger fail.

## 5. Ba câu hỏi — bằng chứng và giới hạn kết luận

### 1. Lệnh giảm tốc có đến sớm hơn?

So governor 20 ms với 100 ms trong từng cặp seed/repeat, căn theo first
contact. Báo riêng decision time, driver receive time, publication time và
wheel target. Dùng trace đầy đủ 20 ms, không suy từ control trace 100 ms.

Giữ những khác biệt đã có trước cả hai can thiệp; ghi precontact reduction
nếu có. Publication time chỉ là một mốc quan sát bảo thủ, không tự bằng
thời điểm bánh hoặc thân đã đổi vận tốc.

### 2. Wheel/body thực có đổi tốc độ sớm hơn trước contact tiếp theo?

Đối chiếu encoder trái/phải, GT body speed và timeline contact chịu tải.
Chỉ rõ contact tiếp theo đang xét và giữ cả các contact đã xảy ra trước khi
lệnh đến; không chỉ chọn một contact muộn thuận lợi. Đưa ra actual trajectories,
snapshots trước lệnh, sau lệnh và trước từng contact, cùng source age/support.

Phân biệt slowdown có trước command do contact với response sau command.
`executed_linear_m_s` trong drive là reference đã giới hạn; wheel target cũng
không phải vận tốc thực. `timing_pass` hay đủ snapshot không tự chứng minh
wheel/body đã phản ứng hữu ích.

GT được cấu hình 50 Hz, nên thời gian quan sát body thường cách khoảng
20 ms khi không mất mẫu; joint có timeline riêng. Báo độ phân giải/gap thực
thu được và khoảng bất định của thời điểm đổi vận tốc. Không interpolate
thêm để tuyên bố phân biệt được khác biệt nhỏ hơn thông tin đã ghi. Nếu
không phân biệt được thứ tự response/contact, kết luận **chưa xác định**;
không đổi sampling hoặc bổ sung episode để ép có câu trả lời.

### 3. Crossing có tốt hơn với chi phí thời gian/tracking hợp lý?

Báo slip/rung sau contact, crossing, toàn chuỗi–recovery và toàn tuyến;
arrival/stall, stopping, tracking và thời gian của mọi arm. Đối chiếu cả PI
cố định và governor 100 ms, giữ uncertainty theo cặp/block, mọi spike và
sensitivity GT gốc / grid 20 ms / grid dịch 10 ms.

Các gate arrival/tracking/time hiện có vẫn giữ nguyên. Vì đánh đổi ứng dụng
chưa được chấp nhận, phải báo số đo và trade-off; không tự gọi mức giảm
10% hoặc thêm 0,5 s là tiêu chuẩn nhà máy hay ngưỡng đã áp dụng.

Nếu câu 1 có nhưng câu 2 chưa chứng minh được, không quy cải thiện ở câu 3
thành lợi ích của phản ứng sớm. Kết quả chất lượng vẫn được báo mô tả, cùng
các khác biệt approach/contact và giới hạn quy kết nguyên nhân.

## 6. Điểm dừng và đề xuất sau review

- **Phép đo không hợp lệ:** dừng batch; không so performance trên subset
  thuận lợi, không tự cấp một batch khác.
- **Phép đo hợp lệ nhưng response/crossing chưa phân biệt được hoặc không
  cải thiện:** kết thúc screen ở trần đã chốt, giữ kết luận mô tả/chưa đủ
  bằng chứng; không tự mở tuning.
- **Phép đo hợp lệ và có tín hiệu lặp lại:** review trade-off cùng yêu cầu
  ứng dụng trước quyết định tuning tiếp theo; không tự mở Optuna/PPO/predictor.

**Khuyến nghị ngân sách:** có thể xem xét một release mới tối đa 12 attempts
cho contract v2 theo lịch trên. Review này không tạo release và không tiêu
slot; trạng thái hiện tại vẫn **chưa được phép chạy simulation**.
