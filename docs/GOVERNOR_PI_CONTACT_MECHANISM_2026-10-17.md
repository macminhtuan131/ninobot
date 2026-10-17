# Audit PI–PI: contact, caster và pha IMU — 17/10/2026

**Bước chuẩn bị tiếp theo:** [protocol H2 có lặp, tối đa 16 attempts](GOVERNOR_H2_REPLICATION_PROTOCOL_2026-10-17.md)
đã chuẩn bị riêng; chưa cấp ngân sách/chạy. Người dùng chưa có yêu cầu nhà
máy nên ngưỡng lợi ích/chi phí thời gian còn trống. Audit dưới đây giữ nguyên
kết luận và phạm vi bốn trace lịch sử.

## Quyết định

**Biến thiên trạng thái tiếp xúc/chuyển động có thật trong trace; reporting
lấy mẫu thưa cũng nhạy với spike. Chưa xác định được một lỗi vật lý hoặc
instrumentation duy nhất để sửa.** Không chọn correction PI, detector,
damping, geometry hoặc tần số IMU từ audit này. Không thử delay khác;
200 ms tiếp tục bị loại, mặc định 0 ms.

Audit trả lời ba câu hỏi bằng đúng bốn cold starts PI đã lưu. Không chạy
simulation, predictor, PPO hoặc Optuna. Không thay native metrics, study
scores, spike hay danh sách attempts. Cả bốn arrival và dừng 2 s vẫn được
giữ; batch này không có arrival failure để loại khỏi báo cáo.

**Dừng nhánh can thiệp nhỏ dựa trên một lượt mỗi phương án.** Audit không
xác nhận H2 về lợi ích can thiệp vì bốn lượt đều PI full, không có governor
can thiệp. Không mở một vòng audit/pilot tiếp từ cùng dữ liệu chỉ để tìm
tham số thuận lợi. Nếu cấp ngân sách mới, cần yêu cầu lợi ích có ý nghĩa
ứng dụng và thiết kế lặp/blocked comparison đủ xử lý biến thiên; không đòi
mô phỏng tất định, cũng không lấy PPO thắng PI làm điều kiện cho mọi tuning.

## 1. Phạm vi và phương pháp

- Input: bốn lượt seed 77400/77401, hai lần/seed của
  [batch PI-only](GOVERNOR_POST_RESET_PI_REPEATABILITY_2026-10-17.md).
- Contact theo header timestamp gốc; phân biệt **manifold bắt đầu** và
  **mẫu chịu tải**: depth >0 và norm lực >1e-6 N. Tổng norm các điểm của
  một manifold là sampled-load diagnostic, **không phải impulse** hoặc
  phép đo tải liên tục chính xác.
- IMU ở timestamp gốc; công thức vertical acceleration giữ nguyên từ
  governor core, gravity compensation theo config đã lưu. GT và joint
  dùng header; drive lookup chỉ dùng mẫu đã có trước hoặc tại thời điểm
  cần kiểm tra, có giới hạn age. Các trạng thái +20/+40 ms được ghi rõ là
  sau peak, không được dùng làm đầu vào nhân quả của peak.
- Cửa sổ bổ sung first manifold → +3 s giống nhau cho cả bốn lượt. Đây là
  sample RMS chẩn đoán, **không thay native whole-route/crossing RMS**.
- Bốn attempts đều được đọc. Không loại top samples, không winsorize,
  không đổi objective sang percentile thuận lợi.

## 2. Peak lớn có đi kèm contact và phản hồi cơ học không?

**Có sự đi kèm theo thời gian; chưa chứng minh quan hệ nguyên nhân duy nhất
hoặc độ lớn gia tốc thật trên phần cứng.**

