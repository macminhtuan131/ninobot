# Nino — đánh giá tiến độ và kế hoạch sau Deep Research, 28/10/2026

## 1. Quyết định hiện tại

**Nino đã hoàn thành bước tích hợp/kiểm dữ liệu cảm biến ban đầu và đang
chuẩn bị xác minh chuyển động có điều khiển. Chưa có dataset đã kiểm chứng
cho command → wheel → body trên robot thật; governor chưa được promote.**

Ưu tiên hiện tại là **motion contract → wheel response trên sàn sạch →
body validation → một operating-envelope pilot**. Route quality memory là
ứng viên sau các gate đó, chưa phải hạng mục triển khai đồng thời. Phương
án dự phòng là điều chỉnh cơ khí/caster/clearance hoặc phép đo phù hợp khi
bằng chứng chỉ ra giới hạn authority hoặc geometry.

Đây là quyết định kỹ thuật từ bằng chứng hiện có, chưa chứng minh tính mới
khoa học hoặc tính phù hợp triển khai nhà máy. Không dùng một phần trăm
hoàn thành chung vì acquisition, controller và navigation có mức đạt khác nhau.

Bằng chứng phần cứng gần nhất vẫn thuộc 27/10; review này đọc offline và
kiểm nguồn ngoài, không kiểm runtime Pi mới. Không suy process còn chạy.

## 2. Nguồn và cách sử dụng báo cáo nhận được

- [Báo cáo người dùng gửi, giữ nguyên](external_reviews/NINO_DEEP_RESEARCH_RECEIVED_2026-10-28.md).
- [Manifest nguồn và SHA256](external_reviews/NINO_DEEP_RESEARCH_RECEIVED_2026-10-28.provenance.json).
- [Kiểm nguồn/nhận định bên ngoài](NINO_RESEARCH_REPORT_SOURCE_CHECK_2026-10-28.md).
- [Sensor integration thật](REAL_SENSOR_INTEGRATION_2026-10-27.md),
  [TF/IMU và cập nhật gyro](IMU_TF_APPLIED_AND_MOUNTING_GUIDE_2026-10-27.md).
- [Survey controller](GOVERNOR_DESCRIPTIVE_SURVEY_2026-10-18.md),
  [audit timing](GOVERNOR_H2_TIMING_ENVELOPE_2026-10-23.md),
  [v6/v7](GOVERNOR_ISOLATED_CADENCE_V6_RESULT_2026-10-23.md).

Nhãn: **[N]** dữ liệu/source/config Nino; **[T]** nguồn ngoài có URL;
**[S]** suy luận có điều kiện; **[Đ]** đề xuất chưa kiểm chứng.

### Những phần giữ và sửa từ báo cáo

| Nội dung báo cáo | Quyết định sau đối chiếu |
|---|---|
| Sensor/sign audit đã đủ cho bước kế tiếp | Giữ; chỉ mở lại khi đổi phần cứng/driver/frame hoặc có lỗi cụ thể ảnh hưởng phép đo |
| Ưu tiên command→wheel ID | Giữ; còn phải chốt owner, RC, stop và profile trước thử chuyển động |
| Motion contract + envelope + quality memory là một hướng ưu tiên liên tục | Thu hẹp milestone trước mắt tới motion/envelope; memory là nhánh có điều kiện |
| V7 chỉ kiểm độ tin cậy logger | Sửa: nếu coverage đạt, v7 còn có thể trả lời timing/actual-response contrast trong sim. Hoãn vì ưu tiên hardware, không phủ nhận giá trị khoa học của contrast |
| Wheel90 từ đầu command là deadtime/bandwidth motor | Sửa: gồm transport, shaping/ramp và actuator; cần định nghĩa timing riêng, không fit một model rồi gọi toàn bộ là đặc tính motor |
| 5 lặp/profile, hoặc 6–10 crossing | Chưa nhận làm protocol. Phải khóa số/order trước dữ liệu; không chọn n sau kết quả |
| Fixed low/nominal/slowdown đồng thời kiểm H2 | Tách câu hỏi: fixed-speed trade-off trước; H2 cần comparator và trigger sau contact riêng, có requested/executed timing |
| Unknown obstacle → Collision Monitor | Giới hạn: LiDAR ngang không preview đáng tin mọi cáp thấp/hõm/rãnh; envelope phải xét khả năng quan sát |
| Dây mềm có thể crawl | Chưa chấp nhận: chưa đánh giá quấn/kéo thì ưu tiên tránh/cố định/xử lý mặt sàn |
| Literature/novelty với citation turn IDs | Chưa truy ngược đủ. Giữ nguyên nguồn nhận, xác minh URL riêng; novelty hiện chưa đủ cơ sở |
| USD ranges và Gantt 7/10/20 ngày | Không đưa vào kế hoạch thực thi: thiếu BOM/nguồn lực/báo giá. Dùng dependency và effort tương đối |

