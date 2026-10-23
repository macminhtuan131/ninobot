# Audit slip theo pha — toàn bộ 8 cặp PI–governor

**Ngày:** 20/10/2026. **Phạm vi:** đọc offline đúng 16 attempts của khảo sát
18/10, ghép theo `(seed, repeat)`. Không chạy simulation, không đổi PI,
governor, vật lý, sampling, native metric, điểm study hoặc tiêu chí nghiên cứu.

## 1. Kết luận và quyết định

**Phần slip cần giải thích tập trung ở tiếp xúc caster và khoảng đầu phanh;
recovery không phải nguồn excess slip chính trong batch này.** Hai block vẫn
cho kết quả khác chiều; chưa chứng minh governor cải thiện lặp lại.

- Khoảng **93,8%** tích phân slip² toàn tuyến của governor nằm từ contact đầu
  đến hết pha hạ lệnh tốc độ. PI trong cửa sổ tương ứng là **94,4%**.
- Pha recovery chỉ chiếm khoảng **0,007%** tích phân governor. Có tăng nhỏ ở
  7/8 cặp, nhưng quy mô không giải thích chênh lệch chính.
- Chênh lệch trước lệnh giảm tốc đã đáng kể ở một số cặp, dù approach caliper
  của khảo sát đạt. Không thể gán toàn bộ chênh lệch sau contact cho governor.
- Các đỉnh lớn đi cùng thân giảm tốc, bánh phải chạy nhanh hơn chuyển động
  thân và trạng thái tiếp xúc chịu tải biến đổi. Đây là bằng chứng về cơ chế
  **contact–wheel response**, chưa xác định riêng lỗi caster, PI hoặc vật lý.

**Quyết định:** giữ cấu hình hiện tại để đối chiếu. Không sửa recovery,
không tăng penalty, không tăng giới hạn mô-men hoặc bỏ ramp từ kết quả này.
Chưa chọn một correction controller/vật lý vì chưa tách được nguyên nhân
của biến thiên tiếp xúc và độ trễ phản hồi. Các tiêu chí 10% / +0,5 giây vẫn
ở mức đề xuất; không đưa ra kết luận H2 đạt/không đạt hoặc tự cấp thêm lượt.

Nếu mở thí nghiệm tiếp theo, câu hỏi cần kiểm chứng là **can thiệp có cải
thiện phần contact còn lại sau khi bánh/caster đã gây giảm tốc thân không**,
với đối chứng và approach được kiểm soát. Không có căn cứ từ audit này để
mở một pilot sửa recovery, thử delay khác hoặc tuning rộng.

## 2. Dữ liệu và cách chia pha

Nguồn: `rl_runs/governor_descriptive_survey_2026-10-18/ledger.json` và toàn bộ
control/drive trace, IMU, joint, GT, contact của 16 attempts. Hai seed 77500,
77501; mỗi seed bốn cặp lặp; mỗi cặp có PI `full` và governor `reactive`.
Giữ đủ **16/16 physical arrivals**, toàn bộ native outcomes, stop checks và
spike. Batch này không có arrival failure; không loại lượt nào.

Sampling giữ đúng cách báo cáo đã khóa:

- Slip chẩn đoán dùng **timestamp header GT gốc**, không tạo grid mới. Joint
  được nội suy tại các timestamp đó, không ngoại suy; gap tối đa 10,001 ms.
- Giữ nguyên công thức slip, denominator floor, ratio clip, tích phân
  trapezoid cắt tại biên, giới hạn gap GT và điều kiện coverage 98%.
- Native slip vẫn dùng snapshot/accumulator control-step ban đầu; báo riêng
  với GT slip, không chọn metric có lợi hơn.
- IMU giữ mẫu gốc và mọi spike. Joint gốc khoảng 500 Hz và drive publication
  khoảng 50 Hz dùng để giải thích phản hồi, không thay sampling của slip.

Biên pha dựa trên **drive publication đầu tiên xác nhận lệnh governor mới**,
qua `command_received_sim_s` và `governor_input_time_s`. Không dùng endpoint
control trễ một chu kỳ để xác định bắt đầu phanh. Đây là mốc publication
bảo thủ, không phải đo thời điểm actuator bắt đầu tác động chính xác.