| Seed/lặp | Peak sau contact, cửa sổ 3 s (m/s²) | Thời điểm sau first manifold | Bối cảnh |
|---|---:|---:|---|
| 77400/1 | **80.973** | +62 ms | Pha caster; tải caster trái lớn ở +7 ms, thân/bánh biến động rõ |
| 77400/2 | 13.638 | +84 ms | Trùng mẫu caster phải chịu tải cáp |
| 77401/1 | 9.550 | +590 ms | Sau bánh chủ động trái bắt đầu chịu tải |
| 77401/2 | **67.103** | +717 ms | Trùng mẫu bánh chủ động phải chịu tải cáp khoảng **430.8 N** |

### Seed 77400

- Lượt 1: caster trái có mẫu chịu tải khoảng **255.4 N tại +7 ms**.
  Peak IMU +62 ms xảy ra **55 ms sau mẫu đó**, không được gọi là lực và
  peak đồng thời hoặc dùng mẫu caster phải ở +82 ms làm nguyên nhân đã có
  trước peak.
- Ở +42 → +62 ms, GT vz thay đổi **−0.0272 → −0.0745 m/s**; vận tốc bánh
  trái từ joint **6.880 → 3.588 rad/s**. Tại peak, GT wx/wy khoảng
  **−0.396/−0.330 rad/s**. Có chuyển động thân và phản hồi bánh đi kèm,
  không chỉ một số RMS sau resampling.
- Lượt 2 cũng có phản ứng caster và hụt tốc. Peak +84 ms trùng mẫu caster
  phải khoảng **163.6 N**. Vì vị trí peak trong chuỗi khác nhau, không so
  hai peak như thể cùng một contact phase có trạng thái giống hệt.

### Seed 77401

- Lượt 2: bánh phải có mẫu chịu tải khoảng **430.8 N tại +717 ms**, cùng
  timestamp peak 67.103 m/s². Joint bánh phải **6.349 → 4.981 rad/s** từ
  +697 → +717 ms; GT vz **−0.0100 → −0.0328 m/s**. GT wx sau thêm 20 ms
  đạt khoảng **−0.768 rad/s**.
- Drive trước peak 18 ms còn target bánh phải khoảng **6.375 rad/s** và
  executed linear command khoảng **0.400 m/s**. Không có BRAKE/RECOVER;
  độ trễ của mẫu drive được giữ rõ, không đồng nhất nó với joint tại peak.
- Một diagnostic bổ sung sau khi xem đồ thị, dùng cùng cửa sổ **+0.8–1.0 s**
  cho mọi lượt: bánh phải lượt 1 quay âm lần đầu ở +864 ms, min **−0.689
  rad/s**; lượt 2 không có mẫu âm, min **6.196 rad/s** trong cửa sổ này.
  Như vậy **lượt có peak IMU nhỏ hơn vẫn có phản hồi bánh xấu ở pha sau**.
  Không dùng cửa sổ thăm dò này làm quality gate mới.

Whole-route peak 9.844 m/s² của 77401/1 nằm **trước cáp 5.53 s**. Bảng trên
dùng postcontact peak 9.550 để không gộp startup/clean-floor peak với
crossing. Whole-route peak và native outcome ban đầu vẫn giữ nguyên.

## 3. Caster và thứ tự contact bắt đầu khác ở đâu?

### Thứ tự manifold không đổi, thời điểm chịu tải có đổi

Cả bốn lượt có thứ tự first manifold: **caster trái → caster phải → bánh
chủ động trái → bánh chủ động phải**. Không có bằng chứng đảo thứ tự này.

| Seed/lặp | Caster trái chịu tải (ms) | Caster phải (ms) | Bánh trái (ms) | Bánh phải (ms) |
|---|---:|---:|---:|---:|
| 77400/1 | 1 | 82 | 573 | 705 |
| 77400/2 | 2 | 84 | 597 | 702 |
| 77401/1 | 3 | 84 | 579 | 715 |
| 77401/2 | 0 | 85 | **618** | 717 |

Mốc 0 là first manifold của từng lượt, không phải timestamp engine chung.
Bánh trái bắt đầu có mẫu chịu tải chậm hơn **24 ms** ở 77400/2 và **39 ms**
ở 77401/2. Việc manifold xuất hiện chưa tự chứng minh đã chịu tải.

