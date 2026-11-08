# Draft — phân biệt bánh quay và thân tiến, một lượt có video

Ngày 07/11/2026. **prepared_not_released; motion slots được cấp = 0.**
Đây là protocol để review, chưa là runtime/helper được triển khai hoặc nút
bấm đã sẵn sàng chạy. Không dùng lại slot pilot đã đóng.

## 1. Câu hỏi duy nhất và phạm vi

**Khi final ROS reference tiến và reported wheel feedback tăng, bánh chủ
động thật có quay và thân xe thật có dịch chuyển không?**

Một lượt chẩn đoán có thể phân biệt nhánh lỗi, không đủ đo độ lặp, xác nhận
slip, hiệu chuẩn gyro/radius hoặc so controller. Nếu có video cũ đúng session
V2 và nhìn rõ bánh/thân, phân tích video đó trước khi đề nghị motion mới.

## 2. Việc làm được ngay mà chưa chạy xe

1. Chuẩn bị camera cố định, giữ cùng ảnh một điểm trên thân và mốc cố định
   ngoài đường bánh; thêm dấu tương phản trên bánh/đai ốc quay để thấy
   rotation. Không gắn vật có thể mắc vào bánh hoặc cản LiDAR.
2. Phải thấy từng bánh muốn kết luận. Nếu một góc bị vỏ che, dùng góc bổ
   sung hoặc ghi bánh đó `not_visible`; không suy hai bánh từ một bánh.
3. Chụp ảnh setup: robot, vùng thử, mốc, caster và tải. Camera/người/dây đặt
   ngoài vùng dừng; không giảm StopZone để đặt camera gần hơn.
4. Ghi model camera nếu biết, kích thước ảnh, frame timestamps/FPS thực khi
   có file; thông số chưa biết để null. Không coi FPS danh nghĩa là đều.
5. Chuẩn bị ID liên kết video ↔ bag ↔ trial, tên file và hash sau khi đóng.
   Video quay liên tục từ baseline đến hết stop, không cắt ghép bản gốc.

Ảnh setup chỉ xác minh góc nhìn, không được đánh dấu thành dataset body motion.
Nếu chỉ có một camera không nhìn đủ thì claim bị giới hạn, không yêu cầu
mua thêm cảm biến để tiếp tục phân tích wheel feedback.

## 3. Hai mức reference, không đánh đồng

| Mức | Yêu cầu | Kết luận được | Chưa kết luận được |
|---|---|---|---|
| A — quan sát đồng phiên | Camera cố định; marker thân, mốc tĩnh và bánh đủ rõ; video liên tục, ID đúng | Bánh có quay / thân có tiến / không thấy / không phân biệt; khoảng thời gian trong video | Latency ROS→body, body speed/slip hay khoảng dừng chính xác |
| B — reference định lượng sau đó | Scale/geometry đúng mặt phẳng marker, distortion/perspective được kiểm; camera không dịch; frame PTS; sync độc lập với ROS và uncertainty | Displacement/timing trong giới hạn hiệu chuẩn | Slip nếu rolling geometry hoặc body speed chưa đủ chính xác |

Không áp homography mặt sàn trực tiếp lên marker cao trên thân rồi coi là
đúng scale; parallax/height phải được xử lý hoặc lượng hóa. Không tích phân
acceleration IMU làm GT độc lập cho lần này. Không đồng bộ clock bằng cách
ép onset wheel feedback trùng onset nhìn thấy rồi dùng nó đo latency.

Ở mức A chỉ cần liên kết chắc cùng session, có baseline/đoạn thử/stop trong
video và không có lượt chuyển động khác. Ở mức B cần cue độc lập được camera
nhìn và Pi log timestamp (ví dụ tín hiệu quang có timestamp); ghi độ trễ
phát/hiển thị, uncertainty và clock offset/drift. Chưa có cue đã kiểm thì
latency ROS→body giữ unknown. Âm thanh/lời đếm chưa đo sync chỉ là nhãn hỗ trợ.

## 4. Điều kiện trước khi đề nghị release một lượt

- Xác nhận live Pi/agent, boot/GID/type/endpoint và owner; candidate discovery
  cũ phải revalidate read-only. Chưa chạy stack motor để thay phép kiểm này.
- Giữ firmware/RC AUTO; đối chiếu stop/arm đã kiểm, không bypass mất RC.
- Có recorder ready, source/final trace mới, status/feedback/IMU/scan/TF
  hợp lệ cho contract. Giữ STOP guard ngay trước tiến và trong trial.