| Pha | Định nghĩa |
|---|---|
| Startup | 1 giây đầu, giữ riêng để không nhầm với crossing |
| Precontact | Sau startup đến manifold cáp đầu tiên của chính lượt đó |
| Contact trước phanh | Contact đầu → publication đầu giảm scale |
| Braking | Publication scale 0,96 → publication scale 0,90 |
| Holding | Publication scale 0,90 → publication bắt đầu recover 0,94 |
| Recovery | Publication 0,94 → publication trở lại scale 1,00 |
| Sau recovery | Từ lệnh trở lại scale 1,00 đến cuối episode |

Mỗi PI được chia bằng offset của governor cùng cặp, tính từ **contact đầu
của chính PI**. PI không thực sự phanh trong những cửa sổ này. Cách ghép
không tạo ra cùng pose, cùng contact state hoặc cùng quãng đường.

Cả tám governor đều có một vùng phanh/giữ/phục hồi liên tục. **Đính chính khi
chuẩn bị thí nghiệm cadence:** attempts 8 và 10 có `governor_events=2`, tức
có retrigger bên trong HOLD dù phase/scale không đổi. Không thể suy ra
“không retrigger” chỉ từ các lần đổi phase. Holding là 0,8 giây trong sáu
lượt; 1,5 giây ở attempts 8 và 10 do bộ đếm hold được khởi động lại. Các giới
hạn 0,8–1,0 giây vẫn là giới hạn theo mỗi lần trigger, không phải chặn tổng
thời gian của mọi retrigger. Tích phân, biên pha và điểm số audit giữ nguyên.
Braking và recovery
đều dài 0,2 giây theo các mốc publication. Pha trở lại lệnh cruise không có
nghĩa vận tốc thân đã lập tức ổn định; phần còn lại vẫn được giữ riêng.

## 3. Đủ tám cặp: excess nằm ở đâu?

**Đơn vị bảng: chênh lệch tích phân slip², ×10⁻³ s; governor − PI.** Số
dương nghĩa governor lớn hơn. Đây là phân rã có tính cộng của tích phân,
không phải thay thế primary slip²/m. RMS và slip²/m không được cộng theo pha.

| Seed / repeat | Trước can thiệp¹ | Phanh + giữ | Recovery | Sau recovery | Toàn tuyến |
|---|---:|---:|---:|---:|---:|
| 77500 / 1 | −0,8898 | +5,4785 | +0,0017 | +0,0000 | +4,5904 |
| 77500 / 2 | −1,8006 | +1,4710 | +0,0004 | +0,0002 | −0,3290 |
| 77500 / 3 | +7,3466 | +4,9182 | +0,0001 | −0,0048 | +12,2601 |
| 77500 / 4 | −3,0913 | −1,6665 | +0,0006 | −0,0045 | −4,7617 |
| 77501 / 1 | +1,0764 | −6,0079 | −0,0003 | +0,0034 | −4,9284 |
| 77501 / 2 | +1,4748 | −8,6042 | +0,0007 | +0,0041 | −7,1247 |
| 77501 / 3 | +2,3589 | −0,5006 | +0,0002 | −0,0035 | +1,8549 |
| 77501 / 4 | −0,9264 | −0,7185 | +0,0016 | −0,0040 | −1,6473 |

¹ Bao gồm startup, precontact và contact trước lệnh phanh. File CSV/JSON và
bảng chi tiết tách cả ba; không gom startup thành nhiễu do contact. Sai số
cộng ở bảng chỉ do làm tròn.

Các trường hợp quyết định cách đọc:

- **77500/1:** phần tăng chủ yếu nằm trong phanh/giữ (+5,4785), dù trước can
  thiệp governor thấp hơn PI. Đây là cặp phù hợp để kiểm tra can thiệp trong
  early contact; riêng nó chưa chứng minh phanh gây slip.
- **77500/3:** phần tăng đã xuất hiện trước lệnh giảm tốc (+7,3466), rồi
  tăng tiếp trong phanh/giữ (+4,9182). Chỉ đổi recovery sẽ không giải thích
  hoặc xử lý được chênh lệch lớn này.
- **77501/3:** phanh/giữ thấp hơn PI (−0,5006), nhưng toàn tuyến vẫn cao hơn
  (+1,8549), do phần chênh lệch có trước can thiệp (+2,3589).
