# Studio: theo dõi lượt TD3 đang chạy — 07/11/2026

## Lỗi và correction

Tab Train trước đây chỉ nhận stdout từ `QProcess` do chính cửa sổ đó tạo.
Continuation khởi chạy bên ngoài Studio không có kết nối này; mở lại GUI
cũng không tự nối với worker cũ. Điều đó không có nghĩa learner ngừng học.

`nino_pi.training_live` bổ sung reader local chỉ đọc:

- Tìm process cùng UID, đúng module training, request và output root.
- Đối chiếu request với `job.json`; ưu tiên directory trong log stdout.
  Không tự gán hai job có request giống nhau khi thiếu thông tin phân biệt.
- Theo dõi stdout hoặc UI log, coverage, kết quả, evaluation và checkpoint
  hoàn chỉnh mỗi 2 giây. File JSON đang ghi dở giữ snapshot trước đó.
- Phân biệt số bước global và bước thêm của continuation. Critic lấy từ
  log được gắn nhãn có thể trễ; actor không được suy ra khi chưa có counter.
- Hiển thị đúng request đang theo dõi trong form: seed, số bước thêm, resume,
  profile, map và budget. Không load model hoặc submit request khi theo dõi.

Studio tự tìm worker khi mở tab Train ở chế độ thường. Nút **Theo dõi lượt
train đang chạy** tìm lại worker và trở về view live sau khi xem lịch sử.
Demo không tự attach vào job thật; nút tìm vẫn là thao tác chỉ đọc.

## Vòng đời và giới hạn

- Khi theo dõi worker ngoài GUI, nút train/smoke bị khóa để tránh job trùng;
  nút dừng worker bị khóa vì GUI không sở hữu process đó.
- Đóng cửa sổ chỉ đóng observer; không gửi signal tới worker ngoài GUI.
  Worker do GUI tự tạo vẫn giữ quy trình cancel/checkpoint/cleanup hiện có.
- Không thấy worker nhưng job chưa đóng → báo `worker_missing`, giữ khóa,
  không tự retry. Lỗi/final result hiện theo artifact, không coi 100% bước
  train là đã hoàn tất evaluation hoặc QC.
- Reader chỉ hỗ trợ worker local và output của các trainer Studio đã biết.
  Không đọc trạng thái robot, SSH, chạy thêm sim hoặc thay ngân sách.
- Nút TensorBoard ưu tiên thư mục TensorBoard của job đang xem.
- Phiên train đang chạy được giữ nguyên; không sửa engine/config RL.

## Kiểm chứng

Artifact xác minh nằm tại workspace client:
`artifacts/training_live_gui_2026-11-07/`.

Đã attach chỉ đọc vào PID 489244, artifact
`20261107T080414816378Z_common_train`. Snapshot khi kiểm bản đã build:
global **24.319**, continuation **4.319/10.000** (bắt đầu 20.000),
critic log **14.318**; form hiển thị seed 11/budget thêm 10.000/resume đúng.
Đây là tiến độ live tại thời điểm chụp, chưa phải QC cuối.
Đóng cửa sổ test vẫn thấy đúng PID/starttime sống; không tạo QProcess train
hoặc kết nối Pi. Ảnh `studio_live.png` và `live_verification.json` lưu riêng.

Tests dùng fake `/proc`/log/JSON để kiểm discovery, request matching, resume
offset, partial line/rotation, JSON ghi dở, evaluation, checkpoint publication,
PID reuse và UI ownership. Bộ GUI regression kiểm cả luồng đóng owned worker
và các khóa chéo với recorder: **35 tests đạt**, `nino_pi` build đạt.
Không chạy optimizer/Gazebo mới để test GUI. Đã mở cửa sổ Studio bản cập nhật
ở tab Train, dùng module từ install; worker train PID 489244 vẫn giữ nguyên.
