# Kết quả thí nghiệm governor 100 ms / 20 ms — 20/10/2026

## 1. Quyết định

**Batch đã dừng đúng hard-stop sau attempt 9 vì thiếu coverage đo slip.**
Đã launch 9/12 slots; cả chín đến đích vật lý và dừng ổn định 2 sim seconds.
Slots 10–12 chưa chạy và không được chạy bù/resume. Không retry, replacement
hoặc smoke riêng. Không mở tuning, predictor, PPO hoặc thử phần cứng.

Trong hai cặp fast/reference có timing hợp lệ, governor 20 ms phát publication
giảm tốc sớm hơn **40 và 42 ms**. Chưa chứng minh vận tốc thân/bánh thực đáp
ứng sớm hơn do governor hoặc chất lượng vượt vật cản tốt hơn có lặp.
Planned aggregate và CI không khả dụng; không lấy trung bình subset thuận lợi.
Không kết luận H2 đạt/không đạt; ngưỡng 10% / +0,5 giây vẫn chỉ là đề xuất.

## 2. Thực thi và integration

Người dùng cấp ngân sách batch mô tả tối đa 12 attempts trong lượt yêu cầu
20/10; [release](governor_cadence_experiment_2026-10-20/execution_release.json)
ghi trước launch và gắn protocol SHA256
`7c483ebec986bc020a630bd696b654d97216436b0da54ed6685fc4a8700a4340`.
Executor theo đúng thứ tự đã khóa, cold start từng attempt, domain 130 và
partition riêng; ledger ghi trước từng launch. Claim ngân sách đã consumed;
ba slot chưa chạy không phải ngân sách còn được tự tiếp tục sau hard stop.

- 9/9 setup, provenance, native replay, cadence và post-arrival stop đạt.
- 8/9 measurement integrity toàn bộ đạt; attempt 9 không đạt coverage.
- Ba fast attempts đều có đúng **835 micro updates / 167 scoring rows**.
- Scoring/follower/history vẫn 100 ms; physics 1 ms; world chunks 20 ms chung.
- PI, torque limits, detector, observation windows, ramp 0,4/s, target 0,90,
  holding và geometry không đổi. Không sửa source/config trong batch.
- Cleanup được collector xác nhận ở cả chín; không còn process batch đang chạy.

| Attempt | Seed/lặp | Controller | Arrival/stop | Đo lường | Ghi chú |
|---:|---|---|---|---|---|
| 1 | 77600/1 | PI | Đạt/đạt | Đạt | Cold start |
| 2 | 77600/1 | 20 ms | Đạt/đạt | Đạt | 835 micro updates |
| 3 | 77600/1 | 100 ms | Đạt/đạt | Đạt | Reference |
| 4 | 77601/1 | PI | Đạt/đạt | Đạt | Cold start |
| 5 | 77601/1 | 100 ms | Đạt/đạt | Đạt | Reference |
| 6 | 77601/1 | 20 ms | Đạt/đạt | Đạt | 835 micro updates |
| 7 | 77601/2 | 100 ms | Đạt/đạt | Đạt | Reference |
| 8 | 77601/2 | PI | Đạt/đạt | Đạt | Cold start |
| 9 | 77601/2 | 20 ms | Đạt/đạt | **Không đạt** | Hard stop, coverage 80,12% |
| 10 | 77600/2 | 20 ms | Chưa chạy | Không có dữ liệu | Không thay lượt |
| 11 | 77600/2 | 100 ms | Chưa chạy | Không có dữ liệu | Không thay lượt |
| 12 | 77600/2 | PI | Chưa chạy | Không có dữ liệu | Không thay lượt |

## 3. Lỗi đo làm dừng batch

Attempt 9: native slip RMS replay khớp **0,030711177593437788**; tuổi/skew
snapshot control và micro-cadence vẫn đạt. Tuy nhiên, observer trace lưu
thiếu một đoạn đồng thời trên GT/joint:

| Kênh | Timestamp cuối trước gap | Timestamp đầu sau gap | Gap |
|---|---:|---:|---:|
| GT | 16,400 s | 19,640 s | 3,240 s |
| Joint | 16,408 s | 19,720 s | 3,312 s |