- **77500/2:** tích phân toàn tuyến thấp hơn, nhưng primary post-contact
  slip²/m cao hơn. Khác cửa sổ và quãng đường chuẩn hóa có thể cho dấu khác
  nhau; không thay primary bằng tổng tích phân để tuyên bố thắng.

![Phân rã đủ tám cặp](governor_survey_phase_audit_2026-10-20/all_eight_pair_phase_deltas.png)

Primary đã khóa vẫn giữ nguyên: block 77500 governor cao hơn khoảng 22,15%,
block 77501 thấp hơn khoảng 20,12%. Estimand relative benefit trung bình hai
block là −1,01%, CI95% [−24,21%; +15,68%], lấy nguyên từ khảo sát. Các pha
trong audit là giải thích hậu nghiệm, không được dùng chọn một subset có lợi.

## 4. Thân xe, bánh, motor và contact

### Trình tự và thời gian

Thứ tự **contact có tải được ghi nhận đầu tiên theo từng component** giống
nhau trong 16 lượt: caster trái → caster phải → bánh chủ động trái → bánh
chủ động phải. Có nhiều manifold begin/end và tái tiếp xúc trong chuỗi;
không rút gọn chúng thành bốn va chạm đơn độc.

- Governor bắt đầu publication giảm tốc ở **82–98 ms** sau manifold đầu.
- Caster phải bắt đầu có tải ở **70–91 ms** sau manifold đầu trong governor.
  Năm lượt đã có tải trước publication phanh; ba lượt còn lại chỉ cách
  publication **2–6 ms**. Không có bằng chứng đã thay đổi đáng kể vận tốc
  thân trước những tiếp xúc rất sớm này.
- Bánh chủ động trái chạm cáp có tải ở **609–628 ms**, bánh phải ở
  **742–780 ms**; giảm lệnh đã xảy ra trước các tiếp xúc muộn đó trong 8/8.
  Đây là bằng chứng thực thi lệnh, chưa tự chứng minh lợi ích outcome.
- Mẫu có tải cáp cuối cùng: PI khoảng **844–883 ms**, governor
  **901–940 ms**. Không coi crossing kéo dài là dữ liệu thiếu hoặc cắt bỏ.

### Phản hồi tại các đỉnh slip

Đỉnh GT slip lớn nhất của mỗi governor nằm ở **98–195 ms** sau contact đầu,
đều trong pha hạ lệnh tốc độ, trước khi bánh chủ động chạm cáp.
Vận tốc thân tại các đỉnh chỉ khoảng **0,176–0,234 m/s**, trong khi bánh phải
tại timestamp GT tương ứng khoảng **8,26–11,39 rad/s**. Bánh phải chạy nhanh
hơn vận tốc thân quy đổi tại bánh khoảng **0,331–0,559 m/s**.

Trong context as-of của bảy đỉnh có caster phải đang chịu tải cáp. Ở bảy
đỉnh có dữ liệu floor bánh phải đủ mới, không ghi nhận floor load theo
định nghĩa depth/force đã khóa; đỉnh còn lại **thiếu contact support đủ mới**,
được giữ là unavailable, không gán là không tiếp xúc. Một lượt có đỉnh trễ
hơn (77501/3, khoảng 195 ms) sau pha caster phải chạm cáp, với cả hai bánh
chủ động không ghi nhận floor load trong context đó.

Các thông tin này phù hợp với việc contact làm thay đổi tải bánh và thân,
trong khi vận tốc quay bánh khác chuyển động thân. Chúng **không chứng minh
bánh luôn mất tải liên tục**, không phân biệt dứt điểm contact numerics với
động lực học thật, cũng không xác nhận interference của bracket.

Wheel target và actual đều được giữ riêng. Ví dụ, ở 77500/1 governor,
target bánh phải quanh đỉnh từ drive publication gần nhất khoảng
6,11 rad/s, nhưng joint nội suy tại GT peak là 11,39 rad/s. Bản thân
`target − actual` là tracking error, không đồng nghĩa slip. Phải đối chiếu
với vận tốc thân/yaw để tính slip theo công thức gốc.

### Lệnh mô-men và giới hạn

