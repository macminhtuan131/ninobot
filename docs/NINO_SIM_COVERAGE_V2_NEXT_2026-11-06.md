> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

# Sau failure coverage V1 — bước kế tiếp có giới hạn

> **Mới nhất: V2 đã chạy và đóng.** A seed11 hoàn tất; C seed11 có840replay
> rồi fail decision đầu episode6 vì drive chưa ACK wheel feedback; tổng1.864
> replay/1.736critic/868actor,0eval,15launches;49slot còn lại đóng.
> [Kết quả V2](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md).
> **Việc ngay:** nối candidate reset readiness vào backend có phiên bản, kiểm
> fixture ACK muộn và typed failure trước validator. Chỉ đề xuất qualification
> zero-only riêng sau review; không mở training mới hoặc retry V2. Nếu đạt,
> ưu tiên eval-only checkpoint A đã có thay vì train lại toàn ma trận.
> Các mục bên dưới giữ lịch sử chuẩn bị V2.

06/11/2026 · **Cập nhật: runner V2 đã triển khai, preflight qua GUI 80 tests đạt;
54 GUI tests/build hai package đạt. Chưa release/budget physics V2.**
Xem [kết quả](NINO_SIM_COVERAGE_V2_IMPLEMENTATION_2026-11-06.md) và
[protocol](NINO_SIM_COVERAGE_V2_PROTOCOL_2026-11-06.md). Các mục dưới là outline
đầu vào trước triển khai; bước 2–3 đã qua kiểm phần mềm, bước 4 chưa mở physics.

1. Giữ nguyên [V1 đã đóng](NINO_SIM_COVERAGE_RESULT_2026-11-06.md), partial,
   raw và manifest. Không retry/resume, không tái sử dụng63slot chưa chạy.
2. Dùng correction `coverage_qualification_adapter.py` làm đầu vào thiết kế
   runner V2: metadata condition phải hiện diện trước validator; chỉ từ
   source plan, không GT. Metadata conflict fail trước control request.
3. Nối factory đã sửa vào **đường train thật của runner V2**, có identity,
   source pins và test `collector→training wrapper→row→real validator→replay`.
   Kiểm reset stop6/8 và decision đầu mỗi episode; không thay bằng test mà
   validator bị mock. Fixture synthetic và recorded-row regression tách rõ.
4. Chốt root/protocol/fingerprint/release/budget mới trước bất kỳ Gazebo nào.
   Nếu tiếp cùng câu hỏi, ma trận đề xuất vẫn2arm×3seed×1.024 và16eval×140;
   đây là **đề xuất mới**, không là ngân sách còn dư V1. Không thêm smoke
   ngoài budget; episode đầu phải là integration check nằm trong budget.
5. Giữ primary/native và sensitivity grids, constraints và rule nghiên cứu
   như V1 nếu câu hỏi không đổi; giải thích mọi thay đổi trước kết quả.
   Kết luận task/measurement/learning benefit và hardware luôn tách riêng.

**Một việc kế tiếp:** review pins/ma trận và chốt release V2 riêng sau preflight
đã đạt. Không train dài hơn, chỉnh
reward/gain/QoS hoặc thu thêm real data để xử lý lỗi field trace này.