Cửa sổ toàn tuyến là 6,429–23,129 s. Coverage hợp lệ chỉ **13,38/16,70 s =
80,1198%**, dưới gate 98% hiện có. Bốn GT samples sau gap còn không có joint
interpolation support hợp lệ. Whole-route GT slip phải unavailable; không
nội suy bắc qua gap, đổi grid, điền bằng native metric hoặc bỏ attempt này.
Timing đầy đủ cũng unavailable do body support bị gap trong cửa sổ yêu cầu.

Đây là bằng chứng **trace observer thiếu dữ liệu**, chưa xác định sensor,
bridge, callback queue, serialization hoặc scheduler nào gây ra. Các trace
được evaluator lưu vẫn liên tục và native replay đạt; không được suy ra
robot mất toàn bộ feedback. Log có exception khi cleanup sau SIGINT; thứ tự
đó chưa chứng minh exception gây gap trong lúc chạy. Native physical outcome
và stop vẫn giữ là success, tách khỏi measurement failure.

## 4. Trả lời ba câu hỏi

### 4.1. Lệnh có sớm hơn không?

Các mốc dưới đây tính từ first manifold của từng attempt, không phải cùng
physical state. Publication là mốc quan sát bảo thủ, không phải motor onset.

| Seed/lặp | 20 ms: input/publication | 100 ms: input/publication | Publication sớm hơn |
|---|---:|---:|---:|
| 77600/1 | 36 / 54 ms | 81 / 94 ms | 40 ms |
| 77601/1 | 36 / 45 ms | 83 / 87 ms | 42 ms |
| 77601/2 | Timing unavailable | 82 / 83 ms | Unavailable |
| 77600/2 | Chưa chạy | Chưa chạy | Unavailable |

Hai fast attempts hợp lệ có publication trước caster phải chịu tải tiếp
theo **27 và 36 ms**. Điều này xác nhận cơ hội phát lệnh sớm hơn trong hai
lượt đó. Chưa chứng minh lợi ích outcome.

### 4.2. Vận tốc thân/bánh có thay đổi sớm hơn một cách hữu ích không?

**Chưa xác lập.** Ở hai fast attempts có timing đầy đủ, thân đã giảm còn
0,253 và 0,280 m/s ở mẫu trước input giảm tốc đầu tiên, so với approach
khoảng 0,4 m/s. Tại mẫu body cuối trước caster phải, vận tốc lần lượt là
0,321 và 0,269 m/s, tức phản hồi contact không đơn điệu. Joint cũng biến đổi
mạnh trong contact. Không thể dùng một speed dip hoặc snapshot sau lệnh để
nhận dạng riêng motor lag hay quy toàn bộ giảm tốc cho governor.

Mẫu body ở snapshot publication còn có thể có timestamp trước input mới;
full timestamps/ages và joints được giữ trong JSON. Command/target giảm
sớm đã được ghi nhận, còn **earlier actual causal response** chưa được chứng
minh bằng batch không đầy đủ này.

### 4.3. Slip/rung/tracking/time có tốt hơn không?

Số đo từng attempt dưới đây giữ nguyên cửa sổ và cách tính đã khóa. Không
coi hai cặp có đủ số đo là toàn bộ population đã định trước.

| Attempt / arm | Time (s) | RMSE (mm) | Slip²/m sau contact (s/m) | Rung RMS sau contact (m/s²) | GT slip RMS toàn tuyến | Rung RMS toàn tuyến (m/s²) |
|---|---:|---:|---:|---:|---:|---:|
| 1 / PI | 16,60 | 2,855 | 0,007445 | 10,055 | 0,027994 | 4,363 |
| 2 / 20 ms | 16,70 | 4,253 | 0,006737 | 11,834 | 0,029598 | 5,023 |
| 3 / 100 ms | 16,70 | 3,773 | 0,018736 | 8,208 | 0,040235 | 3,511 |
| 4 / PI | 16,60 | 3,872 | 0,013698 | 1,572 | 0,036717 | 1,100 |
| 5 / 100 ms | 16,70 | 3,793 | 0,009267 | 1,142 | 0,030311 | 1,161 |
| 6 / 20 ms | 16,70 | 3,314 | 0,010930 | 1,182 | 0,034151 | 0,764 |
| 7 / 100 ms | 16,70 | 3,932 | 0,013615 | 7,921 | 0,035165 | 3,569 |
| 8 / PI | 16,60 | 3,090 | 0,018703 | 1,428 | 0,038357 | 1,231 |
| 9 / 20 ms | 16,70 | 4,437 | Unavailable | Unavailable¹ | Unavailable | 2,683² |
| 10–12 | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable |

