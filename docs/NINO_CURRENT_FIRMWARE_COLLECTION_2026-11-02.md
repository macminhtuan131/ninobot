# Nino — chuẩn bị thu trên firmware hiện tại, 02/11/2026

> **Đánh giá raw lượt v2 bị ngắt:** chỉ còn 3,703 s trước trial; mẫu cuối trước forward 5,381 s. SQLite index integrity fail, không còn primary motion window. Helper log source completed không thay raw. Pilot giữ stopped 1/3; chưa thu thêm. Báo cáo workspace: `artifacts/interrupted_pilot_v2_evaluation_2026-11-02/REPORT.md`. Đề xuất tiếp: một capture đứng yên kiểm recorder closure trước ngân sách motion mới.


> **Cập nhật sau reboot 02/11:** Agent và sensor readers đã nối lại ở boot 415f7fe9; raw IMU/hai bánh/LiDAR/TF có dữ liệu. Pilot v2 **đóng ở 1/3**, hai slot còn lại đóng: trial source đã kết thúc nhưng recorder chưa có closure trước reboot. Giữ raw, chưa retry. Không dùng lệnh thu bên dưới để chạy lại đợt đã đóng.


> **Cập nhật mới nhất 02/11: pilot v2 đã được đồng ý và chuẩn bị, 0/3 lượt.**
> V1 vẫn đóng ở 1/3, hai slot cũ không tái sử dụng. Readiness mới kiểm live
> trước cấp slot; zero-only preflight đạt, chưa chạy motion pilot.
> [Lệnh thu lượt 1 và điểm dừng](NINO_WHEEL_REPEATABILITY_PILOT_V2_2026-11-02.md).
> Các cập nhật cũ bên dưới là lịch sử.


## Pilot repeatability dừng trước motion — lifecycle startup lỗi

Slot1 `wheel_repeatability_20261102T053608943617Z` failed readiness trước
enable/forward; selected có, smoother/final không có. Log xác định smoother
configure-response timeout, manager chưa activate và monitor chưa configure.
21/21 checksum khớp, bag/audit đóng sạch nhưng required missing nên manifest
incomplete. Pilot stopped,2slot còn lại closed, không reset/retry.

Đã chuẩn bị correction readiness ngay ở startup và trước cấp session;
13unit readiness/preallocation đạt, một zero-only check live đạt, không
source/enable hay firmware/PI/QoS thay đổi. Chưa chứng minh lỗi middleware
đã hết. Candidate pilot v2 giữprofile, pendingnewbudget và readinessfalse;
không dùng lại2slot cũ. Xem [pilot stopped](NINO_WHEEL_REPEATABILITY_PILOT_2026-11-02.md).

## Pilot 3 lượt đã chuẩn bị theo yêu cầu mới

Người dùng yêu cầu thực hiện pilot đề xuất. Đã freeze contract cho tối đa
3operator-invoked attempts, cùng0,05m/s; session/ledger riêng, review sau
mỗi lượt, không retry/bù. Hiện0/3slots, chưa có motion pilot. Firmware giữ
nguyên, RC AUTO/cùng sàn tải do operator xác nhận khi ghi. Xem
[pilot và lệnh lượt1](NINO_WHEEL_REPEATABILITY_PILOT_2026-11-02.md).

17 runtime input hashes khớp,6 mocked handoff và13 ledger/metric tests đạt;
zero preflight208 final references đều zero và lifecycle active, không
source/enable changes. Runtime `~/nino_runtime/wheel_repeatability_pilot_20261102_v1/`.

## Kết quả mới nhất — đã có tiến và tự dừng trong một followup RC AUTO

Session `rc_auto_followup_20261102T050858953708Z`: manifest
captured_not_calibrated, issues rỗng, bag/audit exit0;23/23 file checksum
khớp, SQLite ok, required channels đủ. Source39/selected41/smoothed51/
final51 positive commands,max0,05m/s,yaw0. Raw hai bánh tăng góc rõ;
source-forward mean left/right0,7027/0,6016rad/s, sau finalzero gần0.
Người vận hành báo xe tiến ngắn, tự dừng, không lệch/giật rõ.