### Trạng thái caster đã khác trước cáp

- **Ngay ở gate release**, swivel caster trái/phải của cặp 77400 lần lượt
  khoảng `(0.000061, −0.000637)` và `(0.000478, 0.000073)` rad. Cặp 77401
  khoảng `(0.000057, 0.000089)` và `(−0.000189, −0.000087)` rad. Đây là
  khác biệt nhỏ quan sát được, **không phải bằng chứng rằng góc nhỏ này gây
  spike**. Gate kiểm tra đứng yên, không khôi phục cùng trạng thái contact.
- Trong cửa sổ **1.0–1.5 s sau release**, vẫn trên sàn sạch, tỷ lệ mẫu
  caster phải chịu tải sàn của 77401/1 và /2 là khoảng **6.7% và 27.3%**;
  caster trái khoảng **100% và 77.3%**. Phân bố support đã khác trước cáp.
- Ở mốc GT x≥1 m, caster phải của 77401/1 và /2 có tốc độ quay gần nhất
  khoảng **15.79 và 0.0167 rad/s**. Cặp 77400 cũng khác trạng thái quay
  từ trước cáp. Đây là mốc GT lấy mẫu đầu tiên qua 1 m, không exact-state
  branching hoặc phép đo slip caster.
- Trong approach −300→−50 ms, median caster phải của cặp 77400 là
  **1.281/1.965 rad/s**, cặp 77401 **1.946/4.576 rad/s**. Body speed/pose
  cân bằng thô không bảo đảm support state giống nhau.

Không xác định được **thời điểm phát sinh nguyên nhân đầu tiên**: cold starts
không cùng microstate, và differences đã tồn tại tại boundary đầu quan sát.
Không quy low rolling của caster ít tải thành trượt hoặc lỗi damping; không
đề xuất kéo dài gate/ép caster quay hoặc sửa geometry từ các khác biệt này.

## 4. Độ nhạy với pha IMU: biết được gì và chưa biết gì?

IMU header trong cả bốn episode cách nhau **20 ms**, không có duplicate hoặc
gap lớn hơn 20 ms trong đoạn đã đọc. Receipt age quan sát 0–6 ms; phân tích
ở đây dùng header, không dùng thời điểm nhận callback.

Mẫu IMU đầu sau first manifold xuất hiện ở **+2/+4 ms** cho 77400/1,/2 và
**+10/+17 ms** cho 77401/1,/2. Pha acquisition tương đối contact có khác,
nhưng không có tín hiệu IMU tần số cao để tính counterfactual nếu lấy mẫu
sớm/muộn hơn. **Không thể xác nhận acquisition aliasing là nguyên nhân**.

Các kiểm tra bổ sung, không thay score:

| Seed/lặp | RMS mẫu gốc 50 Hz, +3 s | RMS trên 10 grid nội suy 50 Hz¹ | RMS trên 5 residue lấy thưa 10 Hz² |
|---|---:|---:|---:|
| 77400/1 | **7.743** | 6.725–7.743 | 1.426–14.823 |
| 77400/2 | 2.012 | 1.516–2.012 | 1.477–2.709 |
| 77401/1 | 1.811 | 1.330–1.811 | 0.680–2.701 |
| 77401/2 | **5.640** | 3.799–5.337 | 0.637–12.310 |

¹ Nội suy tuyến tính các mẫu **đã lưu**, query 50 Hz với offset sau contact
0,2,…,18 ms. Không extrapolate/đi qua gap. Không phải mô phỏng lại sensor ở
pha acquisition khác. Range chỉ của 10 offset đã thử; pha gốc +17 ms của
77401/2 không nằm trong tập offset đó, nên raw RMS vẫn báo riêng.