- Startup theo contract đã review: gate-off/zero → disable ACK mới → zero
  baseline → enable ACK mới; enable bit không thay effective RC/motor mode.
- Có video mức A đủ góc nhìn và tên session, vùng trống/tải/pose/caster note.
- Review profile và **cấp riêng tối đa một slot** trước chạy; không bù slot.

Đây là các phụ thuộc của một lượt motion tương lai. Lần chuẩn bị này không
SSH, không enable hoặc phát command. Chưa có readiness live thì không đưa
lệnh `run_trial.sh` như một bước sẵn sàng thực thi.

## 5. Profile đề xuất giữ nguyên và dữ liệu

Giữ source tiến **0,05 m/s trong 2 s**, ramp tham chiếu **0,10 m/s²**;
sau đó zero/disable, quan sát hậu dừng; bag **60 s** tự đóng. Thời gian
source tiến không phải hai giây chạy đều; diện tích reference không phải
chuyển vị thân. Không tăng tốc/gain/current hoặc thử vật cản.

| Required cho claim | Field/đơn vị/frame/clock | Giới hạn |
|---|---|---|
| Bag command chain hiện có | source/selected/smoothed/final Twist: m/s, rad/s; bag receipt clock | Final ROS chưa là executed motor target |
| Raw motor feedback | names, position rad, velocity rad/s; source header và bag receipt riêng | Mapping/sign/scale và binary chưa xác minh đầy đủ |
| Status/enable và trial events | raw bitmask, requested enable, wall/monotonic khi helper có | Firmware enable không tự là effective enable hoặc power readback |
| Scene/guard | scan raw, TF, monitor state event nếu có, guard abort/result | Thiếu sparse event không suy NONE; STOP/nguồn stale vẫn abort |
| Video và metadata | original file, session ID, PTS nếu có; wheel visibility/body landmark | Clock/scale unknown giữ null, không bịa body speed |
| Observation operator | wheel L/R thấy quay? thân tiến? tự dừng? lệch/giật? can thiệp? | Giữ riêng reported feedback và quan sát |

Raw IMU và các channel đã có vẫn giữ theo collection profile. Target sau
limit/current/voltage chỉ optional nếu thật có interface; không tạo từ cmd.

Primary wheel cũ, nếu vẫn dùng cùng contract: baseline source−2..0 s và
primary source+1,25..1,75 s, support theo protocol cũ. Không đổi grid/window
để làm lượt này pass. Outcome vật lý là phân loại độc lập, không phải phần
thưởng hoặc primary slip. Kết luận mỗi claim có QC riêng.

## 6. Quyết định sau đúng một lượt

| Lệnh / video / feedback | Quyết định |
|---|---|
| STOP hoặc final không tiến, dù source tiến | Giữ lượt abort/invalid cho wheel response; review scene/guard, không fit motor |
| Final tiến, feedback tăng; bánh và thân cùng có chuyển động | Feasibility đồng phiên đạt; lập protocol độ lặp riêng, chưa gọi slip/latency đạt |
| Final tiến, feedback tăng; bánh nhìn rõ đứng yên | Review danh tính/scale/telemetry/firmware/backend, không chỉnh gain/current để che mâu thuẫn |
| Bánh quay rõ, thân không tiến rõ | Kiểm cơ khí/truyền động/tiếp xúc; chưa gán slip định lượng từ video mức A |
| Video không thấy đủ hoặc chuyển vị dưới khả năng phân biệt | Unknown; lưu nguyên phiên, không tự retry hoặc thêm mẫu |

STOP/telemetry stale/discovery/ACK lỗi giữ raw và nguyên nhân, không chạy
bù. Tối đa một correction có căn cứ được đề xuất sau review; lần chạy lại,
nếu cần, phải là protocol/ngân sách riêng. Không tiếp tục vô hạn.

## 7. Bàn giao cần nhận

`bag + session.json + trial events/result + hashes + original video(s) +
setup photo + observations`. Annotation video có `wheel_left`, `wheel_right`,
`body_translation` mỗi trường thuộc `observed / not_observed / ambiguous /
not_visible`; `not_observed` chỉ nghĩa không thấy trong độ phân giải đó.
Các uncertainty/sync/scale thiếu giữ null. Tất cả tách khỏi dataset RL và
không được tự nạp vào replay buffer TD3.