Đạt command-to-wheel và visible motion feasibility cho một lượt sàn sạch.
Góc tăng đến finalzero~1,6966/1,5190rad; nominal encoder distance vớiR0,060m
~0,0965m, không là body displacement GT. Hai bánh chênh phản ứng ban đầu,
giữ mọi spike (gồm right -0,2348rad/s hậu zero), chưa chỉnh gain/geometry.
Không gọi mean gần0 là fine physical stopping guarantee hoặc actuator ID.

Giữ firmware + RC AUTO. Không cần lặp IMU sign/inventory, nối Agent hoặc
sửa logger cho câu hỏi đã qua. Chưa qua repeatability, body/slip reference,
obstacle envelope, governor/RL hoặc generalization. Lượt LOST/no-motion cũ
vẫn giữ riêng; different boot nên không tuyên bố RC là nguyên nhân duy nhất.

Đóng slot followup đã chạy; không chạy lại cùng helper. Bước đề xuất tiếp
là1condition×3lượt cùng numerical profile để kiểm độ lặp và chênh L-R,
chưa release budget/helper hoặc tự chạy. Artifact workspace STM32–Pi:
`artifacts/rc_auto_followup_evaluation_2026-11-02/REPORT.md`,
`wheel_response.png`, `NEXT_PILOT_DRAFT.md`, `next_pilot.protocol.draft.json`.

## RC AUTO, boot mới và followup chuẩn bị ngày 02/11

Người dùng báo RC:AUTO; sau đó xác nhận nguồn motor bật, xe đứng yên trên
sàn trống. Pi vừa reboot, boot `99aa3542-3236-4261-805f-d67b42ef4394`;
Agent/readers đã khôi phục, raw IMU/wheel/joint/LiDAR/TF có dữ liệu. Snapshot
12s status57/57 bằng51: firmware enable bật, timeout, hai feedback fresh.
Đây là bằng chứng tốt hơn RC:LOST nhưng chưa chứng minh có đáp ứng chuyển động.

Live preflight gate Pi disabled tạo 214 selected/212 smoothed/207 final
references đều zero; lifecycle active, owner đúng, không gửi source/enable,
launch đóng exit0. Không bắt buộc firmware enable bit phải off trong kiểm
zero này vì RC đang ở AUTO/armed theo người dùng; không đổi firmware guard.
Readiness gắn boot mới, không dùng token readiness boot cũ.

Runtime followup riêng: `~/nino_runtime/rc_auto_followup_20261102_v1/`.
Cùng numerical profile đã chọn:0,05m/s, shaping0,10m/s², source2s rồi zero/
disable, quan sát3s; bag60s. Ba terminal start_stack → record_wheel →
run_trial; terminal3 chạy ngay khi terminal2 hiện Output. Giữ RC AUTO,
người cạnh nút dừng. Helper chỉ cho một operator-invoked attempt, đóng bằng
followup.claim.json; không retry dù tạo session mới. Chưa chạy motion này.

Lượt cũ `044400` giữ nguyên là no-motion; followup này là điều kiệnRC/boot
khác nên không suy nhân quả định lượng hoặc generalization từ so sánh hai
lượt. Kiểm file/hash11/11 và6 case mock(+repeat refusal) đạt; chưa có kết
quả hardware followup. Artifact workspace `artifacts/rc_auto_followup_2026-11-02/`.

## Quyết định mới của người vận hành: giữ firmware

Người dùng chọn **giữ firmware hiện tại** sau khi board báo RC:LOST.
Không quay lại nhánh flash/ROS-only. Hướng tiếp tục: RC kết nối và cấp quyền
ROS theo firmware thực, người vận hành vẫn phát lệnh bằng teleop trên Pi.

Bước nhỏ kế tiếp là kiểm link và mapping RC, chưa là thử motion: dừng
command stack bằng Ctrl+C ở terminal launch; ngắt riêng nguồn công suất
motor, giữ Pi/STM32/receiver logic hoạt động theo cấu hình thực. Việc bật
handset có thể thay effective source/arm nên chưa bật link khi chưa cô lập
motor. Bật handset, giữ sticks giữa và đọc LCD/ảnh handset; không hướng dẫn
gạt A/E/F chỉ từ source nếu chưa đối chiếu tay thật. Target bước này là
hết LOST và biết trạng thái DISARM/ESTOP/MANUAL/AUTO; chưa cấp phép chạy lại.

