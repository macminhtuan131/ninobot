# Đánh giá lại báo cáo mới và GUI tiến độ Nino — 03/11/2026

## 1. Kết luận và phạm vi

**Ưu tiên motion contract và kiểm chứng wheel/body; chưa mở một chiến dịch
PPO hoặc độ lặp mới ngay.** Dữ liệu local mới hơn báo cáo đính kèm cho thấy
một bất đồng cần giải quyết: final command và reported feedback tăng trong
lượt V2 nhưng người vận hành báo xe không tiến. Một diagnostic có video
thấy bánh, thân và mốc sàn có giá trị hơn thêm trace encoder đơn độc.

- **[N]** Bằng chứng chính là [inventory/status](NINO_REAL_DATA_STATUS_2026-11-03.md)
  và [checklist real data](NINO_REAL_DATA_CHECKLIST_2026-11-03.md): 15 bag local,
  hai lượt được operator báo tiến/tự dừng, chưa có campaign độ lặp hoàn chỉnh,
  body reference độc lập hoặc body stopping/slip định lượng đã review.
- **[S]** Báo cáo mới hữu ích ở định hướng baseline mạnh, phân biệt input sim
  với hardware, và yêu cầu reference độc lập. Nhiều khẳng định về hiện trạng,
  cơ chế, rate và ngưỡng cần sửa trước khi dùng làm quyết định.
- **[Đ]** Kế hoạch bên dưới là đề xuất có gate. Lần sửa này chỉ thay GUI,
  hồ sơ và đánh giá dữ liệu; không SSH, flash, enable, chạy robot, mô phỏng,
  chỉnh gain/current, đổi StopZone hoặc cấp ngân sách mới.

Báo cáo đính kèm ngày 02/11 được đọc như nguồn phản biện, không phải dữ liệu
thay thế raw. Đường dẫn/hash attachment và nguồn nội bộ được giữ trong
`nino_pi/project_evidence.json`. Snapshot có ngày chốt; kết nối Pi không tự
làm snapshot trở thành inventory live. Chưa kiểm kê lại Pi trong lần này.

## 2. Những nhận định cần chỉnh

| Nội dung báo cáo | Đối chiếu / quyết định |
|---|---|
| Chỉ có một bag chuyển động, pilot 0/3 | **[N]** Status 03/11 ghi hai phiên operator xác nhận tiến/tự dừng, nhiều failed/unknown và các ledger đóng. Không đếm các phiên đó thành ba repeats và không mở lại pilot v2 |
| Encoder/IMU thật 500 Hz; STM32 đóng PI vận tốc 500 Hz | **[N]** Inventory quan sát khoảng 47,13 Hz. `CONTROL_PERIOD_MS=2` là source scheduling; source `motor_task.c` velocity path ghi SPD_REF, actuator đóng vòng vận tốc. Binary/mode đang chạy chưa readback độc lập đầy đủ |
| Robot dùng DC/PWM/hộp số; phải bù deadzone PWM/STM32 PI | **[N/S]** Người dùng xác nhận CyberGear CAN. Không có bằng chứng để sửa PWM/gain theo mô hình báo cáo; xác minh backend và telemetry trước |
| Rev30/downward LiDAR/300 features là controller hiện tại | **[N/S]** Là thông tin lịch sử cần gắn config/checkpoint cụ thể. Governor đang xét là sensor-only; không xóa observation/controller đang dùng theo nhãn revision trong report |
| Governor kém do chồng speed_scale PPO | **[N/S]** Survey PI/reactive không có evidence PPO cùng chạy. Giả thuyết này không giải thích survey; H2 timing/contact và H3 vẫn chưa xác lập |
| Bỏ scan/TF khỏi wheel pilot | **[Đ]** Full SLAM/Nav2 không cần cho wheel ID. Tuy nhiên chuỗi hiện dùng Collision Monitor nên TF scan→thân và scan freshness vẫn là phụ thuộc thực, không bỏ STOP để chạy |
| Encoder zero = thân dừng | **[S]** Chỉ là reported-wheel settling. Dừng thân phải dùng reference độc lập, clock, uncertainty và dải noise+dwell; không yêu cầu float chính xác bằng zero |
| Yaw mismatch phát hiện slip khi cả bánh quay nhưng thân đứng | **[S]** Với full track b, `yaw_enc=(Rr*ωr−Rl*ωl)/b`. Cả bánh cùng trượt dọc đối xứng vẫn có yaw residual gần zero. Đây là consistency proxy, không slip measurement |
| Torque RMS / action differences = năng lượng / jerk | **[S]** Torque RMS không là J; cơ năng cần tích phân τ·ω, điện năng cần V·I. Bình phương sai phân action chưa chia thời gian, units và signal order không tự là physical jerk |
| Trừ mean a_z tĩnh là rung thân chuẩn trong mọi thao tác | **[S]** Chỉ là proxy trong orientation hẹp. Cần gravity/frame/rotation, lever arm và bandwidth để diễn giải khi nghiêng/quay; không suy force/damage từ IMU peak |
| CV<3%, asym<5%, stop<150 ms; tăng lên .2–.4 m/s sau ba lượt | **[Đ]** Chưa là ngưỡng chấp nhận. Không thêm vào GUI như runtime/safety gate, không tăng tốc tự động. Ba lượt pilot không chứng minh độ tin cậy triển khai |
| N≥10–20 hay ≥50 là chuẩn đủ của mọi đánh giá | **[S]** Cỡ mẫu phải theo estimand/biến thiên/effect và đơn vị độc lập. K/N là số đếm nguyên: success 95% không khả dĩ ở N=3,5,10. Không dùng một bảng CI với cùng p=.95 để đại diện các thử nghiệm ấy |
| Corner LiDAR mm, delay Pi 15–45 ms, stack 300 ms đủ contact | **[S]** Chưa được đo ở Nino. Corner scan có thể là reference cần validation, không GT mm mặc định. Ba frames cách 100 ms span 200 ms từ đầu đến cuối; chưa tính actuator lag |
| Lockstep có độ trễ vật lý tuyệt đối bằng zero | **[S]** Pause wall time không xóa cadence, sensor delay, ramp/slew hoặc response cơ học. Không gán latency thật từ mô phỏng |

