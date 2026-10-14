# HƯỚNG NGHIÊN CỨU MỚI: NINO VƯỢT VẬT CẢN THẤP BẰNG ĐIỀU CHỈNH TỐC ĐỘ PHẢN ỨNG

**Ngày quyết định:** 13/10/2026, Asia/Bangkok.  
**Căn cứ:** người dùng yêu cầu áp dụng đánh giá Deep Research đã cung cấp. Đây là quyết định phạm vi và thiết kế thực nghiệm; không phải xác nhận độc lập rằng mọi nhận định trong đánh giá đã được chứng minh.

## 1. Câu hỏi chính

> Một bộ giám sát tốc độ chỉ dùng IMU, encoder và lịch sử lệnh có thể cải thiện
> chuyển động của robot vi sai có caster khi vượt vật cản thấp không được quan sát
> trước tiếp xúc, so với PI cố định và một bộ giảm tốc phản ứng được hiệu chỉnh tốt,
> mà vẫn giữ đến đích, bám đường và thời gian hợp lý hay không?

Tên mô tả đề xuất: **Proprioceptive Reactive Speed Adaptation for Differential-Drive Robots Traversing Low-Profile Floor Obstacles**.

“Không quan sát trước tiếp xúc” và “chưa gặp khi huấn luyện” là hai điều khác nhau.
Một layout mới chỉ được gọi là held-out khi nằm ngoài dữ liệu huấn luyện/tuning.
Chưa dùng tên “caster-aware” như một đóng góp đã chứng minh: robot thật không có
encoder caster. Caster được đo trong mô phỏng để chẩn đoán; actor chỉ có thể suy
luận tác động của nó qua cảm biến khả dụng.

## 2. Phạm vi thay đổi

| Hạng mục | Quyết định |
|---|---|
| Flat cable/rigid low obstacles | Phạm vi nghiên cứu chính |
| Rough, terrain randomization rough, rough Optuna | Tạm gác; giữ map/model/study, không chạy tiếp theo roadmap cũ |
| Combined map và chuyển policy | Không còn là mục tiêu của thí nghiệm đầu tiên; xét lại sau nếu cần |
| PI riêng từng bánh và bám đường | Giữ làm tầng nền và đối chứng |
| Phanh/phục hồi theo x=3.90/4.60 m | Giữ trong dữ liệu lịch sử, chỉ là diagnostic/oracle reference |
| Preview nhìn xuống hoặc ground truth trong actor | Loại khỏi contract mới |
| PPO | Phương pháp ứng viên; chưa mặc định là giải pháp cuối |
| Optuna | Chỉ mở khi runtime/vật lý ổn định và có giả thuyết điều khiển kiểm tra được |
| TensorBoard/Laya | Theo dõi; không phải đóng góp điều khiển hoặc quyền thay đổi thí nghiệm |
| Sim-to-real | Mục tiêu cần đo đạc/thực nghiệm phần cứng; chưa có kết quả |

Không có worker rough train/tune đang chạy được tìm thấy khi chuyển hướng.
Các runtime frozen và checkpoint cũ không được sửa để biến chúng thành kết quả
của đề tài mới.

## 3. Contract cảm biến và điều khiển

### Actor/supervisor

Runtime mới chuẩn bị lịch sử **18 giá trị × 5 frame = 90 đầu vào**:

- Roll/pitch IMU, ba vận tốc góc, ba gia tốc.
- Vận tốc encoder trái/phải.
- Lệnh vận tốc thẳng/quay yêu cầu và lệnh đã thực thi từ drive diagnostics.
- Hệ số tốc độ thực thi đã lọc.
- RMS/peak gia tốc đứng theo khoảng hành động và tỷ lệ coverage IMU.

**Không đưa vào:** tọa độ robot/vật cản, khoảng cách đích, path progress, thời gian
episode, range LiDAR, preview, force/contact hoặc joint state caster mô phỏng,
vận tốc ground truth. Quan sát được tạo bằng danh sách field tường minh, không
slice/mask ngẫu nhiên từ observation cũ.