## 3. Tiến độ theo bằng chứng

| Mảng | Đã đạt [N] | Chưa đạt / giới hạn | Trạng thái công việc |
|---|---|---|---|
| Thu cảm biến thật | Bag IMU/motor/status/LiDAR/TF; 20/20 hashes; raw/bridge đối chiếu | Counts không bảo đảm coverage mọi transient | Đóng inventory chung |
| IMU | Mapping X/Y thô +90° tái hiện, TF áp; gyro trái dương/phải âm | Fine alignment, scale, rigidity/uncertainty chưa hiệu chuẩn đầy đủ | Đủ cho bước kế tiếp, không lặp các thao tác cũ |
| Geometry/TF | XYZ gần đúng từ người vận hành đã áp và kiểm TF | Radius lăn hiệu dụng, track, caster/load chưa đo đầy đủ | Đo khi claim phụ thuộc; không lấy cao trục làm radius odom |
| Firmware/RC | Source đã review; receiver/tay có theo operator; nút đỏ được báo là emergency stop | Binary/source match, mapping switch, effective enable và cơ chế nút đỏ chưa xác minh hết | Còn gate command contract |
| Teleop | Có source helper/gate/smoother/monitor, command path đề xuất | Chưa có proof chuỗi đầy đủ hoạt động trên Pi ở phiên mới; IP gần nhất timeout | Chuẩn bị, chưa ready để suy motion |
| Wheel response thật | Chưa có dataset motor-driven được admit | Mapping động, timing, ramp/stop, repeatability | Ưu tiên kế tiếp |
| Body/slip thật | Chưa có reference độc lập đã đánh giá | Encoder odom không là body reference | Sau wheel ID; có thể khảo sát reference offline trước |
| Governor sim | Survey 16 attempts hợp lệ; lợi ích slip trung bình −1,01%, CI mô tả rộng, đổi dấu block | H2/H3 chưa xác lập; publication sớm chưa là causal body response | Frozen baseline |
| Cadence/acquisition sim | V7 đã chuẩn bị và software-tested theo archive | Chưa release/chạy Gazebo; v6 fail measurement | Giữ, chưa mở batch mới |
| Navigation/memory | Hạ tầng/helper và maps | Scan/TF contract chưa đủ; chưa có route-memory outcome thật | Chưa triển khai memory |

Không đọc “đóng audit” thành mọi phép hiệu chuẩn đã hoàn thành: chỉ có nghĩa
bằng chứng hiện có đủ để chuyển sang câu hỏi cụ thể hơn. Không cộng tiến bộ
logger/TF vào thành tích governor.

## 4. Các rào cần xử lý đúng phạm vi

**[N] Profile thu đầy đủ đang bắt `/scan`, `/odom`, `/tf`; wheel-response
claim không cần các kênh đó.** Đã thêm profile riêng với required
`/cmd_vel`, `/motor_fb`, `/motor_status`; IMU, các tầng command, raw scan/
TF/derived odom được giữ optional để ghi khi có. Nếu claim source→final
hoặc toàn chuỗi thì phải bổ sung required các tầng source thực dùng trước
thu. Đây là contract khác, không hạ required của full profile.