Source tham khảo gán A=CH5 (ROS/AUTO khi high), E=CH9 arm và F=CH10 estop
latch, nhưng binary/transmitter mapping thật còn cần xác minh. Sau khi có
link và biết mapping mới xác lập quy trình chọn ROS/arm/stop có đối chiếu;
không coi lựa chọn giữ firmware là mở thêm motion budget hoặc bypass stop.

## Cập nhật RC: LOST từ người vận hành

Board hiện báo `RC: LOST`. Source đã review dừng khi mất SBUS link ngay cả
khi bit firmware enable đặt; phù hợp với lượt ROS positive nhưng bánh không
đáp ứng. Đây là quan sát sau lượt, không là RC trace đồng bộ trong bag;
chưa chứng minh binary identity hoặc nguyên nhân duy nhất.

Giữ firmware hiện tại có thể vẫn cần RC online/chọn ROS/arm để chạy teleop.
Yêu cầu teleop độc lập RC cần chính sách ROS-only trong firmware nếu bản
nạp có cùng logic; Agent/teleop trên Pi không thay điều kiện này. Người
dùng đã yêu cầu giữ firmware nên không tự quay lại flash/BOOT hoặc chạy
lượt mới. Giữ các bản ROS-only offline là chưa deploy.

## Kết quả lượt tiến thật `044400` — ROS đạt, bánh chưa đáp ứng

Session `current_firmware_commissioning_20261102T044400945078Z`:
manifest captured_not_calibrated, issues rỗng, bag và audit exit0. Raw/hash/
SQLite hợp lệ; có đủ required command channels. Đây là lượt commissioning
được người vận hành khởi chạy, không là assistant tự phát chuyển động.

39 source / 40 selected / 50 smoothed / **50 final positive commands**, max
0,05 m/s, yaw zero. Source/gate và Collision Monitor không chặn hết lệnh
trong lượt. Firmware status19 khi enable, về3 sau disable; cả hai feedback
fresh. Wheel position chỉ dao động ~0,00115 rad trong pha source tiến;
không thấy đáp ứng tiến bền vững. Người vận hành xác nhận **xe không di
chuyển**. Arrival/quality/physical stop/control authority chưa đạt; helper
hoàn tất không đồng nghĩa commissioning chuyển động thành công.

**Đóng lượt thử đã chọn, chưa mở thêm motion budget.** Kết thúc audit logger
cho câu hỏi này, không thu lại cùng lượt hoặc tăng speed/current để dò.
Bước kế tiếp là đọc trạng thái RC/arbitration: source firmware tham khảo
có effective_enable sau biến enable, có thể chặn/ghi đè ROS do SBUS. Binary
chưa xác minh nên chưa kết luận RC là nguyên nhân chắc chắn. Đã yêu cầu ảnh
LCD board/vùng `RC:...`, không cần gạt công tắc hoặc chạy lại. Source LCD
có LOST/ESTOP/DISARM/MANUAL/AUTO; chưa xác nhận giao diện bản nạp giống source.

Báo cáo/JSON/raw copy trong workspace STM32–Pi:
`artifacts/wheel_commissioning_evaluation_2026-11-02/REPORT.md`.
Các hướng dẫn chạy trial trong phần lịch sử bên dưới không là release một
lượt mới sau kết quả này. Giữ firmware, không flash hoặc RC bypass tự động.

## Cập nhật sau phiên recording-only `044018` — chưa có lượt tiến

Session `current_firmware_commissioning_20261102T044018461949Z` ghi đủ thời
lượng, bag và audit đều exit0/không forced; audit không còn lỗi diagnostics.
20/20 checksum khớp, SQLite `ok`. Manifest vẫn incomplete vì thiếu hai topic
required `/cmd_vel_teleop` và `/motor_enable`; không sửa required/manifest.

Bag có 1048 final Twist đều zero, motor_status 254×3 + 23×35, không có
trial claim/event/result/readiness failure artifact. Kết luận giới hạn:
chưa có bằng chứng helper vào lượt thử trong session. Không loại trừ helper
đã lỗi sớm trước khi gắn vào session nếu không có output terminal 3. Không
coi phiên này là motor-response trial hoặc lỗi recorder/driver. Không có
nonzero/enable request được ghi. Review artifact:
`artifacts/current_firmware_collection_2026-11-02/recording_only_044018_review.json`.

