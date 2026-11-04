# Bàn giao định hướng và GUI v4 — 03/11/2026

> **Cập nhật 04/11 — [History / Governor / TD3 / GUI v5](NINO_RESIDUAL_IMPLEMENTATION_2026-11-04.md):** đã có environment chạy, optimizer smoke TD3/PPO, portable actor và kiểm ROS/Gazebo fixture. Xem tab **Xây project** để kiểm artifact hiện hành. Train nghiên cứu và learned residual trên robot vẫn chưa mở; dữ liệu thật chưa được thu thêm trong cập nhật này. Các mục có ngày trước bên dưới giữ bối cảnh lịch sử.

## Quyết định và phần đã sửa

- [Đ] Hướng hiện hành: [motion contract → SysID → B0/B1 → residual velocity](NINO_RESEARCH_DIRECTION_2026-11-03.md).
  TD3/MLP history là ứng viên; PPO cùng ABI là comparator. Training chưa mở.
- [N-code] Thêm pure feature/history/reference core, ABI20×5, projection
  common/diff theo m/s. Feature proxy không biến thành slip; actuator target
  thiếu giữ null. Default hardware và simulation residual authority0.
- [N-code] Thêm YAML TD3/PPO, contract/reward/model factory và backend API.
  `train.py` lịch sử chặn YAML mới; parameters PPO tách khỏi TD3. Chưa có
  Gazebo/ROS adapter mới được xác nhận và chưa có training runner được release.
- [N-code] [GUI v4](../src/nino_pi/GUIDED_COLLECTION.md) dùng fixed jobs qua
  QProcess/SSH: chuẩn bị → sensor connection/inventory → ZERO → recorder →
  **explicit motion click** → QC → operator observation → fetch. Không còn
  hộp copy commands trong luồng chính. Hiển thị trạng thái/mẫu/time còn lại,
  log và hướng dẫn nút tiếp theo; nút hủy luôn ở header.
- [N-code] Có heartbeat supervisor, cleanup child do GUI sở hữu, closure
  riêng với trial completion; mất output không chặn gửi signal cleanup.
  Giữ current RC AUTO firmware và Collision Monitor. Advanced software
  authority là đường khác, chưa có xác nhận firmware live tương thích.
- [N-code] Runtime có source tracked, builder reproducible và payload hashes;
  deploy copy-only không ghi đè runtime khác hash hoặc reset ledger. Chỉ nút
  record/trial được người vận hành bấm mới vào diagnostic một slot.
- [N-code] Cập nhật inventory/diagnostic/session profiles, D01–D30,
  T01–T24, parameters/sources/quality trong GUI. Phân biệt tầng data đã có
  với SysID/body/reference/residual còn thiếu. Profile gốc giữ0,05m/s,
  ramp0,10m/s², source2s, bag60s.
- [N-code] README và tài liệu thực hành dẫn tới hướng/GUI mới; thuật toán,
  protocol, dữ liệu và checkpoint cũ được giữ với nhãn lịch sử phù hợp.

## Kiểm chứng đã thực hiện

**71 tests offline đạt:** 62 tests GUI/protocol/workflow/quality/runtime và
9 tests residual core/experiment contract. Có fixture local subprocess cho
heartbeat timeout và đóng đường output, QProcess event parsing, và Qt demo
không tạo dữ liệu thật. Lỗi đặt signal trùng virtual `QObject.event` đã sửa;
Qt regression test thu exception hook để tránh test pass khi slot báo lỗi.

Build Python package xác nhận GUI modules, plan/evidence JSON và runtime ZIP
được đóng gói. Runtime được kiểm syntax/hash; build reproducible được đối
chiếu. `git diff --check` đạt. Đã xem screenshot Qt ở1180×980 và960×760,
gồm trạng thái recorder ready với nút motion riêng. Cửa sổ nhỏ có scroll;
nút hủy ở header luôn truy cập được.

Giới hạn: interpreter kiểm thử chưa có Gymnasium/SB3/PyTorch, nên chưa kiểm
end-to-end Gym adapter/model construction hoặc optimizer. Test contract/gate
và pure core không thay việc đó. Không SSH, flash, phát enable/vận tốc, thu
bag thật, chạy Gazebo hoặc training trong đợt sửa này. Snapshot real giữ đến
02/11; software tests không tăng số lượt robot đã thành công.

## Việc người vận hành làm tiếp

Mở ứng dụng **Nino · Thu dữ liệu**, hoặc:

```bash
bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh
```

Chọn diagnostic, điền IP/key hiện có, bấm theo hướng dẫn. Sau reboot có thể
dùng2a để kết nối các wrapper sensor đã review;2b mới đọc inventory thật.
File/cổng/hash/GID đổi thì dừng ở lỗi cụ thể để đối chiếu, không tự đoán.
Chuẩn bị video thấy bánh/thân/mốc sàn và metadata. Nút4 chỉ thu; nút5 mới
yêu cầu tiến. Chờ recorder đóng đủ rồi QC/quan sát/fetch; video copy riêng.
Outcome unknown hoặc bất đồng vẫn giữ nguyên, chưa mở repeatability/RL.

Nguồn hai attachment được lưu path/hash trong `project_evidence.json`.
Chi tiết bằng chứng Nino và correction giả định báo cáo nằm trong tài liệu
định hướng; không coi mọi citation của attachment là đã được kiểm full text.
