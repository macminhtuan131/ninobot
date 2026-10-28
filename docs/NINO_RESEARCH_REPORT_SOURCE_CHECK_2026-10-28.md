# Kiểm nguồn và phạm vi kế thừa báo cáo Deep Research — 28/10/2026

Báo cáo người dùng gửi được lưu nguyên văn trong
[external_reviews](external_reviews/NINO_DEEP_RESEARCH_RECEIVED_2026-10-28.md).
Các token `cite turn...`/`filecite` ở bản pasted không có bibliography có thể
truy ngược trong phiên này. Không tự chuyển chúng thành trích dẫn đã xác minh.

Đã kiểm có chọn lọc các nguồn primary sau để xác định các tiền đề cho bước
kế tiếp. Đây không phải systematic literature review đủ 12–20 bài hoặc
bằng chứng tính mới.

| Nguồn và nội dung đã kiểm | Claim hỗ trợ | Giới hạn đối với Nino |
|---|---|---|
| [Nav2 Velocity Smoother README, source Jazzy](https://raw.githubusercontent.com/ros-navigation/navigation2/jazzy/nav2_velocity_smoother/README.md) | Shaping vận tốc/gia tốc/deadband; OPEN_LOOP/CLOSED_LOOP; closed-loop cần odom nhanh/ít trễ | Không xác nhận stack Nino đã chạy trên Pi; không bắt full odom cho wheel-ID open-loop |
| [Nav2 Collision Monitor README, source Jazzy](https://raw.githubusercontent.com/ros-navigation/navigation2/jazzy/nav2_collision_monitor/README.md) | Sensor-based cmd_vel filtering/stop/slowdown; không có hard realtime safety certification | Không bao phủ floor hazards không nằm trong sensor view; chưa đo stop distance Nino |
| [Tutorial source Jazzy](https://raw.githubusercontent.com/ros-navigation/docs.nav2.org/jazzy/docs/tutorials/general_tutorials/using_collision_monitor/using_collision_monitor.md), [tutorial rolling hiện tại](https://docs.nav2.org/rolling/tutorials/general_tutorials/using_collision_monitor/using_collision_monitor/) | Topic/TF/source contract; rolling có hướng dẫn tính reaction/driver latency đo thật | Phải ghi version. Không chép defaults/topic type rolling xuống Jazzy; câu latency không được gán nhầm là nội dung tutorial Jazzy |
| [ROS 2 Clock and Time](https://design.ros2.org/articles/clock_and_time.html) | ROS/System/Steady time có semantics khác; SteadyTime dùng cho hardware timeout | Không xác nhận clock/sync thực của firmware Nino |
| [Twist.msg Jazzy](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/geometry_msgs/msg/Twist.msg), [RMW types Jazzy](https://raw.githubusercontent.com/ros2/rmw/jazzy/rmw/include/rmw/types.h) | Twist không header; middleware publish/receive timestamps không là actuator execution stamp | Bag receipt không tự là execution hoặc decomposition latency |
| Lee, Kim, Seo (2024), Scientific Reports 14:13745, DOI [10.1038/s41598-024-63825-y](https://doi.org/10.1038/s41598-024-63825-y); [full text PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11637058/) | Novel caster có thực nghiệm; báo cáo caster riêng 65 mm và toàn robot 30 mm; grip/COM ảnh hưởng | Khác caster/robot Nino, fixed 0,1 m/s; không suy height ratio hay slow-always-better. Không lấy các mô tả kích thước chưa nhất quán làm threshold thiết kế Nino |
| [BADGR, paper tác giả](https://arxiv.org/abs/2002.05700), [project](https://sites.google.com/view/badgr), [repo](https://github.com/gkahn13/badgr) | Action-conditioned prediction từ ảnh cho physical outcomes như bumpiness/collision đã tồn tại | Không cùng indoor caster/contact regime; làm yếu claim predictor tổng quát mới, chưa bác bỏ một đóng góp cơ chế hẹp |
| [ViNG, paper tác giả](https://arxiv.org/abs/2012.09812), [project ICRA 2021](https://sites.google.com/view/ving-robot/) | Visual experience/topological graph và navigation từ trải nghiệm đã có | Không phải chứng minh route-quality speed memory Nino mới; khác sensing/objective và cần baseline hand zones |

Các hàng ambiguous trong báo cáo nhận như “IEEE 2024 caster ID”,
“Reference Governor 2014/2023”, “Online SSL traversability 2026”,
“Slip-resistant planning/control 2026”, “Capability-aware traversability
2026” chưa có title/authors/DOI đủ để khớp chính xác. Trạng thái là **chưa
xác minh từ citation được cung cấp**, không khẳng định bài không tồn tại
hoặc nội dung sai. Không chọn một bài gần giống để gán lại ID.

Không kế thừa mức novelty vừa/cao cho hướng motion-contract/envelope từ
report này. Tiến bộ ứng dụng và đóng góp nghiên cứu phải đánh giá riêng;
muốn phát biểu novelty cần tìm đúng các công trình gần nhất có thể bác bỏ
claim và so cơ chế/measurement/actuator/obstacle cụ thể.

Các giá tiền và Gantt placeholder trong bản nhận không có BOM/vendor/
nguồn lực đi kèm, nên không dùng làm budget/deadline. Không cần mua sensor
hoặc thay kiến trúc vì các placeholder đó.