Cần mở ba terminal **đồng thời**. Terminal 1 chạy stack, terminal 2 chạy
recorder; ngay khi terminal 2 hiện Output thì chạy terminal 3 `run_trial.sh`,
không đợi terminal 2 kết thúc. Nếu đã chạy terminal 3 mà lỗi sớm, đọc đúng
output đó trước khi mở phiên mới. Snapshot process sau phiên cho thấy
command stack không còn chạy; khởi động terminal 1 lại khi thực hiện lượt
đã chọn. Giữ session recording-only này và không tính nó là một lượt motion
thành công/thất bại. Không thay firmware hoặc tự gửi lệnh chuyển động.

## Cập nhật 11:38 (+07) — lượt zero hoàn tất, lỗi audit được khoanh vùng

Lượt `zero_feedback_20261102T043000235565Z` có chuỗi zero/enable/disable
hoàn tất, nhưng manifest **vẫn incomplete** vì audit compact lỗi chuyển
`DiagnosticStatus.level` dạng `b'\x00'` sang int. Bag chính exit0, không
thiếu topic required, SQLite `ok`, 23/23 file checksum khớp. Không sửa raw
hoặc promote manifest gốc. Báo cáo qualification theo từng claim nằm trong
workspace STM32–Pi tại
`artifacts/zero_feedback_probe_2026-11-02/evaluation_043000/REPORT.md`.

Raw: 159 Twist đều zero cả sáu thành phần; hai enable Bool true/false.
136 status đều có freshness hai bánh: 35×95, 3×22, 19×19; zero baseline /
enable requested / disable requested có lần lượt 3 / 19 / 3. Firmware ACK
không là effective RC permission hoặc actuator mode readback. Bánh có mean
velocity gần zero nhưng giữ đủ peak/jitter; người vận hành xác nhận xe đứng
yên và không giật rõ. Chưa có dataset motion/physical stop/slip thật.

Đã sửa parser diagnostics byte/int trong source repo và Pi (không sửa
controller/firmware), 30 unit tests đạt. Audit read-only 5 s sau sửa exit0,
errors rỗng, đọc được 6 diagnostics; không tạo command publisher. **Không
cần lặp lượt motor zero chỉ để có manifest đẹp.** Giữ lỗi và báo cáo riêng.

Live preflight chuỗi command đã thực hiện với gate disabled: 230 selected,
202 smoothed, 201 final references đều zero; smoother và Collision Monitor
active, owner đúng, status luôn disabled/fresh. Launch đã dừng sạch; không
gửi motor_enable hay source velocity trong kiểm tra. Runtime/handoff có
6 case mock đạt; bắt buộc recorder và STM32 subscribe enable trước khi gửi;
SIGINT/SIGTERM đi qua cleanup zero/disable. Không bypass Collision Monitor.

**Bước tiếp theo: một lượt commissioning tiến–zero đã chọn trước.** Mở ba
terminal trên Pi, theo thứ tự, giữ các terminal trước chạy:

1. `bash ~/nino_runtime/current_firmware_collection_20261102_v1/start_stack.sh`
2. `bash ~/nino_runtime/current_firmware_collection_20261102_v1/record_wheel.sh`
3. `bash ~/nino_runtime/current_firmware_collection_20261102_v1/run_trial.sh`

Terminal 3 tự chờ recorder/telemetry; chạy ngay sau khi mở terminal 2,
không để session quá 30 s mới bắt đầu. Profile source 0,05 m/s trong mục tiêu
2 s, shaping reference 0,10 m/s²; zero/disable rồi quan sát 3 s; bag 60 s.
Người vận hành cạnh nút dừng và sàn trống, không thao tác RC trong lượt.
Nếu xe không chạy, lỗi hoặc bị chặn: giữ outcome và không tự retry. Đợi
terminal 2 đóng bag trước khi restart Pi/đóng session. Cuối cùng Ctrl+C
terminal 1 để dừng chuỗi command. Không quay lại helper cũ ngày 01/11.

Readiness phần mềm gắn boot `ccd18cfb-4138-463b-b3d2-e4087c802a0d`, không
là đảm bảo cơ khí/an toàn. Chưa chạy nonzero trial; quyền RC thật và
command-to-motion vẫn cần đo. Không đổi firmware.