² Mọi residue `samples[i::5]`, i=0…4, không nội suy; giữ dữ liệu gốc đầy đủ
bên cạnh, không chọn residue thuận lợi để chấm điểm. Pha bắt đầu từng residue
khác theo run, không coi đây là identical-phase sensor experiment.

- Hai mẫu lớn nhất chiếm **93.6%** và **95.6%** tổng bình phương gia tốc
  mẫu trong cửa sổ 3 s của 77400/1 và 77401/2. **Giữ nguyên các mẫu đó**.
- Các range nội suy 50 Hz của hai lượt cùng seed **không chồng nhau** trong
  kiểm tra này: downstream grid shift được thử chưa giải thích hết chênh lệch.
- Lấy thưa 10 Hz có thể bỏ lỡ peak, và residue có thể đảo xếp hạng. Ví dụ
  residue 0 ở 77400 cho RMS **1.836/2.259**, ngược với raw **7.743/2.012**.
  Đây là độ nhạy reporting, không chứng minh controller nào tốt hơn.
- GT/joint/contact cũng khác. Không quy toàn bộ outcome cho IMU sampling;
  cũng không coi force sample và IMU peak tương quan là validation mô hình
  sensor/contact hoặc sim-to-real.

## 5. Quyết định kỹ thuật và điểm dừng

| Câu hỏi | Kết luận | Mức chắc chắn trong bốn trace |
|---|---|---|
| Peak lớn có phản ứng cơ học đi kèm? | Có; đặc biệt 77401/2 peak và tải bánh phải đồng timestamp | Cao về association, chưa chứng minh nguyên nhân |
| Contact sequence có bị đảo? | Không; load onset và trạng thái caster khác | Cao trong dữ liệu đã ghi |
| Sampling phase có ảnh hưởng? | Reporting lấy thưa rất nhạy; acquisition 50 Hz chưa định lượng được | Cao về diagnostic, chưa xác định acquisition effect |
| Đủ căn cứ sửa PI/detector/physics? | **Chưa** | Không chọn correction mới |

Giữ PI/detector/ramp/geometry/IMU rate và physical scoring hiện tại. Không
lọc spike, sửa study score, thử delay khác hoặc mở tuning một lượt/trial.
Audit này kết thúc ở đây; không đề xuất thêm audit từ cùng bốn trace như
một cách trì hoãn quyết định. Muốn mở lại thử nghiệm cần một mục tiêu lợi
ích ứng dụng và protocol có replication/uncertainty phù hợp, hoặc bằng
chứng hiệu chuẩn vật lý mới đủ để chọn đúng một correction.

## 6. Kiểm tra và artifacts

- **4 tests đạt**: lookup không lấy future/stale feedback; manifold/zero
  depth không thành load; spike và đủ mọi residue vẫn được giữ; gap không
  được nội suy âm thầm. Đây không phải toàn bộ repository test suite.
- **258 file input/runtime/config được hash trước–sau, không đổi**. Nguồn
  audit/test mới và tài liệu này được bổ sung; không sửa runtime controller.
- Hình đã kiểm tra trực quan; cảnh báo Axes3D của Matplotlib không ảnh hưởng
  đến plot 2D hoặc phép tính.

Artifacts: [analysis.json](governor_pi_contact_mechanism_2026-10-17/analysis.json),
[quyết định](governor_pi_contact_mechanism_2026-10-17/decision.json),
[verification](governor_pi_contact_mechanism_2026-10-17/verification.json),
[đồ thị đối chiếu](governor_pi_contact_mechanism_2026-10-17/contact_aligned_pairs.png).
Timeline contact JSON và IMU/GT/joint CSV cho từng run nằm cùng thư mục.

Tái tạo audit vào thư mục **mới**:

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/audit_pi_contact_mechanism.py \
  --rows docs/governor_pi_repeatability_2026-10-17/episodes.json \
  --output /tmp/nino_pi_contact_mechanism_replay
```

Lệnh chỉ đọc trace và tạo diagnostic artifacts. Không gọi ROS/Gazebo.
