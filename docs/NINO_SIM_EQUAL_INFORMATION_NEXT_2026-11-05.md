> **Cập nhật05/11:** đã triển khai [contract103D/1D](NINO_SIM_EQUAL_INFORMATION_CONTRACT_2026-11-05.md) và [qualification offline](NINO_SIM_EQUAL_INFORMATION_RESULT_2026-11-05.md). Không optimizer/Gazebo; bước sau là draft qualification wrapper trong Gazebo. Phần dưới giữ bối cảnh trước thực hiện.

# Bước Sim tiếp: contract cùng thông tin trước khi train tiếp

05/11/2026 · **Đề xuất, chưa mở optimizer hoặc lượt physics mới.**
Sau stop-time transfer6s, không tune amplitude/lead hoặc mở thêm các batch
gần giống chỉ để tăng số lần baseline thắng. Giữ các batch đã đóng.

## Quyết định hiện tại

Baseline common +0,005m/s sau steady, rút0,5s trước known source stop có
tín hiệu tracking mô tả ở stop8s và stop6s, cùng một clear fixture. Giữ nó
làm candidate đối chứng cổ điển; B0 vẫn giữ. Không gọi đây là cải thiện
first-contact, learned benefit hoặc baseline phần cứng đã hiệu chuẩn.

## Một việc cần làm kế tiếp — offline

Viết contract mới cho so sánh TD3/cổ điển **cùng thông tin về planned stop**,
trước khi quyết định một budget train mới. Đầu ra là spec/config/acceptance
tests có thể review; chưa phải một learner đã được train.

1. Nêu remaining gap cụ thể: tracking tốt hơn candidate cổ điển ở điều kiện
   nào, với chi phí thời gian/path/intervention nào? Primary vẫn cần chốt
   trước outcomes; minimum worthwhile effect hiện null, không tự thay bằng
   phần trăm vừa quan sát. Nếu không có gap đáng quan tâm, dừng learning cho
   envelope clear đã xem, dùng classical candidate cho nghiên cứu tiếp.
2. Chọn cách cấp preview như nhau: planned-source phase/thời gian còn lại
   do reference generator cung cấp cho cả hai controller, hoặc cùng rule
   withdrawal đã định trước ở cả hai. Nêu rõ rule bên ngoài actor là thành
   phần controller. Chưa gọi equal-information chỉ vì hai arm cùng map.
   Nếu thêm feature preview, cần ABI/history schema mới và checkpoint mới;
   không sửa feature cũ rồi load checkpoint V3 như tương thích.
3. Chốt action range/projection/requested/executed semantics và common/diff
   axes. Không biến frozen common-only negative control thành policy mới
   được train. Nếu giới hạn common-only là một giả thuyết, phải có task/
   replay identity tương ứng; giữ yaw follower, không học steering vô cớ.
4. Chốt reward, train/eval stop schedules và splits toàn run/condition,
   số training seed và budget hữu hạn theo compute thực đo. Stop6/8 đã xem
   là development, không được đổi tên thành unseen test bank. Không chọn
   checkpoint theo test set; giữ failures, native và diagnostic riêng.
5. Kiểm offline zero-init, causal history/source-clock/phase, action sau
   projection, terminal/truncation và save-load/ABI. Sau đó mới mở một pilot
   train có lý do và đối chứng phù hợp. Không tự dùng smoke64/512 như bằng
   chứng đủ hội tụ hoặc chọn ngân sách dài tùy ý.

## Điểm dừng

Không có objective/gap rõ hoặc thông tin preview không khả dụng cho ứng dụng
→giữ đối chứng B0/cổ điển trong Sim, chuyển công sức sang model discrepancy/
operating envelope. Nếu claim contact, cần H2 riêng trong contract khác;
không nối thêm obstacle vào batch này. Dữ liệu thật chưa là prerequisite
cho contract Sim; calibration và hardware deployment vẫn gate độc lập.