## Cập nhật 11:28 (+07) — sửa readiness của recorder, chưa enable thật

Lượt người dùng `zero_feedback_20261102T042419791275Z` dừng ở readiness,
trước khi tạo publisher command trong helper cũ. Bag ghi được sensor,
31 status đều 35 (0x23); `/cmd_vel` và `/motor_enable` không có message,
không có event sequence. 22/22 file hash khớp, SQLite integrity `ok`,
metadata bag đóng. Manifest vẫn `incomplete` vì supervisor ngắt collector
khi readiness timeout; audit bị ngắt và hai command channels thiếu. Không
sửa raw/manifest hoặc coi lượt này là thử enable. Bản sao raw và source cũ
được giữ trong `artifacts/zero_feedback_probe_2026-11-02/failed_readiness_042419/`.

**Nguyên nhân helper:** chờ recorder subscribe `/motor_enable` trước khi
advertise publisher của nó. Rosbag hiện tại chỉ subscribe topic có publisher.
Mock ban đầu đã giả định recorder subscribe ngay khi chạy nên bỏ sót lỗi này.

Một correction có căn cứ đã deploy: tạo hai publisher để advertise type trước
khi chờ; chưa publish message. Chờ cả recorder và STM32 trên cả `/cmd_vel`
và `/motor_enable`, sau đó mới bắt đầu zero baseline/enable/disable. Nếu
recorder không match thì không gửi zero/enable/disable. Owner/freshness
checks giữ nguyên. Bản cũ trên Pi giữ tại `record_zero_probe.py.before_recorder_fix`.
Helper mới SHA256:
`3c354a91f0b406ca1187d756789a85081931d478a0bbf796d18b498e69273356`.

Kiểm chứng: mock mới tái hiện lỗi với code cũ, đạt 4 case sau correction
(normal, competing owner, stale status, recorder không match và không gửi
command). Fixture ROS thật trên Pi dùng hai topic riêng trong namespace
`/nino_recorder_discovery_fixture_<id>/`, không trỏ motor: trước advertise
không match, sau advertise chưa gửi message đã match cả hai; gửi 20 Twist
zero + 20 Bool false, bag đủ 20/20 mỗi topic, SQLite `ok`, metadata đóng.
Fixture không chứng minh enable, CAN hoặc stopping thật. File-only check
trên Pi đạt; không tự chạy lại probe motor.

Read-only snapshot mới lúc 11:25:48, cùng boot `ccd18cfb`: status 57/57 bằng
35, raw IMU 567, motor_fb 566, joint/odom_unfiltered 557, scan 67; không có
publisher command motor. **Feedback freshness đã có trước enable**; chưa
biết nguyên nhân thay đổi từ snapshot 32 cũ. Lượt thu zero kế tiếp dùng để
kiểm yêu cầu enable/disable và feedback trong các phase, không gán feedback
xuất hiện cho enable nếu baseline đã fresh.

Người vận hành có thể chạy lại **một lượt sau correction**, cùng command
`record_zero_probe.sh` bên dưới, giữ xe tại chỗ/người cạnh nút dừng; helper
không yêu cầu tiến. Nếu tiếp tục lỗi thì giữ artifact và dừng để ra quyết
định, không tự mở chuỗi correction/retry. Chưa chạy `run_trial.sh`.

## Cập nhật mới nhất — boot `ccd18cfb`, 02/11 lúc 11:18–11:21 (+07)

Pi `.109` đã nối SSH lại. Đã khôi phục Agent, bridge/state publisher,
LiDAR và EKF bằng wrapper cũ trong boot
`ccd18cfb-4138-463b-b3d2-e4087c802a0d`. Launcher PID tương ứng
1222/1228/1241/1250; không dùng PID của các boot lịch sử dưới đây.

Quan sát read-only 12 s: raw IMU 568 mẫu (~47,28 Hz), `/motor_fb` 568,
`/motor_status` 57/57 bằng 32, `/scan_raw` 80 (~6,66 Hz). TF mounting
đạt cấu hình; source header trong cửa sổ không zero/nonincreasing.
Không có publisher trên `/cmd_vel`, `/cmd_mit`, `/cmd_torque`, `/motor_enable`.
`/joint_states` và `/odom/unfiltered` chưa có vì thiếu freshness CAN;
EKF/TF xuất hiện không chứng minh có body reference hoặc wheel input hợp lệ.

