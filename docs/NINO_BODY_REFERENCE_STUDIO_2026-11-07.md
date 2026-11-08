# Studio — liên kết video với session bánh/thân

Ngày 07/11/2026. Phần mới chỉ xử lý file local và nhãn quan sát;
không chạy robot, recorder, SSH, RC, enable hoặc training.

## Đánh giá hiện tại

- Kết luận Sim giữ nguyên: cùng learner seed11 đã train 30.000 global steps;
  classical vẫn được ưu tiên cho clear-box/lịch dừng 6/8 s/Ki0,10.
- Review bốn bag thật giữ nguyên: 95.459 messages, 100 file raw khớp hash;
  mâu thuẫn V2 giữa reported wheel và quan sát thân chưa giải quyết được.
- Lần kiểm kết nối này, SSH BatchMode tới `d@192.168.0.109` timeout. Đây là
  bằng chứng không truy cập được từ laptop lúc kiểm, không xác định nguyên
  nhân nguồn/mạng/driver hoặc trạng thái motor. Chưa có readiness live mới.
- Chưa nhận video thật trong lần phát triển này; không có body speed/slip
  được bổ sung chỉ vì đã xây màn hình nhập liệu.

## Các bước trong GUI

Mở lại Nino Studio để nạp bản mới. Trong **Thu dữ liệu thật → Studio ·
recorder chỉ đọc**, bấm **Reference bánh/thân · gắn video với session đã thu**.

1. **Chọn session local** đã tải về laptop. Hỗ trợ session cũ có
   `manifest.json + bag/` và Studio có `raw/manifest.json + raw/bag/`.
   Màn hình pin hash manifest để liên kết danh tính, không tự chạy QC bag.
2. **Thêm video gốc**. Nếu còn video đúng V2, dùng file đó trước khi cần
   motion mới. Có thể mở video đã chọn bằng trình xem mặc định. Không copy,
   cắt ghép, upload hoặc thay đổi video.
3. **Ghi nhãn từng bánh và thân**: chưa đánh giá / thấy chuyển động / không
   quan sát thấy / không phân biệt / không nhìn thấy bộ phận. Ghi mốc, góc
   nhìn, sàn/tải/caster và điểm chưa chắc. Xác nhận đúng session là lời khai
   operator, chưa là kiểm độc lập. Không suy không quan sát thấy = zero vật lý.
4. **Tính hash và lưu hồ sơ riêng**. Mặc định vào
   `~/nino_research/body_reference_reviews/`, mỗi lần một JSON mới. Không cho
   lưu trong session/raw, kể cả qua symlink. Chọn nơi khác ngoài session nếu
   cần. Video không bị copy nên phần lưu chỉ là metadata nhỏ.

Việc đọc/hash chạy ở background; có thể hủy và đóng, GUI chờ worker kết
thúc. Manifest thay đổi, file rỗng/đang đổi hoặc nhãn sai làm thao tác lỗi,
không tự ghi hồ sơ thành công. File video không bị xóa khi bỏ khỏi danh sách.

## Hồ sơ này xác nhận được gì?

| Có trong JSON | Không được tự suy |
|---|---|
| Session path, manifest hash và status ghi trong manifest | Raw integrity/closure hiện tại đã được kiểm lại |
| Video path, kích thước byte, SHA256 | Video xác thực, đủ góc nhìn hoặc đúng session đã kiểm độc lập |
| Metadata stream khi máy có ffprobe | FPS đều, PTS từng frame hoặc clock đã đồng bộ |
| Nhãn operator và ghi chú | Body-motion success, Q3/Q4 hoặc độ lặp đã đạt |
| Reference candidate, trường chưa đo là null | Body speed, ROS→body latency, slip hoặc target actuator |

Nếu máy chưa có `ffprobe`, vẫn có thể đăng ký file/hash với nhãn
`checksum_only_media_not_validated`; không giả vờ đã decode video. Màn hình
không tự cài phần mềm hoặc tự tính calibration. Mọi hồ sơ mới giữ
`motion_released=false`, physical verdict unknown, không đủ cho slip/TD3
replay; phần quan sát operator được giữ riêng để review sau.

## Điều cần người vận hành làm tiếp

- Nếu có video cũ: chọn đúng session, gắn video, lưu hồ sơ và gửi đường dẫn
  JSON/video để review. Có thể làm phần này khi Pi không kết nối.
- Nếu chưa có video: chuẩn bị góc quay cố định thấy bánh và thân/mốc. Chưa
  enable/chạy xe để chỉ kiểm góc nhìn. Gửi ảnh setup để chọn claim nhìn được.
- Xác nhận Pi đang bật/IP hiện tại. Sau đó mới kiểm live boot/GID/owner/
  scene/ACK và xem xét một diagnostic theo protocol/ngân sách riêng.

[Draft diagnostic và mức reference A/B](NINO_BODY_REFERENCE_DIAGNOSTIC_DRAFT_2026-11-07.md),
[báo cáo wheel/body](NINO_WHEEL_BODY_GAP_REVIEW_2026-11-07.md).
Không tự mở lại ba repeats, tăng tốc/gain/current hoặc thay kết luận Sim.