LiDAR và pose ước lượng vẫn có thể dùng ở tầng định vị/bám đường và dừng vật cản
lớn. Đây là giới hạn actor, không phải yêu cầu tháo LiDAR khỏi toàn hệ thống.
Requested command có thể phản ánh giảm tốc đến đích của bộ bám đường; nó không
chứa lịch kích hoạt theo vị trí cáp. Layout cáp được thay đổi giữa các scenario.

### Control authority

Giữ PI và bộ bám đường flat của profile đã lưu. Supervisor chỉ thay đổi tốc độ,
không thêm torque hoặc yaw residual trong screen. Hệ số 0.55–1.00, slew 0.4/giây,
control 0.1 s, physics 0.001 s.

Bộ reactive tham chiếu phát hiện nhiễu từ gia tốc đứng, tốc độ quay thân và sai
lệch vận tốc bánh so với **lệnh thực thi**. Nó yêu cầu scale 0.70 trong 0.80 s,
sau đó phục hồi và cooldown. Đây là starting configuration cần thử trên flat,
không được gọi là bộ reactive đã tối ưu cho flat. Duration được kiểm tra đủ để
giảm 1.00→0.70 ở ramp khai báo; phản hồi motor thực tế mới xác nhận mức đạt được.

Độ trễ actuator/filter và việc speed scaling ảnh hưởng yaw ở adapter cũ vẫn phải
được kiểm tra bằng drive/trajectory trace. Không tuyên bố steering độc lập với
speed khi chưa đo/đổi contract. Không chuyển thẳng categorical actor rough hoặc
checkpoint flat cũ sang observation 90 giá trị.

## 4. Vật lý và tính hợp lệ của mô hình

Obstacles hiện là **cylinder cứng nằm ngang**, center z=radius nên chiều cao bằng
2×radius. Không mô phỏng dây mềm, biến dạng, kéo dây hoặc bảo vệ cáp có tiết diện
ramp. Kết luận trước mắt giới hạn ở rigid circular cable-like obstacles.

Bundle mới có hai robot riêng:

1. **Original:** damping trục bánh caster 0.01 N·m·s/rad.
2. **Candidate:** 0.001 N·m·s/rad; cùng geometry, mass, friction và swivel damping.

Sensor preview ảo được tắt trong cả hai; link vật lý vẫn giữ. Candidate chưa
được xác nhận tốt hơn và không thay model chính. Đo actual caster rolling,
reset/settling, penetration, motor response và IMU để chọn profile nền trước PPO.
Contact/solver force chỉ là dữ liệu chẩn đoán, không phải lực đo đã hiệu chuẩn.

## 5. Scenario và phân chia dữ liệu

Spec: `src/nino_rl/config/flat_proprioceptive_research.yaml`.
Bank được chuẩn bị tại `rl_runs/flat_proprioceptive_v1/scenarios.json`.

| Stage | Mục đích | Geometry/layout hiện đã chuẩn bị |
|---|---|---|
| A | Cơ chế phản ứng một obstacle | Một cylinder, vị trí/angle/radius biến thiên |
| B | Nhiều sự kiện | 1–6 cylinder, center spacing tối thiểu 0.55 m |
| C | Hướng tiếp cận/caster | Kế hoạch tương lai; chưa có turning-route contract |

Mỗi stage A/B có **48 train, 12 validation, 24 test**, tổng cộng 168 layout.
Các split có seed/layout riêng; test còn dùng radius chưa có trong train/validation.
Training radius 6/8/10 mm; test radius 7/9/12 mm. Vị trí x nằm trong 1.50–4.90 m,
angle trong −30°…+30°. Các giá trị là dải thí nghiệm mô phỏng, chưa phải phân bố
vật cản hoặc độ khả thi đã đo trên robot thật.