Status 32 theo schema source tham khảo: command timeout, enable-variable
chưa đặt, hai bit freshness chưa đặt. Message `/motor_fb` có mặt không
chứng minh CAN motor đang cập nhật. Firmware đang nạp chưa xác nhận trùng
commit nguồn đã review.

**Bước kế tiếp đã chuẩn bị và deploy, chưa chạy:** một lượt đứng yên chỉ
zero → ROS enable (mục tiêu 4 s) → disable, recorder 30 s. Mục đích là
phân biệt liệu feedback có xuất hiện sau enable; không yêu cầu freshness
trước enable cho riêng phép kiểm này để tránh vòng điều kiện. Motion trial
vẫn phải có feedback hợp lệ. Không có nonzero Twist trong helper này;
enable có thể cấp lực giữ motor và cần người vận hành cạnh xe/nút dừng.
Không thay firmware hoặc bỏ điều kiện RC trong STM32.

Runtime trên Pi:
`~/nino_runtime/zero_feedback_probe_20261102_v1/`.

```bash
bash ~/nino_runtime/zero_feedback_probe_20261102_v1/record_zero_probe.sh
```

Helper tự mở recorder, chờ recorder subscribe, kiểm owner/status, baseline
zero 2 s, enable/hold zero 4 s, disable/zero 2 s rồi chờ recorder đóng.
Thu raw feedback/status/IMU, final zero command, enable request; scan/TF và
các tầng command khác là optional theo tình trạng thật. Không tạo target
telemetry hoặc giả vờ trace toàn chuỗi teleop. Lỗi/stale/owner cạnh tranh
sẽ kết thúc lượt và yêu cầu disable; không tự chạy lại. Các yêu cầu dừng
ROS không thay cho cơ chế dừng vật lý đã kiểm tại xe.

Đã kiểm syntax/file-only trên Pi và đối chiếu SHA256 5/5 file. Ba tình
huống mock offline đạt: bình thường, owner cạnh tranh, status stale sau
enable; chỉ xác minh helper/cleanup, không phải CAN/stop hoặc robot thật.
Artifact cục bộ: `artifacts/zero_feedback_probe_2026-11-02/` trong workspace
STM32–Pi, gồm live snapshot, deployment/hash, source/config và test offline.
Assistant chưa chạy phép enable này hoặc trial tiến.

**Đến bước người vận hành thu:** giữ motor được cấp nguồn, xe tại vùng trống,
người cạnh nút dừng, không thao tác RC trong lượt; nếu xe tự chuyển động thì
dừng bằng nút đã kiểm và giữ toàn bộ artifact. Chạy lệnh đúng một lần,
đợi thông báo `Done`; không restart Pi giữa lượt. Gửi output/session để
đánh giá trước khi chạy `run_trial.sh`.

Go/stop/unknown: nếu raw cho thấy freshness cả hai bánh trong cửa sổ enable,
status disable trở lại và integrity/closure đạt thì tiếp tục kiểm readiness
lượt tiến đã chọn. Nếu không có feedback, mất kết nối hoặc chưa ACK disable,
giữ dữ liệu và dừng để phân biệt CAN/firmware/arbitration; không kết luận
cần flash, không tự retry. Bit enable chỉ là trạng thái firmware, không
phải actuator readback hay chứng minh không cần RC khi chuyển động.

## Lịch sử trước boot `ccd18cfb` (không là trạng thái live hiện tại)

## Quyết định và bằng chứng mới nhất

Giữ firmware STM32 hiện tại; không tiếp tục nạp bản ROS-only. Người dùng
muốn assistant chuẩn bị đến lúc cần thao tác thu dữ liệu. Không chạy lại
calibration tư thế/gyro đã có bằng chứng.

Đã tái sử dụng Agent đang chạy (PGID 1646) và khôi phục bridge/state publisher,
LiDAR raw, EKF reader trong boot cuối đọc được
`ceb30e10-5401-494a-99ed-2c8b51662909`. Runtime/log:
`~/nino_runtime/collection_preparation_20261102_v1/`, launcher PGID
sensors/LiDAR/EKF 2231/2232/2233. Không có publisher trên bốn topic input
motor khi kiểm; không flash/enable/velocity/torque được assistant gửi.