¹ Không được bộ phân tích đã khóa xuất thành post-contact outcome hợp lệ;
không tự phục hồi metric riêng để hoàn tất cặp. ² Native whole-route rung
vẫn được báo riêng, không thay cho slip bị thiếu.

Hai fast/reference cặp đầu cho hướng slip khác nhau: fast thấp hơn ở
77600/1 nhưng cao hơn ở 77601/1. Rung sau contact fast cao hơn reference
trong cả hai cặp đó. Đây là số đo mô tả từng cặp, chưa phải ước lượng lợi ích
của cả batch. Time của các lượt PI là 16,60 s, governor là 16,70 s; không áp
ngưỡng thời gian đề xuất để tự kết luận chấp nhận được.

Chênh lệch đã có trước can thiệp. Diagnostic slip²/m từ contact đến mốc
publication sớm hơn của mỗi cặp là 0,483451/0,402244 (fast/reference) ở
77600/1 và 0,498142/0,309747 ở 77601/1. Cả hai endpoint quadrature có sensor
support vượt mốc publication: được gắn cờ contaminated, **không gọi là causal
negative control**. Precontact sensor statistics cũng khác giữa các lượt.
Không trừ các chênh lệch này khỏi outcome để tạo kết quả đã hiệu chỉnh mới.

Theo analyzer đã khóa, mọi **aggregate contrast/CI của population đủ bốn
cặp đều unavailable** vì thiếu block/repeat bắt buộc. Không bỏ failures,
spikes hoặc thay sampling; đầy đủ metrics/peaks/sensitivity trong JSON.

## 5. Bước tiếp theo và điểm dừng

Giữ checkpoint cấu hình và toàn bộ trace hiện tại. **Dừng nhánh thực thi
của release này**, không chạy ba slot còn lại, không mở batch khác tự động.

Việc cần làm trước một simulation budget mới là kiểm tra offline có phạm
vi hẹp **đường thu thập observer quanh gap attempt 9**: phân biệt dữ liệu đến
evaluator với dữ liệu được logger nhận/ghi, xem queue/backpressure và thời
điểm mất coverage. Chỉ chọn một correction acquisition nếu có bằng chứng;
không sửa governor, physics, PI, metric hoặc ngưỡng coverage để tránh lỗi.
Chưa xác định nguyên nhân thì ghi rõ, không thay bằng giả thuyết đã chứng minh.

**Audit offline tiếp theo đã hoàn thành:**
[observer acquisition gap](GOVERNOR_OBSERVER_GAP_AUDIT_2026-10-20.md) khoanh
vùng đường observer riêng và backlog khớp queue depth; evaluator vẫn nhận
feedback mới xuyên gap. Chưa phân biệt được scheduling/delivery với
serialization/write/flush. Đề xuất observer wall-time health telemetry,
chưa sửa runtime hoặc mở simulation mới.

Kết quả hiện tại xác nhận được triển khai micro-cadence và lệnh sớm hơn ở
hai cặp; **chưa đủ bằng chứng nâng cấp governor 20 ms hoặc mở tuning/ML**.

## 6. Dữ liệu và tái lập offline

- [Ledger gốc](/home/tuanmac/ninorobot/rl_runs/governor_cadence_experiment_2026-10-20/ledger.json).
- [Executor summary](/home/tuanmac/ninorobot/rl_runs/governor_cadence_experiment_2026-10-20/summary.json).
- [Frozen analyzer JSON](governor_cadence_experiment_2026-10-20/live_analysis/report.json).
- [Execution review và gap evidence](governor_cadence_experiment_2026-10-20/live_analysis/execution_review.json).
- [12 assigned slots CSV](governor_cadence_experiment_2026-10-20/live_analysis/assigned_attempts.csv).
- [Input hashes](governor_cadence_experiment_2026-10-20/live_analysis/execution_review_inputs_sha256.json).
- [Script review offline](governor_cadence_experiment_2026-10-20/live_analysis/summarize_execution.py).

Không sửa offline verification cũ thành bằng chứng live: `verification.json`
là snapshot kiểm tra trước chạy. Release, ledger và báo cáo này mô tả trạng
thái thực thi mới; protocol và các snapshot trước chạy được giữ nguyên.