Runtime sample ở mỗi reset cung cấp x/radius/angle trực tiếp cho API spawn
collision/visual cylinder. Đây là thay đổi hình học vật lý, không phải nhân
residual torque giả làm randomization. Trong screen, scenario được khóa bằng ID
để controller và các lần lặp gặp cùng layout. Việc gọi API spawn đã được kiểm tra
ở mức code/static; xác nhận live bằng tiếp xúc/pose là công việc screen tiếp theo.

Validation dùng chọn tham số. Test giữ lại cho kết luận cuối, không dùng tuning,
teacher data hoặc chẩn đoán để sửa model. Các cặp sát nhau, tiết diện khác và route
rẽ chưa được tạo hoặc được tính là đã kiểm tra; cần feasibility/new contract trước
khi bổ sung. Randomization dynamics/friction chưa bật trong stage này.

## 6. Thực nghiệm nhỏ đầu tiên

**Không train ngay.** Chuẩn bị 3 layout single-obstacle thuộc train split,
full PI và reactive PI, 2 cold repetitions, đảo thứ tự controller ở lần lặp thứ
hai: **12 episode/profile vật lý**. Original và damping candidate là hai screen
riêng, tổng 24 episode nếu chạy cả hai.

Mỗi episode khởi động simulator mới để tránh carryover caster. Ghi control,
drive, contact và caster reset/joint trace; yêu cầu xác nhận runtime Bullet.
Command-clock correction và timing checks của bundle flat trước được giữ.
Feedback thực thi stale/missing gây lỗi rõ ràng, không giả thành ride êm.

Phân tích cần tách:

- Impact đầu tiên: chỉ dùng để mô tả; không kỳ vọng IMU phản ứng trước tín hiệu.
- Độ trễ từ tín hiệu IMU/encoder đến giảm tốc thực thi.
- Contact tiếp theo, rung/slip trong crossing và phục hồi.
- Giữ tốc độ thấp quá lâu, tăng tốc gây slip, lệch hướng hoặc stall.
- Lặp cùng scenario có đủ ổn định để phân biệt tác động controller hay không.

Window chất lượng dùng vị trí vật lý chỉ ở **analysis**, không ở control. Script
hiện xuất window quanh obstacle và tổng hành trình; cần dùng contact trace để xác
định component/order và impact đầu tiên. Nếu chưa đến window, ghi unavailable;
failed arrival vẫn tính. Các kết quả screen không tự giải phóng training/Optuna.

## 7. Đối chứng và điều kiện đi tiếp

1. **Full-speed PI:** điều khiển nền không thích nghi.
2. **Reactive PI:** baseline chính; tune hữu hạn trên train/validation khi cơ chế
   và vật lý đủ ổn định. Các giá trị khởi đầu không phải kết quả tuning.
3. **Time-matched PI:** chạy sau khi đo thời gian reactive; đo độ khớp thực tế,
   không gán nhãn time-matched cho một scale đoán trước.
4. **PPO:** một pilot mới khi có authority có thể học, không cần tự động thắng
   reactive trước mọi hoạt động tuning.

Arrival vật lý 0.20 m, mean time ≤18.5 s và tracking ≤1.05×full PI là mục tiêu
engineering giữ cho screen flat này. Mục tiêu gain 10% và không làm quality metric
còn lại xấu hơn là tiêu chuẩn triển khai đang dùng, **không phải ngưỡng khoa học
đã chứng minh phù hợp mọi ứng dụng**. Báo cáo effect size và uncertainty; budget/
time cho stage B/C phải chốt lại trước trial vì số lượng và chiều cao có thể đổi
bài toán. Không âm thầm thay gate sau khi thấy kết quả.

### Các gate khác nhau

| Gate | Điều kiện |
|---|---|
| Foundation | Reset/timing/feedback/contact hợp lý; geometry có khả năng vượt; scoring vật lý đáng tin |
| Authority | Một can thiệp phản ứng thay đổi được đoạn sau tiếp xúc; lợi ích/chi phí có thể đo và lặp lại |
| Pilot học | Quan sát và exploration hỗ trợ hành vi; actor thể hiện phản ứng và recovery |
| Focused Optuna | Runtime/objective cố định, trial so sánh được, rollout/evaluation đủ thông tin để xếp hạng |
| Promotion/deployment | Reliability, tracking, time và quality đạt yêu cầu trên held-out conditions và hardware khi tuyên bố thật |

