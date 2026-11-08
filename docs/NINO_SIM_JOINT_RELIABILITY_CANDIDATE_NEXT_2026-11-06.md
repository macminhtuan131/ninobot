> Cập nhật06/11: candidate riêng đã triển khai; mộtfixture1handshake+1000labeledmessages cảBE/RELIABLEđủ, sau đó2B0qualificationstop6/8 đạt280ticks. Chưa optimizer/train/rootcauseproof. Xem [kết quả](NINO_SIM_JOINT_RELIABILITY_RESULT_2026-11-06.md) và [learnerdraft mới](NINO_SIM_RELIABLE_TD3_NEXT_2026-11-06.md). Nội dung dưới là kếhoạch tại thờiđiểm trước triểnkhai.

# Candidate kế tiếp: joint reader RELIABLE, giới hạn một correction

06/11/2026 · **Chỉ thiết kế; chưa thay backend frozen, chưa chạy fixture này
hoặc cấp budget Gazebo/train mới.** Diagnostic zero-only2/2 đã đóng.

## Bằng chứng và giới hạn

Đã đo đúng một publisher `/joint_state_broadcaster` kiểu JointState, offered
reliability1(RELIABLE); primary và observer phụ reliability2(BEST_EFFORT),
depth100. Hai launch zero có612checks đủsupport,15.220matching source stamps,
canonical payload parity đạt. Không tái hiện50ms; không có optimizer load.
Final software fixture trước diagnostic phát20message, observer nhận19,
thiếu mẫu đầu stamp10s; không gọi packet loss trong control window hoặc chứng
minh best-effort là nguyên nhân failure của TD3 từ startup fixture khác.

## Một candidate nhỏ có căn cứ

Tạo backend **mới**, chỉ yêu cầu RELIABLE cho subscription joint của observer;
giữdepth100, topic/type, clock/frame, primary processing, PI/physics/guidance/
reward/limits và gate40ms. Không sửa parent scientific source hoặc ROS
joint_state_broadcaster. Publisher hiện offer compatible, nhưng reliability
không bảo đảm source vẫn publish, không queue overwrite, không backlog hoặc
mọi deadline đều đạt. Đây là hardening candidate, không root-cause correction
đã chứng minh. Không chồng thêm correction tăngdepth/đổichunk/đổireset.

## Gate phần mềm trước physics

Một fixture ROS-only có nguồn RELIABLE ghi source index/stamp/payload và
lần gọi publish. Hai readers độc lập BEST_EFFORT/RELIABLE, cùngdepth100;
ít nhất đủ discovery/endpoint match trước khi bắt đầu labeled window.

- Budget đề xuất: một source stream hữu hạn1.000JointState/500Hz; cùng
  message stream cho hai reader. Ghi source attempted publish khác DDS
  delivered/reader received; không gọi `publish()` return là upstream ACK.
- Có một receiver pause100ms có lịch định trước ở giữa stream, cả hai reader
  nhận cùng yêu cầu và ACK thời điểm thực. Không xóa mẫu giai đoạn pause.
- Sau pause, query endpoint tương ứng thời điểm source dừng với deadline5s,
  hỗ trợcausal≤40ms, không dùng future/interpolation, không phát thêm để váđuôi.
- Lưu counter/schema, source/receipt clock riêng, common-window coverage,
  semantic payload hash và deadline/closure. Không dùng hash CDR serialize
  lại làm equality gate; padding khác không là payload mismatch.
- Pass chỉ là candidate tương thích và hồi phục đúng fixture. Nếu cảhai
  cũngpass thì tác dụng reliability chưa được chứng minh. Nếu reliablethua,
  cóbackpressure/deadline hoặc metadata mismatch →no-go candidate.

Chỉ một fixture/candidate; failure giữ lại, không tăng message/budget hoặc
đổi thêm queue để có pass. Nếu thiếu thông tin: unknown và giữclassical/
partiallearner hiện có, không lặp train để tìnhcờ qua.

## Nếu candidate đủ phần mềm và được chọn tiếp

Chốt **protocol mới trước chạy** cho qualification khônglearner: B0 clear
stop6/8s, tối đa2launches×140ticks, cùngendpoint+independent observer và
engineering/task/stop bounds. Đây là đề xuất, chưa release. Nó cũng chưa
chứng minh acquisition dưới optimizer load hoặc lợi ích TD3.

Chỉ sau qualification và nhận định rõ giới hạn load mới cân nhắc learner
budget riêng; không mở lại700/3072batch hoặc resume partial âmthầm. Nếu
upstream khôngpublish hoặc failure cònkhôngtáchđược: dừngcandidate và quyết
định giữbaseline/đổi acquisition architecture bằng một thiết kế riêng;
không kéo chuỗi mini train→logger→retry vôhạn.