**[S]** CI governor rộng, đổi dấu nghĩa là chưa có evidence lợi ích ổn định;
không chứng minh hiệu ứng bằng zero hay mọi −1,01% là noise. Không thay
estimand, chọn grid có lợi, loại spike hoặc tự tăng sample size.

## 3. Kiểm nguồn bên ngoài có ảnh hưởng đến khuyến nghị

Tra cứu 03/11/2026; phạm vi lần này là landing page/abstract nguồn gốc,
không review lại 12–20 bài hoặc xác minh toàn bộ con số trong báo cáo.

- **[T]** [Omi et al., arXiv:2307.15931 v3](https://arxiv.org/abs/2307.15931v3)
  là bản sửa năm 2026, mô tả rover case **simulation-based**. Có hỗ trợ nghiên
  cứu action/observation history; không chứng minh caster thật vượt cáp.
- **[T]** [Gao et al., arXiv:2301.13283](https://arxiv.org/abs/2301.13283)
  nghiên cứu online adaptation lateral predictive/longitudinal PID gains.
  Không suy từ abstract rằng Nino cần RL hay tiếp xúc cáp đã được giải quyết.
- **[T]** [Amano & Azumi, arXiv:2609.28969](https://arxiv.org/abs/2609.28969)
  dùng WHILL/AWSIM/ROS2, Bayesian system ID và DreamerV3; abstract có transfer
  tránh hộp thật. Nó không kiểm contact authority hoặc PI của Nino.
- **[T]** [Johannink et al., arXiv:1812.03201](https://arxiv.org/abs/1812.03201)
  có thực nghiệm block assembly. Hỗ trợ ý tưởng residual chung, không là
  bằng chứng trực tiếp cho AMR vi sai/caster.
- **[T]** [Agarwal et al., NeurIPS 2021](https://arxiv.org/abs/2108.13264)
  nhấn mạnh uncertainty và robust aggregate metrics trên benchmark RL.
  Không dùng nó làm một chứng nhận cỡ mẫu duy nhất cho ba lượt commissioning Nino.

Các kết quả phần trăm RL, precision mm, rate actuator và ngưỡng thời gian
chưa có nguồn/đo đủ trong lần này giữ là **chưa xác minh**, không đưa vào GUI
như số đo Nino. Chưa có cơ sở tuyên bố novelty hoặc cam kết mức cải thiện.

## 4. Điều chỉnh hướng dự án

| Nhánh | Quyết định | Điều kiện đổi hướng |
|---|---|---|
| Motion contract / wheel-body diagnostic | Ưu tiên; tái dùng raw collector, trace và profile thấp hiện có | Có đối chiếu thực vật lý/clock hợp lệ, hoặc lỗi được nhận dạng rõ |
| Độ lặp | Sau diagnostic, protocol mới có giới hạn; review mỗi lượt | Phân biệt được wheel report với thân; không còn bất đồng chưa giải thích |
| Acquisition | Giữ collector hiện có; thêm quality sidecar và hiển thị thiếu dữ liệu | Chỉ sửa thêm vì một failure cụ thể có thể đổi quyết định |
| GUI không RC | Offline build/prep được giữ; hiển thị deployment gap | MCU/binary/rollback và authority live được xác minh riêng; không flash để làm dashboard |
| Governor/PPO/BC/predictor | Giữ frozen/history, chưa huấn luyện/triển khai mới | H2 useful authority và baseline thực nghiệm đủ để đặt câu hỏi tiếp |
| Tuning cổ điển / system ID | Cho phép chuẩn bị protocol; chưa đổi gain/current | Waveform/target/limits và body evidence chỉ ra parameter cần tuning |
| Navigation / route memory | Dự phòng có giá trị ứng dụng, chưa demo autonomous | Backend đủ tin cậy và estimator/TF/navigation commissioning riêng |
| Cơ khí/cảm biến mới | Đặt giả thuyết theo observation, không thay linh kiện theo phỏng đoán | Video/geometry/traction cho thấy giới hạn cơ khí hoặc sensing cụ thể |

Tối đa ba thí nghiệm đề xuất: (1) diagnostic thấp tốc có video, một lượt;
(2) nếu (1) đạt, đợt độ lặp mới tối đa ba lượt cùng điều kiện;
(3) nếu độ lặp đủ để định lượng, body reference/rolling geometry pilot có
hiệu chuẩn và uncertainty theo protocol riêng. Chưa cấp budget trong tài liệu này.
Mỗi bước giữ failures; tối đa một correction có căn cứ trước khi quyết định
stop/unknown/chuyển hướng, không sửa rồi chạy vô hạn.

## 5. GUI đã thay gì?

Tab **Tiến độ / kết quả / to-do** hoạt động offline, gồm:

1. D01–D23: dữ liệu cần/đã/chưa, claim và phần thiếu.
2. Thông số: observed rate/count, IMU axes/gyro means, approximate TF,
   declared wheel geometry, clear-zone wheel response và các unknown.
3. Phiên đã review: raw integrity, validity, physical evidence và giới hạn
   riêng từng lượt; failed/incomplete/unknown giữ nguyên.
4. To-do: bốn việc đã đủ/chuẩn bị và T01–T18 theo gate; không có checkbox
   tự promote evidence hoặc phát command khi chọn task.
5. Rubric Q0–Q4, correction báo cáo và kết quả chất lượng phiên GUI mới.

Có search, chi tiết nguồn, reload snapshot và export JSON. Catalog đóng gói
cùng package; không phụ thuộc Pi để xem kết quả. Nguồn có path/hash/date;
export không sửa raw. Thư mục nguồn có thể không tồn tại khi copy sang máy
khác; vẫn hiển thị provenance, không giả vờ kiểm lại file đó.

### Rubric chất lượng theo claim

| Mức | Ý nghĩa | Không suy ra |
|---|---|---|
| Q0 | Chưa có bằng chứng hoặc chỉ demo | Có dataset thật |
| Q1 | Raw giữ lại nhưng incomplete/lỗi/chưa kiểm đủ | Phiên đạt chỉ vì hash khớp |
| Q2 | Raw đủ kiểm closure/SQLite/metadata/hash/kênh | Coverage mọi window, thân tiến, slip hoặc dừng an toàn |
| Q3 | Review có nguồn đủ cho **claim hẹp** trong cửa sổ xác định | Đạt mọi claim, generalization hoặc deployment |
| Q4 | Độ lặp được đánh giá bằng protocol và đơn vị thử thích hợp | Certification hoặc tự cấp lần chạy tiếp |

Đây là **[Đ] quy ước quản lý bằng chứng**, không thang điểm chất lượng ứng
dụng hay safety standard. Mức historical là **[S] phân loại từ review đã lưu**;
không chạy lại toàn bộ raw. Không phiên nào hiện được gắn Q4.

Chấm riêng các chiều: file/closure; topic/clock/window/coverage;
command/STOP/confound; physical reference; repeats/generalization.
Phiên STOP vẫn có thể Q2 cho raw/chẩn đoán nhưng không pass wheel response.
Clear-zone Q3 chỉ cho reported-wheel primary, không là body GT.

Với phiên GUI mới, collector đóng xong thì tạo `gui_quality_report.json`,
đưa vào `gui_result.json` và hash sidecar riêng. Tự động **tối đa Q2**:
hash thật + manifest closure/SQLite/metadata + kênh required có samples.
Không tính coverage từ counts, không tính latency từ rate và không tự
gán Q3 vì workflow done. GUI demo luôn Q0 cho dữ liệu thật. Backend cũ
không có quality report giữ mức chưa kiểm đủ; không suy trạng thái đẹp.

## 6. Việc nên làm ngay

**Hoàn tất inventory/read-only readiness và chốt backend**, rồi chuẩn bị
một diagnostic có video bánh/thân/sàn, profile +0,05 m/s, ramp 0,10 m/s²,
source 2 s, bag 60 s. Artifact mong muốn: raw + closure/hash + trace + video
có mốc/nhãn đồng bộ + review khớp/không khớp; chưa phải slip measurement.

Chỉ đề nghị campaign độ lặp sau khi artifact này giải thích được bất đồng.
Nếu video/reference cho thấy input bị chặn hoặc mapping/scale/backend sai,
chuyển sang correction đúng tầng, giữ quan sát và ledger cũ nguyên vẹn.

## 7. Kiểm chứng bản sửa offline

46 tests protocol/workflow/ROS-adapter-stub/Qt-demo/capture/quality đạt.
Đã render và xem GUI, gồm bảng thông số, phiên mâu thuẫn và rubric ở cửa sổ
nhỏ có scroll. Chưa có ROS/hardware validation cho quality adapter mới;
tests này không thay dataset thật. `git diff --check` đạt.