Nếu contact/caster chưa hợp lý: xử lý model hoặc cơ khí, không tăng reward penalty.
Nếu cơ chế phản ứng không có cửa sổ cải thiện sau impact: thu hẹp claim, đổi loại
obstacle/sensing hoặc dừng RL cho mục tiêu này. Nếu reactive đơn giản đáp ứng tốt
nhưng PPO không có lợi ích thêm: có thể chọn reactive làm giải pháp ứng dụng và
báo cáo kết quả âm của RL. Không mặc định cần một pipeline BC/PPO phức tạp.

## 8. Lộ trình sau screen

- Chọn profile vật lý có căn cứ; hoàn thành calibration/time-matched PI.
- Chốt action formulation và reward cho actor mới; continuous speed/rate và
  BRAKE/HOLD/RECOVER là phương án cần so sánh, không kế thừa tự động rough.
- Một pilot 20,480 bước, actor/critic/optimizer mới dưới contract mới.
- Nếu pilot học được phản ứng, focused tuning giới hạn learning settings và vài
  reward weights với objective cố định; dùng validation, giữ test độc lập.
- Xác nhận bằng nhiều training seed và held-out layout/dynamics. Ablation IMU,
  encoder/history phải train phù hợp, không chỉ làm mất sensor gây distribution shift.
- Sim-to-real sau driver/PI và sensor timing được đo, calibration caster/motor,
  và thử thật trên vật cản thấp có giới hạn. Không suy ra hiệu quả thật từ Gazebo.

## 9. Commands hiện đã chuẩn bị

Terminal chuẩn bị, không mở simulator:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/prepare_flat_reactive_research.py
python src/nino_rl/scripts/run_flat_reactive_screen.py --physics original
python src/nino_rl/scripts/run_flat_reactive_screen.py --physics caster_damping_candidate
```

Chạy screen khi sẵn sàng; runner tự mở/đóng Gazebo của mình. Không mở thêm flat
Gazebo trong domain 79/partition `nino_flat_79` cùng lúc:

```bash
python src/nino_rl/scripts/run_flat_reactive_screen.py --physics original --run
python src/nino_rl/scripts/run_flat_reactive_screen.py --physics caster_damping_candidate --run
```

Runner giữ episode đã hoàn thành và bỏ qua chúng khi gọi lại cùng command.
Ctrl+C đóng các process do runner mở; các lần chưa hoàn thành chạy lại. Manifest
hash kiểm tra input, library và code; thay spec/code cần output/contract mới.
Không nối study Optuna cũ hoặc checkpoint rough cũ vào output mới.

Kết quả nằm dưới `rl_runs/flat_proprioceptive_v1/screens/<physics>/`.
`analysis.json` và `REPORT.md` chỉ được tạo khi screen đủ episode.

## 10. Trạng thái khi chuyển hướng

- Đã sửa README và thêm scope/spec/code cho protocol mới.
- Đã chuẩn bị bank, runtime sensor-only, robot/world riêng và screen plan.
- Unit tests kiểm tra input leakage, chuỗi reactive, layout/split và cách giữ failed arrival.
- **Chưa mở simulator, chạy screen, train PPO hoặc Optuna trong lần chuyển hướng này.**
- Main robot, rough/flat checkpoints và các kết quả lịch sử được giữ.

Tham khảo hiện trạng trước chuyển hướng:
[rough/flat result](ROUGH_PHASE_ANCHOR_RESULT_2026-10-12.md),
[flat contact audit](flat_peak_contacts_2026-10-12/REPORT.md),
[báo cáo tổng quan lịch sử](TONG_QUAN_DU_AN_RL_NINO_2026-10-12.md).