**[N] Mở launch teleop không phải phép kiểm chỉ đọc.** Gate disabled vẫn
phát zero; downstream có thể làm mới watchdog/chọn velocity mode ở STM32.
Chỉ dùng đọc file/graph hoặc `--check` để chuẩn bị. Chuỗi navigation hiện
thiếu scan/odom TF cần thiết phải được xử lý bằng contract rõ. Không âm thầm
bypass monitor. Một commissioning path riêng có thể được thiết kế, nhưng
phải công khai owner, giới hạn, stop và phạm vi; không mặc định đã có.

**[N] Keyboard source hard-code 0,20/0,10 m/s và 0,60 rad/s, expiry 0,6 s.**
YAML gate clamp output, không đổi requested value của keyboard. Profile
thử phải ghi cả nguồn yêu cầu và giới hạn/output từng tầng. Chưa lấy các
mức mặc định làm tốc độ thử được chấp nhận.

**[N] Bit enable firmware không là effective-enable sau RC arbitration.**
Source có thể giữ `g_system_enabled` trong khi RC/F làm nhánh thực gửi stop.
Status mode không là readback actuator; effort không là current/torque đo
độc lập. Không tự sửa firmware để tạo target telemetry ở bước này.

## 5. Outline công việc theo gate

| Bước | Việc và đầu ra cụ thể | Người/phần việc | Qua bước khi nào? | Dừng/unknown và chuyển hướng |
|---|---|---|---|---|
| P0 — chuẩn bị offline | Profile riêng, session/contract form, protocol và báo cáo trạng thái | Assistant; đã chuẩn bị trong lượt này | Config/`--check` hợp lệ; unknown vẫn null | Không coi syntax pass là motion readiness |
| P1 — chốt đường điều khiển | Inventory runtime khi nối lại; owner source/final/enable, mapping RC, stop/limits; session được điền bằng evidence | Assistant đọc/cấu hình; operator xác nhận phần vật lý | Một path explicit, đủ điều kiện cho lượt motor đầu | Chưa rõ owner/mode/stop → không mở lượt chạy; không đòi flash chỉ vì binary hash unknown |
| P2 — wheel pilot E1 | Raw bag + source/final commands nếu claim, raw wheel/status; bảng timing/quality từng run | Operator thao tác; assistant recorder/evaluation | Mapping và response tổng có giải thích, time support/uncertainty đủ cho claim | Sai sign/status/reset → stop; một correction có căn cứ, không tự chạy bù |
| P3 — body validation E2 | Reference độc lập, uncertainty/sync report; endpoint distance/yaw trước dynamic speed nếu phù hợp | Assistant phân tích; operator bố trí mốc/reference | Reference phù hợp effect cần phân biệt | Không đủ cho transient thì giữ endpoint claim; không nâng thành slip/latency body |
| P4 — envelope pilot E3 | Một gờ cứng cố định, một tải/hướng; fixed-profile trade-off, mọi failure | Operator + assistant; chuẩn bị sau P3 | Outcome/metric có cơ chế, đủ repeatability cho quyết định tiếp | Geometry/support chi phối → cơ khí/avoidance; effect nhỏ/sampling-sensitive → unknown |
| P5 — mở nhánh có điều kiện | Review riêng H2 hoặc memory; protocol mới với baseline mạnh | Chỉ khi P4 hoặc dữ liệu tuyến tạo premise | H2: response và outcome contrast; memory: repeated-route localization/quality có ích hơn hand zones | Không đạt thì giữ classical/envelope; chưa có lý do train predictor/RL |

P0 đạt không tự cấp release cho P1/P2. Các bước phần cứng cần thực hiện với
người vận hành và protocol chuyển động cụ thể; review này chưa chạy chúng.
Nguồn điện chỉ được mở lại nếu failure mới khiến phép đo sắp tới không thể
diễn giải; không khởi động lại audit nguồn chung đã được yêu cầu tạm gác.

## 6. Ba thí nghiệm được đề xuất, chưa phải ngân sách đã cấp

### E1 — sàn sạch, command→wheel tổng hợp