| Quan sát trên dữ liệu đã lưu | PI | Governor |
|---|---:|---:|
| Max trị tuyệt đối applied torque command, bánh trái (Nm) | 0,8892 | 0,8923 |
| Max trị tuyệt đối applied torque command, bánh phải (Nm) | 0,6535 | 0,7126 |
| Max trị tuyệt đối requested torque command, hai bánh (Nm) | 1,5191 | 1,5606 |
| Publication có limited flag, trái / phải | 195 / 235 | 179 / 210 |
| Joint gốc vượt 12 rad/s, trái / phải, số mẫu | 0 / 4 | 0 / 6 |

Giới hạn cấu hình: torque 4 Nm, effort slew 10 Nm/s, wheel target acceleration
12 rad/s²; soft wheel speed mặc định của controller 12 rad/s. Đây là giới
hạn trong mô phỏng, chưa phải thông số motor thật được hiệu chuẩn.

Không publication nào chạm torque cap 4 Nm. Tất cả publication có limited
flag đều có requested torque dưới 4 Nm và wheel actual tại publication dưới
12 rad/s; theo thứ tự limiter trong source đã khóa, phù hợp với **effort
slew limiting**, không phải thiếu torque cap tại các publication đó.
Joint gốc khoảng 500 Hz vẫn ghi lại 4 mẫu PI và 6 mẫu governor vượt 12 rad/s
(max khoảng 12,297 và 12,412 rad/s). Không dùng dữ liệu drive 50 Hz để phủ
nhận các transient này hoặc suy ra mọi cập nhật vòng PI.

Mô-men trong bảng là **lệnh**, không phải phép đo shaft torque. Ở context
đỉnh, drive as-of có thể cũ khoảng 6–18 ms; không gọi đó là torque đo đúng
thời điểm peak. Contact force là force lấy mẫu, không suy ra impulse.
Attempt 8 có một khoảng cập nhật control 5 ms; vẫn giữ nguyên, không loại
episode hoặc cho rằng đây đã là nguyên nhân của chênh lệch slip.

## 5. Artifact và khả năng kiểm tra lại

- [Báo cáo máy và từng episode](governor_survey_phase_audit_2026-10-20/report.json).
- [Bảng từng pha](governor_survey_phase_audit_2026-10-20/phase_metrics.csv):
  coverage, duration, quãng đường, slip² integral/m, RMS; target/actual,
  tracking error, PI/requested/applied torque, limiter và body response.
- [Chênh lệch từng cặp](governor_survey_phase_audit_2026-10-20/pair_deltas.csv).
- [Mục lục tám đồ thị đầy đủ](governor_survey_phase_audit_2026-10-20/REPORT.md):
  slip, body/wheel speed, target/actual, torque/limiter, contact và IMU.
- [Toàn bộ manifold events trong route](governor_survey_phase_audit_2026-10-20/all_contact_events.json).
- Mỗi attempt có `all_gt_context.csv`, `all_imu.csv`, `all_contact_samples.csv`;
  giữ tất cả mẫu trong route, không chỉ các peak được nêu trong báo cáo.
- [Protocol trước tính toán](governor_survey_phase_audit_2026-10-20/protocol_before_calculation.json)
  và [hash/provenance](governor_survey_phase_audit_2026-10-20/provenance.json).

**Kiểm tra:** 70 hash đầu vào khảo sát gốc khớp; mọi input của audit không
đổi trong lúc đọc. Cả 16 lượt replay khớp native slip, GT slip toàn tuyến,
crossing, fixed post-contact, toàn chuỗi contact, cùng post-contact IMU
RMS/peak. Tổng tích phân/quãng đường theo pha và tổng delta từng cặp đều
khớp toàn tuyến. Các metric khác và native outcomes được giữ nguyên từ
báo cáo gốc, không tính lại điểm.

Sáu test offline kiểm tra mapping timestamp không dùng tương lai, receipt
và publication, thiếu execution/retrigger, PI event translation, bảo toàn
tích phân qua spike và biên pha, missing/gap, cùng giữ spike IMU và phân
biệt manifold không tải. Không test nào khởi động ROS/Gazebo.

```bash
cd ~/ninorobot
.venv/bin/python -m pytest -q src/nino_rl/test/test_governor_survey_phases.py
.venv/bin/python src/nino_rl/scripts/audit_governor_survey_phases.py \
  --output /tmp/nino_survey_phase_audit_review
```

Output phải là thư mục chưa tồn tại; các lệnh trên chỉ đọc dữ liệu simulation
đã lưu. Predictor, PPO, Optuna và triển khai thật tiếp tục giữ lại.