Lần kiểm 12 s chưa đạt readiness: IMU raw/bridge và motor_fb đều 568 mẫu,
status 57/57 bằng 32, TF mounting đúng; thiếu joint states và odom/unfiltered
khi status chưa có CAN freshness. LiDAR đọc được serial/firmware/health nhưng
start scan lỗi `80008000`; process thoát. Giữ log, không coi LiDAR có scan
chỉ vì thiết bị được nhận hoặc motor quay.

Sau đó người dùng báo đã cấp nguồn công suất, LiDAR quay và đã restart Pi.
Đây là operator report mới hơn snapshot trên. Pi `.109` hiện không truy cập
được: SSH `No route to host`, ARP `FAILED` từ laptop `.121`. **Chưa xác nhận
boot mới, feedback hoặc scan sau khi cấp nguồn.** Không coi các PID cũ còn
sống sau restart. Đã yêu cầu `hostname -I` và `ip -br address` trên Pi.

## Phần chuẩn bị offline đã hoàn thành

Artifact:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/current_firmware_collection_2026-11-02/`.

- Profile riêng giữ source tiến 0,05 m/s trong mục tiêu 2 s, ramp reference
  0,10 m/s², zero và quan sát 3 s, bag 60 s; không mở ngân sách nhiều lượt.
- Required gồm bốn tầng source/selected/smoothed/final, motor feedback,
  status, raw IMU và `/motor_enable`. Không tạo executed wheel target hoặc
  suy torque đo được từ effort.
- Helper mới yêu cầu ROS motor enable riêng, chờ ACK bit firmware rồi mới
  cho Pi gate phát reference; khi hết lượt chờ final zero, yêu cầu disable.
  Cleanup vẫn zero/disable khi lỗi. **ACK bit 4 không chứng minh quyền RC
  hiệu dụng, mode actuator hay xe sẽ di chuyển. Firmware arbitration được giữ.**
- `stop_pub_timeout=60` giữ zero final trong cửa sổ commissioning để truy
  dấu; không bypass Collision Monitor. Runtime dùng scan_raw và TF thật.
- Guard owner/freshness/recorder còn chạy; một claim/lượt, không tự retry.
  Kết quả không di chuyển, bị chặn hoặc thiếu dữ liệu phải được giữ để phân
  biệt ROS path với điều kiện firmware, không tự suy rằng cần flash.
- `ensure_readers.py` phục hồi các wrapper đọc cũ một lần mỗi boot, không
  launch command stack; từ chối tạo bản trùng hoặc tự restart process lỗi
  trong cùng boot. Không cài service autostart.

Python/shell syntax và collector file-only check đạt. Năm case mocked ROS
(bình thường, enable timeout, owner cạnh tranh, mất enable, wheel stale)
đạt; kiểm nguồn nonzero chỉ sau ACK/gate, zero và disable khi thoát. Đây là
kiểm helper với mock, không test firmware, CAN, physics, Nav2 hoặc stopping
thật. Manifest/hash/logs kèm artifact. **Chưa deploy helper mới, chưa chạy
lượt chuyển động.** `readiness.json` vẫn false, start helper fail closed.

## Việc kế tiếp, theo thứ tự

1. Khôi phục kết nối mạng và đọc boot ID thực. Nếu khác boot cũ, mở lại
   Agent/reader bằng wrapper đã có; không nạp firmware.
2. Quan sát fresh CAN cả hai bánh, message validity và `/scan_raw`/TF. Nếu
   LiDAR còn lỗi với nguồn ổn định, chỉ chọn một correction từ log/driver,
   giữ failure; không hạ gate hoặc bỏ monitor để chạy xe.
3. Khi runtime hợp lệ mới deploy/check helper, đặt readiness cùng boot và
   đưa lệnh thu cho người vận hành. Chưa gọi một lượt motion là ready chỉ
   từ file check hoặc số message.
4. Một lượt commissioning dùng ROS enable trên firmware đang có, không RC
   bypass. Nếu yêu cầu đến firmware nhưng bánh không đáp ứng, giữ raw và
   quyết định từ outcome đó; không tự mở lại nhánh flash/RC hoặc thêm lượt.

Chưa đủ điều kiện gọi người dùng chạy trial/bag ở trạng thái hiện tại.