**[Đ] Câu hỏi:** với command path cố định, response của từng bánh có đo
được và lặp lại ở hai requested profiles cùng peak speed không? Đề xuất
pilot **hai profile × ba run = sáu slots**, sau **một slot commissioning**
đã định nghĩa trước: tối đa bảy slots cho E1. Hai profile tăng/giữ/zero theo hai ramp
đã chọn, cùng peak/hold/load/sàn/hướng. Độ lớn/ramp/duration/order còn phải
khóa trước thu; số ba chỉ khảo sát gross inconsistency, không là power hoặc
ước lượng failure-rate tổng quát. Slot commissioning nằm trong tổng bảy,
được báo riêng, không tính thành repeat ID. Nếu không đủ điều kiện/không
đạt mapping/stop thì đóng các slot còn lại,
không thêm smoke/retry. Không tự lấy phím nhấn tay làm ramp chính xác.

Tiến thẳng hai bánh cùng reference chỉ kiểm dấu tiến/zero/freshness, không
chứng minh kênh trái/phải không bị đổi chỗ. Danh tính cần đối chiếu riêng
với bánh vật lý (ưu tiên evidence kiểm bánh trái đã có nếu đủ) hoặc một
differential maneuver được chốt trong slot commissioning; không thêm slot.

Required tối thiểu cho final-command→wheel: raw final Twist, raw feedback hai
bánh, status/freshness; thêm source/intermediate theo claim và event labels.
IMU hỗ trợ ngữ cảnh, không thay reference body. Ghi clock và trạng thái
source→final; không có target sau ramp thì target unavailable.

Primary là **tổng thời gian đáp ứng được định nghĩa theo run**, tách start
command và final-command origin; báo bracket first detectable wheel change,
rise/plateau90 nếu plateau được định nghĩa và có support, stop-to-band nếu
có band/window chốt trước. Không đạt plateau hoặc bị abort thì giữ censored/
unavailable, không loại run. Báo per-wheel và per-run, min/max/range; không
dùng CI nhỏ mẫu như bằng chứng generalization. Nguồn khoảng 47 Hz chỉ cho
bracket theo mẫu/gap thực, không nội suy ra millisecond precision.

Go: có thể mô tả repeatability và response tổng trong uncertainty. Unknown:
không tách được transport/ramp/actuation hoặc effect dưới độ phân giải. Một
correction measurement cụ thể tối đa trước quyết định; một batch khác cần
protocol/release khác, không tự gia hạn. Không gọi T90 từ đầu ramp là pure
deadtime/bandwidth motor hoặc bằng chứng H2 contact.

### E2 — reference thân và geometry ở mức claim cần thiết

**[Đ] Câu hỏi:** reference ngoài encoder có đủ để phân biệt endpoint distance/
yaw với sai số wheel odom hiện tại không? Đề xuất tối đa hai maneuver (straight
và turn), ba run mỗi maneuver, sáu slots mới sau gate E1; velocity/distance/
angle phải khóa riêng. Đây là pilot calibration/validation, không tiếp tục
đếm run E1 như independent replication.

Chọn video có mốc và sync hoặc scan-matching với độ độc lập khỏi encoder
được đánh giá; khai báo mọi input/prior chia sẻ. Không dùng wheel-fused pose
để kiểm chính wheel odom. So uncertainty với effect quan tâm trước khi mua sensor.
Reference đáp ứng endpoint nhưng không transient vẫn hữu ích cho geometry;
chưa đủ cho slip instant. Ba run không cho confidence tốt về tail risk.

Go cho claim reference thực sự hỗ trợ. Unknown nếu drift/gap/sync chi phối;
không mở rộng sang body-slip claim bằng cách gọi fused odom là ground truth.

### E3 — một cơ chế gờ, fixed-profile envelope

**[Đ] Câu hỏi đầu tiên:** fixed speed/profile đã chọn có trade-off quality/
crossing/time lặp lại trong một regime hình học không? Đề xuất hai fixed
profiles × ba lặp/block session × hai session = **12 slots**, sau E1/E2 và
đo fixture/caster/clearance cần thiết. Session là block, không coi mọi frame
hoặc cùng seed là counterfactual cùng trạng thái. Geometry/độ lớn profile
chưa được chấp nhận; không lấy 6 mm hoặc 0,4 m/s sim làm mức thử thật.

Không dùng E3 này để tuyên bố H2 đạt. So low/faster fixed approach chỉ là
baseline envelope. Nếu kết quả tạo premise cho H2 thì protocol khác phải
khóa trigger deployable/oracle, action và timing thực thi, comparator matched
time/shaping, phase outcome còn lại; biết vị trí gờ phải gắn nhãn preview.

Primary quality metric chốt trước, có thể là IMU vibration trong bandwidth
đã giải thích; slip cần body reference hợp lệ. Giữ crossing/stall/stop và
time/tracking constraints. Outcome dominated by clearance/caster/support
thì đổi cơ khí/avoidance; sampling-sensitive thì unknown; không tăng mẫu tự
động hoặc bỏ spike để làm đẹp. Số lặp là pilot mô tả, không cam kết power.

## 7. Quyết định từng nhánh và mức đầu tư

| Nhánh | Quyết định hiện tại | Điều kiện mở lại |
|---|---|---|
| PI/backend velocity + shaping | Ưu tiên nhận dạng contract, không copy gain/limit sim | Dữ liệu wheel + mode/limits/timing hợp lệ |
| Reactive frozen | Giữ baseline | Có thí nghiệm authority/outcome hợp lệ |
| PPO/BC, predictor | Tạm dừng triển khai/training | Cần lợi thế thông tin/action đã được chứng minh và baseline classical mạnh |
| MPC/RG | Ứng viên, chưa triển khai | Constraints/model/latency phù hợp và có actuator authority |
| Optuna | Công cụ tuning nhỏ sau objective/gate | Có protocol/classical parameter question; không dùng để sửa measurement |
| V7 sim | Frozen/unreleased trong evidence | Quyết định riêng nếu sim timing contrast có information gain đủ; không tự tạo v8 |
| Maps/curriculum | Tái sử dụng, chưa mở rộng train | Đã có cơ chế và parameter uncertainty cần generalize |
| Navigation | Giải quyết contract scan/TF theo nhu cầu; không bắt full Nav2 cho wheel claim | Path explicit và có readiness riêng |
| Route memory | Dự phòng có điều kiện sau envelope/repeated-route evidence | Định vị/direction/TTL/session stability + so hand-coded speed zones |
| Cơ khí/sensing | Dự phòng khi geometry hoặc measurement chi phối | Một phép phân biệt và cải tiến đo được; chưa mua theo budget placeholder |

Effort trước mắt thấp–vừa vì dùng Pi/STM32/IMU/encoder/LiDAR và collector
hiện có. E2 có thể cần reference tạm; E3 phụ thuộc fixture và đo cơ khí.
Chưa có căn cứ chốt chi phí tiền hoặc ngày hoàn thành. Tính mới khoa học
hiện **chưa đủ cơ sở**; benchmark/mechanism paper là giả thuyết đóng góp,
không tự trở thành mới vì dùng một robot có tên khác.

## 8. Sửa đổi đã thực hiện và bước ngay sau đây

Đã lưu bản báo cáo nhận nguyên vẹn cùng hash; lập source-check có URL; sửa
thứ tự ưu tiên và gate ở tài liệu này. Đã thêm profile wheel-response riêng,
session template có motion/clock/run contract, và hướng dẫn `--check`; sửa
ghi chú cũ nói chưa có thử collector trên Pi. Các biểu mẫu còn null ở
hardware mode/limits/stop chưa có bằng chứng. Không có session motion mới.

[Xác minh offline](nino_progress_review_2026-10-28/verification.json):
collector `--check` exit 0 khi process creation bị chặn, không import rclpy,
không tạo output directory; full profile và nhóm evidence generic được giữ.
Package share đã có entry cho protocol mới. Đây là software preparation,
không phải gate motor đã qua.

**Việc ngay tiếp theo:** hoàn tất P1 trên đúng runtime khi nối lại Pi và
với người vận hành: final owner + RC mapping + stop semantics + profile đã
chốt. Artifact cần là một session/contract được điền có evidence, rồi mới
mở E1. Không cần thu lại ba tư thế hay gyro sign. Nếu đã có motor-driven bag
mới ngoài bằng chứng hiện tại, đánh giá bag đó trước mọi đề nghị thu thêm.
